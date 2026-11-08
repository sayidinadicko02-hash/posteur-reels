"""
Robot CTA : répond (presque) instantanément aux commentaires « mot-clé » sur TOUS les posts Instagram.

Pour chaque post, le mot-clé est lu dans la description : Commente "IDÉE"  ->  IDÉE.
Le texte et le lien de chaque mot-clé sont dans cta.json.

1) Quelqu'un commente le mot-clé -> DM « Je te l'envoie ? » + réponse « Regarde tes DM » sous le commentaire.
   (on saute : toi-même, ceux à qui tu as déjà répondu ou déjà envoyé le guide, une seule fois par personne)
2) Il répond au DM -> on lui envoie tout de suite le guide, puis 2-3 s après un 2e message :
   « Dis-moi, t'as déjà un business ou t'aimerais te lancer ? »
3) Il ne répond pas -> rien (filtre). Oublié au bout de 7 jours.
4) DM impossible (compte fermé aux messages…) -> réponse sous le commentaire « écris-moi en DM » ;
   dès qu'il écrit en DM, il reçoit le guide + la relance.

Le script tourne en boucle (DM vérifiés toutes les 20 s à 5 min selon le quota Meta) pendant ~5 h 45, puis GitHub le relance.
L'état (qui a été contacté) est rangé dans Dropbox /ROBOT_CTA/etat.json, pas sur GitHub (dépôt public).

Secrets : IG_TOKEN_CTA, DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN,
          TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Mode test (TEST=1) : un seul passage, rien n'est envoyé.
"""
import os, re, json, time, random, datetime, unicodedata
import requests

IG = "https://graph.facebook.com/v26.0"   # clé « connexion unifiée » (EAB…)
IG_ID = "17841415914105749"               # id Instagram de @sayidina.automatise
MOI = "sayidina.automatise"
CONFIG_FILE = "cta.json"
ETAT_DROPBOX = "/ROBOT_CTA/etat.json"
JOURS_POSTS = 30          # on surveille les posts de moins de 30 jours
INTERVALLE = 15           # secondes entre deux vérifications
DUREE_MAX = 5 * 3600 + 45 * 60
MAX_PAR_MINUTE = 6        # questions max par minute (anti-blocage Instagram)
PAUSE = (3, 7)            # secondes entre deux envois
TEST = os.environ.get("TEST", "0") == "1"
TOK = os.environ["IG_TOKEN_CTA"].strip()

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def now(): return datetime.datetime.now(datetime.timezone.utc)
def date(s): return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                      data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000],
                            "disable_web_page_preview": True}, timeout=30)
    except Exception as e:
        log("Telegram KO", e)

def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper()

# ---------- Instagram ----------
USAGE = {"pct": 0}
def noter_usage(r):
    """Meta renvoie l'usage du quota de l'app (en %) dans l'en-tête x-app-usage."""
    try:
        u = json.loads(r.headers.get("x-app-usage", "{}"))
        USAGE["pct"] = max(u.get("call_count", 0), u.get("total_time", 0), u.get("total_cputime", 0))
    except Exception:
        pass

def get(path, **params):
    params["access_token"] = TOK
    r = requests.get(f"{IG}/{path}", params=params, timeout=60)
    noter_usage(r)
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
        noter_usage(r)
        if r.status_code != 200:
            break
        data = r.json()
    return out

def post(path, **payload):
    r = requests.post(f"{IG}/{path}", json=payload, headers={"Authorization": f"Bearer {TOK}"}, timeout=60)
    noter_usage(r)
    if r.status_code != 200:
        raise RuntimeError(f"POST {path} -> {r.status_code} {r.text[:300]}")
    return r.json()

# ---------- Dropbox (état) ----------
_dbx = {"tok": None, "t": 0}
def dbx_tok():
    if not _dbx["tok"] or time.time() - _dbx["t"] > 3 * 3600:
        r = requests.post("https://api.dropboxapi.com/oauth2/token",
                          data={"grant_type": "refresh_token", "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"].strip()},
                          auth=(os.environ["DROPBOX_APP_KEY"].strip(), os.environ["DROPBOX_APP_SECRET"].strip()), timeout=30)
        r.raise_for_status()
        _dbx.update(tok=r.json()["access_token"], t=time.time())
    return _dbx["tok"]

def charger_etat():
    r = requests.post("https://content.dropboxapi.com/2/files/download",
                      headers={"Authorization": f"Bearer {dbx_tok()}",
                               "Dropbox-API-Arg": json.dumps({"path": ETAT_DROPBOX})}, timeout=60)
    if r.status_code == 409:
        return {}
    r.raise_for_status()
    return r.json()

