"""Pour CHAQUE réel : son complet (mp3 mono) + 7 images clés + durée -> videos/ (chiffré ensuite)."""
import json, os, subprocess, requests
d = json.load(open("data.json")); M = [m for m in d["medias"] if m.get("media_url")]
os.makedirs("videos", exist_ok=True); meta = []
for m in M:
    try:
        open("/tmp/x.mp4", "wb").write(requests.get(m["media_url"], timeout=120).content)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "/tmp/x.mp4"], capture_output=True, text=True).stdout.strip() or 0)
        b = f"videos/{m['id']}"
        os.system(f"ffmpeg -v error -y -i /tmp/x.mp4 -vn -ac 1 -ar 16000 -b:a 32k {b}.mp3")
        ts = [0.2, 1.5, 3, 5, 8, dur * 0.5, max(0, dur - 3)]
        for k, t in enumerate(ts):
            os.system(f"ffmpeg -v error -y -ss {t:.2f} -i /tmp/x.mp4 -frames:v 1 -vf scale=270:-2 -q:v 5 {b}_{k}.jpg")
        meta.append({"id": m["id"], "date": m["timestamp"], "duree": dur, "caption": m.get("caption"), "lien": m.get("permalink"), "insights": m["insights"]})
    except Exception as ex:
        print("::warning::", m["id"], ex)
json.dump(meta, open("videos/meta.json", "w"), ensure_ascii=False)
print(f"::notice::{len(meta)} réels extraits")
