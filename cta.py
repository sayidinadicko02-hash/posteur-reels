"""
Robot CTA : répond tout seul aux commentaires « mot-clé » sur TOUS les posts Instagram.

Pour chaque post, le mot-clé est lu dans la description : Commente "IDÉE"  ->  IDÉE.
Le message et le lien de chaque mot-clé sont dans cta.json.
Pour chaque commentaire qui contient le mot-clé :
  - on saute si c'est toi, si tu as déjà répondu sous le commentaire,
    si tu lui as déjà envoyé le guide en DM, ou si le robot l'a déjà traité ;
  - sinon : DM privé avec une QUESTION (« je te l'envoie ? ») + réponse publique ;
  - au passage suivant, s'il a répondu au DM : on envoie le guide. Sinon rien (filtre).
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
MAX_ENVOIS = 15           # questions max par passage (toutes les 10 min) pour ne pas être bloqué
PAUSE = (10, 25)          # secondes entre deux envois (pour rester naturel)
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

def lire_dm(ids_moi):
    """pseudo -> {"id": id de la personne, "miens": [mes textes], "leurs": [(date, texte)]}"""
    convs = {}
    try:
        data = get_all(f"{IG_ID}/conversations", limit_pages=10, platform="instagram",
                       fields="participants,messages.limit(25){from,message,created_time}")
    except Exception as e:
        log("Lecture des DM impossible :", e)
        return convs
    for c in data:
        autres = [p for p in c.get("participants", {}).get("data", []) if str(p.get("id")) not in ids_moi]
        msgs = c.get("messages", {}).get("data", [])
        for p in autres:
            d = convs.setdefault(p.get("username", "").lower(), {"id": p.get("id"), "miens": [], "leurs": []})
            for m in msgs:
                if str(m.get("from", {}).get("id")) in ids_moi:
                    d["miens"].append(m.get("message", ""))
                else:
                    d["leurs"].append((m.get("created_time", ""), m.get("message", "")))
    return convs

def main():
    config = json.load(open(CONFIG_FILE, encoding="utf-8"))
    reponses = config.pop("_reponses_publiques", ["Je t'ai écrit en DM 📩"])
    ctas = {norm(k): (k, v) for k, v in config.items()}
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    traites = set(state.get("traites", []))
    personnes = set(state.get("personnes", []))   # "pseudo|MOTCLE" déjà contactés : un seul DM par personne et par CTA
    attente = state.get("attente", {})            # "pseudo|MOTCLE" -> {"t": date de la question}
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

    convs = lire_dm(ids_moi)
    stats = {"questions": 0, "guides": 0, "deja": 0, "trop_vieux": 0, "erreurs": 0}
    sans_lien, details, guides = set(), [], []

    # ---- 1) Ceux qui ont RÉPONDU à la question -> on envoie le guide ----
    for qui, info in list(attente.items()):
        user, cle = qui.split("|", 1)
        if cle not in ctas:
            attente.pop(qui); continue
        nom_cta, cfg = ctas[cle]
        conv = convs.get(user)
        t0 = date(info["t"])
        if conv and any(dt and date(dt) > t0 for dt, _ in conv["leurs"]):
            texte = cfg["message"].replace("{lien}", cfg["lien"])
            if TEST:
                guides.append(f"@{user}"); continue
            try:
                post(f"{IG_ID}/messages", recipient={"id": conv["id"]}, message={"text": texte})
                attente.pop(qui); stats["guides"] += 1; guides.append(f"@{user}")
                log("Guide envoyé à", user)
                time.sleep(random.uniform(*PAUSE))
            except Exception as e:
                stats["erreurs"] += 1; log("Guide KO", user, e)
        elif (NOW - t0).days >= 7:
            attente.pop(qui)   # pas de réponse en 7 jours : on laisse tomber

    # ---- 2) Nouveaux commentaires -> on pose la question en DM ----
    medias = get_all(f"{IG_ID}/media", limit_pages=5, fields="id,caption,timestamp,permalink", limit=50)
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
            reps = c.get("replies", {}).get("data", [])
            deja_public = any((r.get("username") or r.get("from", {}).get("username", "")).lower() == moi_nom
                              for r in reps)
            deja_dm = any(any(norm(t) in norm(txt) for t in cfg.get("deja_envoye_si", []))
                          for txt in convs.get(user, {}).get("miens", []))
            qui = f"{user}|{cle}"
            if deja_public or deja_dm or qui in personnes:
                stats["deja"] += 1; traites.add(cid); personnes.add(qui); continue
            if (NOW - date(c["timestamp"])).days >= 7:
                stats["trop_vieux"] += 1; traites.add(cid); continue
            if stats["questions"] >= MAX_ENVOIS:
                continue

            if TEST:
                details.append(f"@{user} ({nom_cta})"); stats["questions"] += 1; personnes.add(qui); continue
            try:
                post(f"{IG_ID}/messages", recipient={"comment_id": cid}, message={"text": cfg["accroche"]})
                traites.add(cid); personnes.add(qui)
                attente[qui] = {"t": NOW.strftime("%Y-%m-%dT%H:%M:%S%z")}
                stats["questions"] += 1
                details.append(f"@{user} ({nom_cta})")
                try:
                    post(f"{cid}/replies", message=random.choice(reponses))
                except Exception as e:
                    log("Réponse publique KO", user, e)
                log("Question envoyée à", user)
                time.sleep(random.uniform(*PAUSE))
            except Exception as e:
                stats["erreurs"] += 1
                log("Envoi KO", user, e)

    state["traites"] = sorted(traites)[-5000:]
    state["personnes"] = sorted(personnes)
    state["attente"] = attente
    if not TEST:
        json.dump(state, open(STATE_FILE, "w"), indent=1)

    titre = "🧪 Robot CTA (TEST, rien envoyé)" if TEST else "🤖 Robot CTA"
    if stats["questions"] or stats["guides"] or stats["erreurs"] or TEST:
        msg = (f"{titre}\n💬 questions envoyées : {stats['questions']}\n"
               f"📩 guides envoyés (ont répondu) : {len(guides) if TEST else stats['guides']}\n"
               f"⏳ en attente de réponse : {len(attente)}\n"
               f"⏭️ déjà traités par toi : {stats['deja']}\n"
               f"❌ erreurs : {stats['erreurs']}")
        if guides:
            msg += "\n\nGuide envoyé à : " + ", ".join(guides[:60])
        if details:
            msg += "\n\nQuestion envoyée à : " + ", ".join(details[:60])
        tg(msg)
    log(json.dumps(stats), "| attente :", len(attente), "| sans lien :", sorted(sans_lien))
    log("Questions :", ", ".join(details)); log("Guides :", ", ".join(guides))
    if not TEST and sans_lien and state.get("alerte_sans_lien") != sorted(sans_lien):
        state["alerte_sans_lien"] = sorted(sans_lien)
        json.dump(state, open(STATE_FILE, "w"), indent=1)
        tg("⚠️ Robot CTA : mots-clés sans lien dans cta.json : " + ", ".join(sorted(sans_lien)))

if __name__ == "__main__":
    main()
