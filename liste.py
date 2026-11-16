import os, requests
tok = requests.post("https://api.dropboxapi.com/oauth2/token",
    data={"grant_type": "refresh_token", "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"].strip()},
    auth=(os.environ["DROPBOX_APP_KEY"].strip(), os.environ["DROPBOX_APP_SECRET"].strip()), timeout=30).json()["access_token"]
for dossier in ("/A_POSTER",):
    r = requests.post("https://api.dropboxapi.com/2/files/list_folder",
        headers={"Authorization": f"Bearer {tok}"}, json={"path": dossier}, timeout=30).json()
    entries = r.get("entries", [])
    print(f"LISTE {dossier} : {len(entries)} fichier(s)")
    for e in sorted(entries, key=lambda x: x["name"]):
        print("LISTE", e["name"], e.get("size", ""))
