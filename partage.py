"""
Partage public Dropbox
Quand Claude pousse des fichiers sur la branche "partage" (dossier partage/),
ce script les copie dans le dossier Dropbox /KITS et crée un lien public pour chacun.
Les liens sont affichés dans le journal GitHub et envoyés sur Telegram.
"""
import os, glob, json
import requests
from transfert import dbx_token, upload, tg

SOURCE = "partage"
DEST = "/KITS"

def lien_public(tok, chemin):
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    r = requests.post("https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings", headers=h,
                      data=json.dumps({"path": chemin, "settings": {"requested_visibility": "public", "audience": "public", "access": "viewer"}}), timeout=30)
    if r.ok:
        return r.json()["url"]
    if "shared_link_already_exists" in r.text:
        r2 = requests.post("https://api.dropboxapi.com/2/sharing/list_shared_links", headers=h,
                           data=json.dumps({"path": chemin, "direct_only": True}), timeout=30)
        r2.raise_for_status()
        return r2.json()["links"][0]["url"]
    raise RuntimeError(f"Lien refusé pour {chemin} ({r.status_code}) : {r.text[:300]}")

def main():
    files = sorted(f for f in glob.glob(f"{SOURCE}/*") if os.path.isfile(f))
    if not files:
        print("Aucun fichier à partager."); return
    tok = dbx_token()
    lignes = []
    for f in files:
        dest = f"{DEST}/{os.path.basename(f)}"
        upload(tok, f, dest)
        url = lien_public(tok, dest)
        print(f"LIEN {os.path.basename(f)} {url}", flush=True)
        lignes.append(f"{os.path.basename(f)} : {url}")
    tg("🔗 Fichiers partagés (lien public) :\n" + "\n".join(lignes))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::{e}", flush=True)
        tg(f"❌ partage.py : {e}"[:3500])
        raise