def sauver_etat(state):
    if TEST:
        return
    try:
        r = requests.post("https://content.dropboxapi.com/2/files/upload",
                          headers={"Authorization": f"Bearer {dbx_tok()}", "Content-Type": "application/octet-stream",
                                   "Dropbox-API-Arg": json.dumps({"path": ETAT_DROPBOX, "mode": "overwrite", "mute": True})},
                          data=json.dumps(state, ensure_ascii=False).encode(), timeout=60)
        r.raise_for_status()
    except Exception as e:
        log("Sauvegarde état KO", e)

# ---------- Logique ----------
RE_MOT = re.compile(r'comment\w*\s*(?:le mot\s*)?["“«]\s*([^"”»]+?)\s*["”»]', re.I)

def mot_cle(caption):
    m = RE_MOT.search(caption or "")
    return m.group(1).strip() if m else None

def contient(texte, mot):
    return re.search(r"(?<![A-Z0-9])" + re.escape(norm(mot)) + r"S?(?![A-Z0-9])", norm(texte)) is not None

def prenom(igsid, user):
    """Prénom affiché sur Instagram (ex. « Théo Galais » -> « Théo »), sinon le pseudo."""
    try:
        nom = get(str(igsid), fields="name").get("name", "").strip()
        if nom:
            return nom.split()[0]
    except Exception as e:
        log("Nom introuvable", user, str(e)[:120])
    return user

