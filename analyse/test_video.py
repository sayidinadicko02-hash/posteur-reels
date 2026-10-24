import os, json, requests, sys
sys.argv=['x']; os.environ['SANS_DUREE']='1'
import importlib.util
key=os.environ["GEMINI_API_KEY"].strip()
d=json.load(open("data.json")); m=d["medias"][-1]
open("/tmp/t.mp4","wb").write(requests.get(m["media_url"],timeout=120).content)
print("::notice::taille", os.path.getsize("/tmp/t.mp4"))
size=os.path.getsize("/tmp/t.mp4")
r=requests.post("https://generativelanguage.googleapis.com/upload/v1beta/files",params={"key":key},headers={"X-Goog-Upload-Protocol":"resumable","X-Goog-Upload-Command":"start","X-Goog-Upload-Header-Content-Length":str(size),"X-Goog-Upload-Header-Content-Type":"video/mp4","Content-Type":"application/json"},json={"file":{"display_name":"t"}})
print("::notice::start", r.status_code, r.text[:200].replace("\n"," "))
up=r.headers.get("X-Goog-Upload-URL")
f=requests.post(up,data=open("/tmp/t.mp4","rb").read(),headers={"Content-Length":str(size),"X-Goog-Upload-Offset":"0","X-Goog-Upload-Command":"upload, finalize"})
print("::notice::upload", f.status_code, f.text[:400].replace("\n"," "))
import time
fi=f.json()["file"]
for _ in range(30):
    if fi.get("state")=="ACTIVE": break
    time.sleep(5); fi=requests.get(f"https://generativelanguage.googleapis.com/v1beta/{fi['name']}",params={"key":key}).json()
print("::notice::state", fi.get("state"), fi.get("uri"))
for mod in ["gemini-2.5-flash","gemini-flash-latest"]:
    g=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent",params={"key":key},json={"contents":[{"parts":[{"file_data":{"mime_type":"video/mp4","file_uri":fi["uri"]}},{"text":"Décris le hook en une phrase."}]}]})
    print(f"::notice::{mod} {g.status_code} {g.text[:500]}".replace("\n"," "))
