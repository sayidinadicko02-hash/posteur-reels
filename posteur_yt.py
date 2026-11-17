"""
Posteur YouTube Shorts (compte GTA 6) : Dropbox -> YouTube
Lit les vidéos déjà rangées dans /GTA6/PUBLIES (donc déjà passées sur Instagram),
les publie en Shorts sur la chaîne YouTube liée au jeton, une toutes les ECART_HEURES heures,
et note ce qui est fait dans state_yt.json (rien n'est déplacé ni supprimé dans Dropbox).

Secrets : DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN,
          YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os, re, json, datetime
import requests

DOSSIER = "/GTA6/PUBLIES"
ECART_HEURES = 4          # quota gratuit YouTube : ~6 envois par jour
EXTENSIONS = (".mp4", ".mov")
STATE_FILE = "state_yt.json"

def log(*a): print(*a, flush=True)

def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                      data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000], "disable_web_page_preview": True}, timeout=30)
    except Exception as e:
        log("Telegram KO", e)

def dbx_token():
    r = requests.post("https://api.dropboxapi.com/oauth2/token",
                      data={"grant_type": "refresh_token", "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"].strip()},
                      auth=(os.environ["DROPBOX_APP_KEY"].strip(), os.environ["DROPBOX_APP_SECRET"].strip()), timeout=30)
    r.raise_for_status(); return r.json()["access_token"]

def dbx_list(tok):
    r = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers={"Authorization": f"Bearer {tok}"},
                      json={"path": DOSSIER}, timeout=60)
    if r.status_code == 409: return []
    r.raise_for_status(); j = r.json(); items = j["entries"]
    while j.get("has_more"):
        j = requests.post("https://api.dropboxapi.com/2/files/list_folder/continue", headers={"Authorization": f"Bearer {tok}"},
                          json={"cursor": j["cursor"]}, timeout=60).json(); items += j["entries"]
    return [e for e in items if e[".tag"] == "file"]

def dbx_download(tok, path):
    r = requests.post("https://content.dropboxapi.com/2/files/download",
                      headers={"Authorization": f"Bearer {tok}", "Dropbox-API-Arg": json.dumps({"path": path})}, timeout=600)
    r.raise_for_status(); return r.content

def yt_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"].strip(), "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(), "grant_type": "refresh_token"}, timeout=30)
    if not r.ok: raise RuntimeError(f"Google refuse la connexion ({r.status_code}) : {r.text[:300]}")
    return r.json()["access_token"]

def yt_upload(tok, data, titre, description):
    meta = {"snippet": {"title": titre[:100], "description": description[:4900], "categoryId": "20"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                               "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(data))},
                      json=meta, timeout=60)
    if not r.ok: raise RuntimeError(f"YouTube {r.status_code} : {r.text[:400]}")
    up = requests.put(r.headers["Location"], data=data, headers={"Content-Type": "video/mp4"}, timeout=1200)
    if not up.ok: raise RuntimeError(f"YouTube envoi {up.status_code} : {up.text[:400]}")
    return up.json()["id"]

def main():
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    done = state.setdefault("done", [])
    now = datetime.datetime.now(datetime.timezone.utc)
    last = state.get("last_post")
    if last and os.environ.get("FORCE_RUN") != "1":
        h = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 3600
        if h < ECART_HEURES - 0.2:
            log(f"Dernier envoi il y a {h:.1f} h, on attend."); return
    tok = dbx_token()
    fichiers = dbx_list(tok)
    videos = sorted([f for f in fichiers if f["name"].lower().endswith(EXTENSIONS) and f["name"] not in done], key=lambda f: f["name"].lower())
    if not videos:
        log("Rien à publier sur YouTube."); return
    v = videos[0]
    txt = next((f for f in fichiers if f["name"].lower() == os.path.splitext(v["name"])[0].lower() + ".txt"), None)
    desc = dbx_download(tok, txt["path_display"]).decode("utf-8-sig").strip() if txt else ""
    titre = re.sub(r"#\w+", "", desc).strip(" 🎮") or "GTA 6"
    description = (desc + "\n#Shorts").strip()
    try:
        vid = yt_upload(yt_token(), dbx_download(tok, v["path_display"]), titre + " #Shorts", description)
    except Exception as e:
        tg(f"❌ YouTube : {v['name']} n'a pas pu être publié.\n{e}"); raise
    done.append(v["name"]); state["last_post"] = now.isoformat()
    json.dump(state, open(STATE_FILE, "w"))
    tg(f"✅ {v['name']} publié sur YouTube.\nhttps://youtube.com/shorts/{vid}\nRestant : {len(videos)-1}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::{e}", flush=True); raise
