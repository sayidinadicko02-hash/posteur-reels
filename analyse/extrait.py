"""Télécharge les 12 meilleurs et 12 pires réels (pour analyse), dans videos/."""
import json, os, requests
d = json.load(open("data.json")); M = [m for m in d["medias"] if m.get("media_url")]
M.sort(key=lambda m: -(m["insights"].get("views") or 0))
os.makedirs("videos", exist_ok=True); meta = []
for tag, lst in (("top", M[:12]), ("flop", M[-12:])):
    for k, m in enumerate(lst, 1):
        p = f"videos/{tag}{k:02d}_{m['id']}.mp4"
        open(p, "wb").write(requests.get(m["media_url"], timeout=120).content)
        meta.append({"fichier": p, "id": m["id"], "date": m["timestamp"], "vues": m["insights"].get("views"), "watch": m["insights"].get("ig_reels_avg_watch_time"), "lien": m.get("permalink")})
json.dump(meta, open("videos/meta.json", "w"), ensure_ascii=False, indent=1)
print(f"::notice::{len(meta)} vidéos")
