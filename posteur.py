"""
Posteur de Reels : Dropbox -> Instagram (+ notification Telegram)
Tourne sur GitHub Actions toutes les 10 minutes.
Dépose tes hooks + description.txt dans le dossier Dropbox /A_POSTER :
le script publie une vidéo toutes les 30 minutes, puis la SUPPRIME de Dropbox
(pour ne pas saturer ton espace). En cas d'échec, la vidéo est gardée dans /ERREURS.

Secrets requis : DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN,
                 IG_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Secret optionnel : GH_PAT (pour renouveler tout seul le jeton Instagram)
"""
import os, json, time, datetime, subprocess
import requests

# ---------------- RÉGLAGES ----------------
DOSSIER_A_POSTER = "/A_POSTER"
DOSSIER_ERREURS = "/ERREURS"
ECART_MINUTES = 30            # temps entre deux publications
IG_VERSION = "v26.0"
EXTENSIONS = (".mp4", ".mov")
# ------------------------------------------

STATE_FILE = "state.json"
IG = f"https://graph.instagram.com/{IG_VERSION}"
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]

def log(*a): print(*a, flush=True)

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": text[:4000], "disable_web_page_preview": True}, timeout=30)
    except Exception as e:
        log("Telegram KO", e)

# ---------- Dropbox ----------
def dbx_token():
    r = requests.post("https://api.dropboxapi.com/oauth2/token",
                      data={"grant_type": "refresh_token", "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"]},
                      auth=(os.environ["DROPBOX_APP_KEY"], os.environ["DROPBOX_APP_SECRET"]), timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def dbx(tok, route, payload):
    r = requests.post(f"https://api.dropboxapi.com/2/{route}", headers={"Authorization": f"Bearer {tok}"},
                      json=payload, timeout=60)
    if r.status_code == 409:   # dossier/fichier introuvable
        return None
    r.raise_for_status()
    return r.json()

def dbx_list(tok, path):
    res = dbx(tok, "files/list_folder", {"path": path})
    if res is None: return []
    items = res["entries"]
    while res.get("has_more"):
        res = dbx(tok, "files/list_folder/continue", {"cursor": res["cursor"]})
        items += res["entries"]
    return [e for e in items if e[".tag"] == "file"]

def dbx_read_text(tok, path):
    r = requests.post("https://content.dropboxapi.com/2/files/download",
                      headers={"Authorization": f"Bearer {tok}", "Dropbox-API-Arg": json.dumps({"path": path})}, timeout=60)
    r.raise_for_status()
    return r.content.decode("utf-8-sig").strip()

def dbx_move(tok, src, dest_dir):
    dbx(tok, "files/move_v2", {"from_path": src, "to_path": f"{dest_dir}/{os.path.basename(src)}", "autorename": True})

def dbx_delete(tok, path):
    dbx(tok, "files/delete_v2", {"path": path})

def dbx_mkdir(tok, path):
    dbx(tok, "files/create_folder_v2", {"path": path, "autorename": False})

