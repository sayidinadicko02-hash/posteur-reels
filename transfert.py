"""
Transfert GitHub -> Dropbox
Quand Claude pousse des vidéos sur la branche "inbox" (dossier a_poster/),
ce script les copie dans le dossier Dropbox /A_POSTER.
Le workflow supprime ensuite la branche inbox pour ne rien garder dans GitHub.
"""
import os, glob, json
import requests

SOURCE = "a_poster"
DEST = "/A_POSTER"

def dbx_token():
    r = requests.post("https://api.dropboxapi.com/oauth2/token",
                      data={"grant_type": "refresh_token", "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"].strip()},
                      auth=(os.environ["DROPBOX_APP_KEY"].strip(), os.environ["DROPBOX_APP_SECRET"].strip()), timeout=30)
    if not r.ok:
        raise RuntimeError(f"Dropbox refuse la connexion ({r.status_code}) : {r.text[:300]}")
    return r.json()["access_token"]

def upload(tok, local, remote):
    with open(local, "rb") as fh:
        r = requests.post("https://content.dropboxapi.com/2/files/upload",
                          headers={"Authorization": f"Bearer {tok}",
                                   "Content-Type": "application/octet-stream",
                                   "Dropbox-API-Arg": json.dumps({"path": remote, "mode": "overwrite", "mute": True})},
                          data=fh, timeout=600)
    if not r.ok:
        raise RuntimeError(f"Envoi de {local} refusé ({r.status_code}) : {r.text[:300]}")

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                      data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text}, timeout=30)
    except Exception as e:
        print("Telegram KO", e)

def main():
    files = sorted(f for f in glob.glob(f"{SOURCE}/*") if os.path.isfile(f))
    if not files:
        print("Aucun fichier à transférer."); return
    tok = dbx_token()
    for f in files:
        name = os.path.basename(f)
        print("Envoi :", name, flush=True)
        upload(tok, f, f"{DEST}/{name}")
    videos = [f for f in files if f.lower().endswith((".mp4", ".mov"))]
    tg(f"📥 {len(videos)} vidéo(s) déposée(s) dans Dropbox / A_POSTER. Publication automatique toutes les 30 min.")

if __name__ == "__main__":
    main()
