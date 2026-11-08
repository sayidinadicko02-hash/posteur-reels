"""
Robot CTA : répond tout seul aux commentaires « mot-clé » sur TOUS les posts Instagram.

Pour chaque post, le mot-clé est lu dans la description : Commente "IDÉE"  ->  IDÉE.
Le message et le lien de chaque mot-clé sont dans cta.json.
Pour chaque commentaire qui contient le mot-clé :
  - on saute si c'est toi, si tu as déjà répondu sous le commentaire,
    si tu lui as déjà envoyé le guide en DM, ou si le robot l'a déjà traité ;
  - sinon : DM privé avec le lien (réponse privée Instagram, possible 7 jours max)
    + réponse publique sous le commentaire.
Récap envoyé sur Telegram.

Secrets : IG_TOKEN_CTA, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (GH_PAT optionnel pour renouveler le jeton)
Mode test (TEST=1) : n'envoie rien, liste seulement ce qui serait fait.
"""
import os, re, json, time, random, datetime, unicodedata, subprocess
import requests

IG = "https://graph.facebook.com/v26.0"   # clé « connexion unifiée » (EAB…)
IG_ID = "17841415914105749"               # id Instagram de @sayidina.automatise
STATE_FILE = "cta_state.json"
CONFIG_FILE = "cta.json"
JOURS_POSTS = 30          # posts publiés il y a moins de 30 jours
MAX_ENVOIS = 60           # sécurité : envois max par passage
PAUSE = (4, 9)            # secondes entre deux envois (pour rester naturel)
TEST = os.environ.get("TEST", "0") == "1"
TOK = os.environ["IG_TOKEN_CTA"].strip()
NOW = datetime.datetime.now(datetime.timezone.utc)

def log(*a): print(*a, flush=True)

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                      data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000],
                            "disable_web_page_preview": True}, timeout=30)
    except Exception as e:
        log("Telegram KO", e)

def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.upper()

def date(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")

# ---------- API Instagram ----------
def get(path, **params):
    params["access_token"] = TOK
    r = requests.get(f"{IG}/{path}", params=params, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"GET {path} -> {r.status_code} {r.text[:300]}")
    return r.json()

def get_all(path, limit_pages=20, **params):
    out, data = [], get(path, **params)
    for _ in range(limit_pages):
        out += data.get("data", [])
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=60)
        if r.status_code != 200:
            break
        data = r.json()
    return out

def post(path, **payload):
    r = requests.post(f"{IG}/{path}", json=payload,
                      headers={"Authorization": f"Bearer {TOK}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"POST {path} -> {r.status_code} {r.text[:300]}")
    return r.json()

# ---------- Jeton ----------
def renouveler_jeton(state):
    global TOK
    if not TOK.startswith("IG"):
        return   # clé unifiée : pas de renouvellement ici, alerte si elle expire
    last = state.get("last_refresh", "")
    if last and (datetime.date.today() - datetime.date.fromisoformat(last)).days < 7:
        return
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": TOK}, timeout=30)
        r.raise_for_status()
        new = r.json()["access_token"]
        state["last_refresh"] = datetime.date.today().isoformat()
        if os.environ.get("GH_PAT") and not TEST:
            subprocess.run(["gh", "secret", "set", "IG_TOKEN_CTA", "--body", new],
                           env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]}, check=True)
            log("Jeton renouvelé et enregistré.")
        else:
            jours = r.json().get("expires_in", 0) // 86400
            if jours < 10:
                tg(f"⚠️ Robot CTA : ton jeton Instagram expire dans {jours} jours. "
                   "Génère-en un nouveau et remplace le secret IG_TOKEN_CTA.")
        TOK = new
    except Exception as e:
        log("Renouvellement du jeton KO :", e)

# ---------- Logique ----------
RE_MOT = re.compile(r'comment\w*\s*(?:le mot\s*)?["“«]\s*([^"”»]+?)\s*["”»]', re.I)

def mot_cle(caption):
    m = RE_MOT.search(caption or "")
    return m.group(1).strip() if m else None

def contient(texte, mot):
    return re.search(r"(?<![A-Z0-9])" + re.escape(norm(mot)) + r"S?(?![A-Z0-9])", norm(texte)) is not None

def dm_deja_envoyes(ids_moi):
    """Pseudo -> textes de tes messages envoyés (pour ne pas renvoyer un guide déjà envoyé à la main)."""
    envoyes = {}
    try:
        convs = get_all(f"{IG_ID}/conversations", limit_pages=10, platform="instagram",
                        fields="participants,messages.limit(25){from,message}")
    except Exception as e:
        log("Lecture des DM impossible :", e)
        return None
    for c in convs:
        autres = [p.get("username", "") for p in c.get("participants", {}).get("data", [])
                  if str(p.get("id")) not in ids_moi]
        miens = [m.get("message", "") for m in c.get("messages", {}).get("data", [])
                 if str(m.get("from", {}).get("id")) in ids_moi]
        for u in autres:
            envoyes.setdefault(u.lower(), []).extend(miens)
    return envoyes