# ---------- Instagram ----------
def ig_get(path, tok, **params):
    r = requests.get(f"{IG}/{path}", params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    if not r.ok: raise RuntimeError(f"Instagram {r.status_code} : {r.text[:400]}")
    return r.json()

def ig_post(path, tok, payload):
    r = requests.post(f"{IG}/{path}", json=payload, headers={"Authorization": f"Bearer {tok}"}, timeout=120)
    if not r.ok: raise RuntimeError(f"Instagram {r.status_code} : {r.text[:400]}")
    return r.json()

def publier_reel(tok, video_url, caption):
    ig_id = ig_get("me", tok, fields="user_id,username")
    uid = ig_id.get("user_id") or ig_id["id"]
    cont = ig_post(f"{uid}/media", tok, {"media_type": "REELS", "video_url": video_url,
                                         "caption": caption, "share_to_feed": True})["id"]
    log("Conteneur créé :", cont)
    for _ in range(40):                       # jusqu'à ~10 minutes de traitement
        time.sleep(15)
        st = ig_get(cont, tok, fields="status_code,status").get("status_code")
        log("Statut :", st)
        if st == "FINISHED": break
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram a refusé la vidéo ({st})")
    else:
        raise RuntimeError("Instagram n'a pas fini de traiter la vidéo en 10 minutes")
    media = ig_post(f"{uid}/media_publish", tok, {"creation_id": cont})["id"]
    try:
        return ig_get(media, tok, fields="permalink").get("permalink", "")
    except Exception:
        return ""

def renouveler_jeton(tok, state):
    """Renouvelle le jeton Instagram (valable 60 jours) une fois par semaine."""
    today = datetime.date.today().isoformat()
    last = state.get("last_refresh", "")
    if last and (datetime.date.today() - datetime.date.fromisoformat(last)).days < 7:
        return tok
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30)
        r.raise_for_status()
        new = r.json()["access_token"]
        state["last_refresh"] = today
        if os.environ.get("GH_PAT"):
            subprocess.run(["gh", "secret", "set", "IG_TOKEN", "--body", new],
                           env={**os.environ, "GH_TOKEN": os.environ["GH_PAT"]}, check=True)
            log("Jeton Instagram renouvelé et enregistré.")
        else:
            jours = r.json().get("expires_in", 0) // 86400
            if jours < 10:
                tg(f"⚠️ Posteur de Reels : ton jeton Instagram expire dans {jours} jours. Génère-en un nouveau et remplace le secret IG_TOKEN.")
        return new
    except Exception as e:
        log("Renouvellement du jeton KO :", e)
        return tok

def main():
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    now = datetime.datetime.now(datetime.timezone.utc)
    last = state.get("last_post")
    if last and os.environ.get("FORCE_RUN") != "1":
        ecoule = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 60
        if ecoule < ECART_MINUTES - 3:
            log(f"Dernière publication il y a {ecoule:.0f} min, on attend."); return

    tok_dbx = dbx_token()
    fichiers = dbx_list(tok_dbx, DOSSIER_A_POSTER)
    videos = sorted([f for f in fichiers if f["name"].lower().endswith(EXTENSIONS)], key=lambda f: f["name"].lower())
    if not videos:
        log("Rien à publier."); return

    v = videos[0]
    base = os.path.splitext(v["path_display"])[0]
    noms = {f["name"].lower(): f["path_display"] for f in fichiers}
    perso = noms.get(os.path.basename(base).lower() + ".txt")          # Hook01.txt = description perso (optionnel)
    desc_path = perso or noms.get("description.txt")
    caption = dbx_read_text(tok_dbx, desc_path) if desc_path else ""
    if not caption:
        tg("⚠️ Posteur de Reels : pas de description.txt dans A_POSTER, je publie sans description.")

    lien = dbx(tok_dbx, "files/get_temporary_link", {"path": v["path_display"]})["link"]
    ig_tok = renouveler_jeton(os.environ["IG_TOKEN"], state)
    try:
        url = publier_reel(ig_tok, lien, caption)
    except Exception as e:
        log("Échec :", e)
        dbx_mkdir(tok_dbx, DOSSIER_ERREURS); dbx_move(tok_dbx, v["path_display"], DOSSIER_ERREURS)
        tg(f"❌ {v['name']} n'a pas pu être publié (rangé dans ERREURS).\n{e}")
        state["last_post"] = now.isoformat(); json.dump(state, open(STATE_FILE, "w")); return

    dbx_delete(tok_dbx, v["path_display"])            # vidéo publiée -> supprimée de Dropbox
    if perso: dbx_delete(tok_dbx, perso)
    restants = len(videos) - 1
    if restants == 0 and desc_path and not perso:
        dbx_delete(tok_dbx, desc_path)                 # lot terminé : on supprime aussi la description
    state["last_post"] = now.isoformat()
    json.dump(state, open(STATE_FILE, "w"))
    tg(f"✅ {v['name']} publié sur Instagram.\n{url}\n" +
       (f"Encore {restants} vidéo(s), prochaine dans ~{ECART_MINUTES} min." if restants else "🎉 Lot terminé !"))

if __name__ == "__main__":
    main()