class Robot:
    def __init__(self):
        cfg = json.load(open(CONFIG_FILE, encoding="utf-8"))
        self.reponses = cfg.pop("_reponses_publiques", ["Regarde tes DM 📩"])
        self.ctas = {norm(k): (k, v) for k, v in cfg.items()}
        self.state = charger_etat()
        self.traites = set(self.state.get("traites", []))
        self.personnes = set(self.state.get("personnes", []))
        self.attente = self.state.get("attente", {})
        self.echecs = set(self.state.get("echecs", []))   # commentaires où le DM était impossible
        self.convs = {}            # pseudo -> {"id", "miens": [...], "leurs": [(date, texte)]}
        self.nb_comments = {}      # post -> nombre de commentaires déjà traités
        self.envois = []           # horodatages des questions (limite par minute)
        self.sans_lien = set()
        self.compte = {"questions": [], "guides": [], "echecs": []}
        self.change = False

    def lire_dm(self, pages):
        try:
            data = get_all(f"{IG_ID}/conversations", limit_pages=pages, platform="instagram",
                           limit=25,
                           fields="participants,messages.limit(15){from,message,created_time}")
        except Exception as e:
            log("Lecture DM KO", e); return
        for c in data:
            autres = [p for p in c.get("participants", {}).get("data", []) if str(p.get("id")) != IG_ID]
            msgs = c.get("messages", {}).get("data", [])
            for p in autres:
                user = p.get("username", "").lower()
                d = {"id": p.get("id"), "miens": [], "leurs": []}
                for m in msgs:
                    if str(m.get("from", {}).get("id")) == IG_ID:
                        d["miens"].append(m.get("message", ""))
                    else:
                        d["leurs"].append((m.get("created_time", ""), m.get("message", "")))
                ancien = self.convs.get(user)
                if ancien:   # on garde aussi les messages déjà lus
                    d["miens"] = list(dict.fromkeys(d["miens"] + ancien["miens"]))
                    d["leurs"] = list(dict.fromkeys(d["leurs"] + ancien["leurs"]))
                self.convs[user] = d

    def envoyer_guides(self):
        for qui, info in list(self.attente.items()):
            user, cle = qui.split("|", 1)
            if cle not in self.ctas:
                self.attente.pop(qui); self.change = True; continue
            _, cfg = self.ctas[cle]
            conv, t0 = self.convs.get(user), date(info["t"])
            if conv and any(cfg["lien"][:40] in t for t in conv["miens"]):
                self.attente.pop(qui); self.change = True; continue   # tu lui as déjà envoyé le lien toi-même
            if conv and any(dt and date(dt) > t0 for dt, _ in conv["leurs"]):
                texte = cfg["message"].replace("{lien}", cfg["lien"])
                if TEST:
                    log("[test] guide pour", user); continue
                try:
                    post(f"{IG_ID}/messages", recipient={"id": conv["id"]}, message={"text": texte})
                    if cfg.get("relance"):
                        time.sleep(random.uniform(2, 3))   # 2e message séparé, pour qu'il le voie bien
                        post(f"{IG_ID}/messages", recipient={"id": conv["id"]},
                             message={"text": cfg["relance"].replace("{prenom}", prenom(conv["id"], user))})
                    self.attente.pop(qui); self.change = True
                    self.compte["guides"].append("@" + user)
                    log("Guide envoyé à", user)
                    time.sleep(random.uniform(*PAUSE))
                except Exception as e:
                    log("Guide KO", user, str(e)[:200])
                    if '"code":4,' in str(e):
                        return   # quota atteint : on réessaiera plus tard
            elif (now() - t0).days >= 7:
                self.attente.pop(qui); self.change = True

    def peut_envoyer(self):
        t = time.time()
        self.envois = [x for x in self.envois if t - x < 60]
        return len(self.envois) < MAX_PAR_MINUTE

    def traiter_commentaires(self, media, nom_cta, cfg):
        """Renvoie True si tous les commentaires du post ont été traités."""
        cle = norm(nom_cta)
        comments = get_all(f"{media['id']}/comments", limit_pages=20, limit=50,
                           fields="id,text,timestamp,username,from,replies{username,from}")
        complet = True
        for c in comments:
            cid = c["id"]
            user = (c.get("username") or c.get("from", {}).get("username", "")).lower()
            if user == MOI or str(c.get("from", {}).get("id")) == IG_ID:
                continue
            if not contient(c.get("text", ""), nom_cta):
                continue
            qui = f"{user}|{cle}"
            if cid in self.traites and (qui in self.personnes or cid in self.echecs):
                continue
            reps = c.get("replies", {}).get("data", [])
            deja_public = any((r.get("username") or r.get("from", {}).get("username", "")).lower() == MOI
                              for r in reps)
            deja_dm = any(any(norm(t) in norm(txt) for t in cfg.get("deja_envoye_si", []))
                          for txt in self.convs.get(user, {}).get("miens", []))
            if deja_public or deja_dm or qui in self.personnes:
                miens = self.convs.get(user, {}).get("miens", [])
                question_sans_guide = (any(norm("Je te l'envoie") in norm(t) for t in miens)
                                       and not any(cfg["lien"][:40] in t for t in miens))
                if question_sans_guide and qui not in self.attente and (now() - date(c["timestamp"])).days < 7:
                    self.attente[qui] = {"t": c["timestamp"]}   # question déjà posée, on attend sa réponse
                self.traites.add(cid); self.personnes.add(qui); self.change = True; continue
            if (now() - date(c["timestamp"])).days >= 7:
                self.traites.add(cid); self.change = True; continue
            if not self.peut_envoyer() or USAGE["pct"] >= 60:
                complet = False; continue     # quota : on garde de la marge pour envoyer les guides en priorité
            if TEST:
                log("[test] question pour", user); self.personnes.add(qui)
                self.compte["questions"].append("@" + user); continue
            try:
                post(f"{IG_ID}/messages", recipient={"comment_id": cid}, message={"text": cfg["accroche"]})
                self.envois.append(time.time())
                self.traites.add(cid); self.personnes.add(qui)
                self.attente[qui] = {"t": now().strftime("%Y-%m-%dT%H:%M:%S%z")}
                self.change = True
                self.compte["questions"].append("@" + user)
                log("Question envoyée à", user)
                self.sauver()
                try:
                    post(f"{cid}/replies", message=random.choice(self.reponses))
                except Exception as e:
                    log("Réponse publique KO", user, e)
                time.sleep(random.uniform(*PAUSE))
            except Exception as e:
                err = str(e)
                if any(k in err for k in ('"code":4,', '"code":32,', '"code":613,', "rate limit", "Rate limit")):
                    log("Limite Instagram atteinte, pause", err[:200])
                    self.envois = [time.time()] * MAX_PAR_MINUTE   # on attend la minute suivante
                    complet = False; continue
                # DM impossible (compte qui bloque les messages, etc.) -> on lui dit de nous écrire
                log("DM impossible pour", user, err[:200])
                self.traites.add(cid); self.echecs.add(cid); self.personnes.add(qui)
                self.attente[qui] = {"t": now().strftime("%Y-%m-%dT%H:%M:%S%z"), "mode": "dm"}
                self.change = True
                self.compte["echecs"].append("@" + user)
                try:
                    post(f"{cid}/replies", message=cfg.get("dm_impossible",
                         "J'arrive pas à t'envoyer le guide en DM 😕 Écris-moi en DM et je te l'envoie direct !"))
                except Exception as e2:
                    log("Réponse publique KO", user, e2)
                time.sleep(random.uniform(*PAUSE))
        return complet

    def tour(self, pages_dm=1, commentaires=True):
        self.lire_dm(pages_dm)
        self.envoyer_guides()
        if not commentaires:
            self.sauver(); return
        medias = get(f"{IG_ID}/media", fields="id,caption,timestamp,comments_count", limit=50).get("data", [])
        for m in medias:
            if (now() - date(m["timestamp"])).days > JOURS_POSTS:
                continue
            mot = mot_cle(m.get("caption"))
            if not mot:
                continue
            if norm(mot) not in self.ctas or not self.ctas[norm(mot)][1].get("lien"):
                self.sans_lien.add(mot); continue
            nb = m.get("comments_count", 0)
            if self.nb_comments.get(m["id"]) == nb:
                continue                     # rien de nouveau sur ce post
            nom_cta, cfg = self.ctas[norm(mot)]
            if self.traiter_commentaires(m, nom_cta, cfg):
                self.nb_comments[m["id"]] = nb
        self.sauver()

    def sauver(self):
        if self.change:
            self.state.update(traites=sorted(self.traites)[-5000:], personnes=sorted(self.personnes),
                              attente=self.attente, echecs=sorted(self.echecs)[-5000:])
            sauver_etat(self.state); self.change = False

    def recap(self, titre):
        q, g, x = self.compte["questions"], self.compte["guides"], self.compte["echecs"]
        if not (q or g or x):
            return
        msg = (f"{titre}\n💬 questions envoyées : {len(q)}\n📩 guides envoyés : {len(g)}\n"
               f"🚫 DM impossible (invités à t'écrire) : {len(x)}\n"
               f"⏳ en attente de réponse : {len(self.attente)}")
        if x: msg += "\n\nDM impossible : " + ", ".join(x[:50])
        if g: msg += "\n\nGuide envoyé à : " + ", ".join(g[:50])
        if q: msg += "\n\nQuestion envoyée à : " + ", ".join(q[:50])
        tg(msg)
        self.compte = {"questions": [], "guides": [], "echecs": []}