def main():
    config = json.load(open(CONFIG_FILE, encoding="utf-8"))
    reponses = config.pop("_reponses_publiques", ["C'est envoyé en DM 📩"])
    ctas = {norm(k): (k, v) for k, v in config.items()}
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    traites = set(state.get("traites", []))
    renouveler_jeton(state)

    try:
        moi = get(IG_ID, fields="id,username")
    except RuntimeError as e:
        if "190" in str(e):
            tg("⚠️ Robot CTA : ta clé Instagram ne marche plus (expirée ?). Génère-en une nouvelle et remplace le secret IG_TOKEN_CTA.")
        raise
    moi_nom = moi["username"].lower()
    ids_moi = {IG_ID}
    log("Compte :", moi_nom)

    envoyes = dm_deja_envoyes(ids_moi) or {}
    medias = get_all(f"{IG_ID}/media", limit_pages=5, fields="id,caption,timestamp,permalink", limit=50)

    stats = {"envoyes": 0, "deja": 0, "trop_vieux": 0, "erreurs": 0}
    sans_lien, details = set(), []

    for m in medias:
        if (NOW - date(m["timestamp"])).days > JOURS_POSTS:
            continue
        mot = mot_cle(m.get("caption"))
        if not mot:
            continue
        cle = norm(mot)
        if cle not in ctas:
            sans_lien.add(mot); continue
        nom_cta, cfg = ctas[cle]
        if not cfg.get("lien"):
            sans_lien.add(nom_cta); continue

        comments = get_all(f"{m['id']}/comments", limit_pages=20, limit=50,
                           fields="id,text,timestamp,username,from,replies{username,from}")
        for c in comments:
            cid, user = c["id"], (c.get("username") or c.get("from", {}).get("username", "")).lower()
            if cid in traites or user == moi_nom or str(c.get("from", {}).get("id")) in ids_moi:
                continue
            if not contient(c.get("text", ""), nom_cta):
                continue
            # déjà répondu publiquement ?
            reps = c.get("replies", {}).get("data", [])
            deja_public = any((r.get("username") or r.get("from", {}).get("username", "")).lower() == moi_nom
                              for r in reps)
            # déjà envoyé en DM ?
            deja_dm = any(any(norm(t) in norm(txt) for t in cfg.get("deja_envoye_si", []))
                          for txt in envoyes.get(user, []))
            if deja_public or deja_dm:
                stats["deja"] += 1; traites.add(cid); continue
            if (NOW - date(c["timestamp"])).days >= 7:
                stats["trop_vieux"] += 1; traites.add(cid); continue
            if stats["envoyes"] >= MAX_ENVOIS:
                continue

            texte = cfg["message"].replace("{lien}", cfg["lien"])
            if TEST:
                details.append(f"@{user} ({nom_cta})"); stats["envoyes"] += 1; continue
            try:
                post(f"{IG_ID}/messages", recipient={"comment_id": cid}, message={"text": texte})
                traites.add(cid)
                stats["envoyes"] += 1
                details.append(f"@{user} ({nom_cta})")
                try:
                    post(f"{cid}/replies", message=random.choice(reponses))
                except Exception as e:
                    log("Réponse publique KO", user, e)
                log("Envoyé à", user)
                time.sleep(random.uniform(*PAUSE))
            except Exception as e:
                stats["erreurs"] += 1
                log("Envoi KO", user, e)

    state["traites"] = sorted(traites)[-5000:]
    if not TEST:
        json.dump(state, open(STATE_FILE, "w"), indent=1)

    titre = "🧪 Robot CTA (TEST, rien envoyé)" if TEST else "🤖 Robot CTA"
    if stats["envoyes"] or stats["erreurs"] or TEST:
        msg = (f"{titre}\n✅ {'à envoyer' if TEST else 'envoyés'} : {stats['envoyes']}\n"
               f"⏭️ déjà traités par toi : {stats['deja']}\n"
               f"⌛ trop vieux (+7 j, impossible) : {stats['trop_vieux']}\n"
               f"❌ erreurs : {stats['erreurs']}")
        if details:
            msg += "\n\n" + "\n".join(details[:60])
        if sans_lien:
            msg += "\n\n⚠️ Mots-clés sans lien dans cta.json : " + ", ".join(sorted(sans_lien))
        tg(msg)
    log(json.dumps(stats), "| sans lien :", sorted(sans_lien))
    if not TEST and sans_lien and state.get("alerte_sans_lien") != sorted(sans_lien):
        state["alerte_sans_lien"] = sorted(sans_lien)
        json.dump(state, open(STATE_FILE, "w"), indent=1)
        if not stats["envoyes"]:
            tg("⚠️ Robot CTA : mots-clés sans lien dans cta.json : " + ", ".join(sorted(sans_lien)))

if __name__ == "__main__":
    main()