QUESTION = "Salut {prenom}, dis-moi, t'as un business ou t'explores juste ?"

def relancer_sans_question(r):
    """Une seule fois : ceux à qui tu as envoyé le guide (à la main ou par le robot) sans leur poser la question.
    Instagram n'autorise un message que si la personne t'a écrit dans les dernières 24 h."""
    r.lire_dm(30)
    deja = set(r.state.get("relance_faite", []))
    liens = [v["lien"][:40] for _, v in r.ctas.values() if v.get("lien")]
    a_faire, hors_delai = [], []
    for user, conv in r.convs.items():
        if not user or user in deja:
            continue
        miens = conv["miens"]
        a_eu_guide = any(any(l in m for l in liens) or "guide" in m.lower() for m in miens)
        a_eu_question = any(any(k in m.lower() for k in ("un business ou", "explores", "te lancer", "aimerais te lancer")) for m in miens)
        if not a_eu_guide or a_eu_question:
            continue
        dates = [date(dt) for dt, _ in conv["leurs"] if dt]
        if dates and (now() - max(dates)).total_seconds() < 23 * 3600:
            a_faire.append(user)
        else:
            hors_delai.append(user)
    nb_guide = sum(1 for c in r.convs.values() if any(any(l in m for l in liens) or "guide" in m.lower() for m in c["miens"]))
    nb_q = sum(1 for c in r.convs.values() if any(any(k in m.lower() for k in ("un business ou", "explores", "te lancer")) for m in c["miens"]))
    log(f"Stats : {len(r.convs)} conversations lues, {nb_guide} avec guide, {nb_q} avec question")
    import collections
    cnt = collections.Counter()
    for c in r.convs.values():
        for m in c["miens"]:
            ml = m.lower()
            if any(k in ml for k in ("un business ou", "explores", "te lancer")):
                cnt[m[:70]] += 1
    for k, v in cnt.most_common(8):
        log("QMSG", v, "|", k.replace("\n", " "))
    log(f"Relance : {len(a_faire)} possibles, {len(hors_delai)} hors délai (pas écrit depuis +24 h)")
    log("A_FAIRE :", ", ".join(a_faire))
    log("HORS_DELAI :", ", ".join(hors_delai))
    envoyes = []
    if not TEST:
        for user in a_faire:
            try:
                post(f"{IG_ID}/messages", recipient={"id": r.convs[user]["id"]},
                     message={"text": QUESTION.replace("{prenom}", prenom(r.convs[user]["id"], user))})
                envoyes.append("@" + user); deja.add(user)
                log("Question envoyée à", user)
                time.sleep(random.uniform(4, 9))
            except Exception as e:
                log("KO", user, str(e)[:200])
                if '"code":4,' in str(e):
                    time.sleep(300)
        r.state["relance_faite"] = sorted(deja); sauver_etat(r.state)
    tg(("🧪 TEST " if TEST else "🤖 ") + f"Relance « business ou t'explores » : {len(envoyes) if not TEST else len(a_faire)} "
       + ("à envoyer" if TEST else "envoyées") + f", {len(hors_delai)} impossibles (pas de message de leur part depuis +24 h)"
       + ("\n\n" + ", ".join(envoyes or ['@'+u for u in a_faire]) if (envoyes or a_faire) else ""))

def main():
    try:
        get(IG_ID, fields="id,username")
    except RuntimeError as e:
        if "190" in str(e):
            tg("⚠️ Robot CTA : ta clé Instagram ne marche plus (expirée ?). "
               "Génère-en une nouvelle et remplace le secret IG_TOKEN_CTA.")
        raise
    r = Robot()
    if os.environ.get("RELANCE") == "1":
        relancer_sans_question(r)
        return
    if os.environ.get("RATTRAPAGE") == "1":
        # Mode « guides seulement » (ManyChat gère les commentaires) :
        # envoie le guide à ceux qui répondent à l'ancienne question, sans jamais poser de nouvelle question.
        debut, n, dernier_recap = time.time(), 0, time.time()
        while time.time() - debut < DUREE_MAX and r.attente:
            pct = USAGE["pct"]
            try:
                r.tour(pages_dm=4 if n % 10 == 0 else 1, commentaires=False)
            except Exception as e:
                log("Tour KO", str(e)[:200]); time.sleep(240)
            n += 1
            log(f"Guides envoyés : {len(r.compte['guides'])} | en attente : {len(r.attente)} | quota {USAGE['pct']} %")
            if time.time() - dernier_recap > 3600:
                r.recap("🤖 Robot CTA (guides)"); dernier_recap = time.time()
            time.sleep(30 if pct < 50 else 90 if pct < 80 else 300)
        r.recap("🤖 Robot CTA (guides)")
        return
    if TEST:
        r.tour(pages_dm=10)
        log("Questions :", ", ".join(r.compte["questions"]) or "aucune")
        r.recap("🧪 Robot CTA (TEST, rien envoyé)")
        return
    r.tour(pages_dm=10)          # premier tour : lit tout l'historique des DM
    if r.sans_lien and r.state.get("alerte_sans_lien") != sorted(r.sans_lien):
        r.state["alerte_sans_lien"] = sorted(r.sans_lien); sauver_etat(r.state)
        tg("⚠️ Robot CTA : mots-clés sans lien dans cta.json : " + ", ".join(sorted(r.sans_lien)))
    debut, dernier_recap, dernier_media, dernier_scan = time.time(), time.time(), time.time(), time.time()
    while time.time() - debut < DUREE_MAX:
        # Quota Meta (app en mode développement ≈ 200 appels/heure) : on ralentit quand il se remplit
        pct = USAGE["pct"]
        attente_s = 20 if pct < 40 else 45 if pct < 70 else 120 if pct < 90 else 300
        time.sleep(attente_s)
        try:
            voir_comments = time.time() - dernier_media >= (60 if pct < 40 else 180)
            scan = time.time() - dernier_scan >= 600     # toutes les 10 min : relit 100 conversations
            if scan:
                dernier_scan = time.time()
            r.tour(pages_dm=4 if scan else 1, commentaires=voir_comments and pct < 60)
            if voir_comments:
                dernier_media = time.time()
            log(f"quota utilisé : {USAGE['pct']} %")
        except Exception as e:
            log("Tour KO", str(e)[:200])
            if '"code":190' in str(e):
                tg("⚠️ Robot CTA : ta clé Instagram ne marche plus. Remplace le secret IG_TOKEN_CTA."); raise
            time.sleep(300 if '"code":4,' in str(e) else 60)
        if time.time() - dernier_recap > 3600:
            r.recap("🤖 Robot CTA (dernière heure)"); dernier_recap = time.time()
    r.recap("🤖 Robot CTA")

if __name__ == "__main__":
    main()
