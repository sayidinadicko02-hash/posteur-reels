import requests, os, re
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9"}
os.makedirs("sonde/out",exist_ok=True)
sc="DPwIYReAYR7"; out=[]
for n,u in [("embed","https://www.instagram.com/reel/%s/embed/captioned/"%sc),("page","https://www.instagram.com/reel/%s/"%sc)]:
    t=requests.get(u,headers=UA,timeout=30).text; out.append(f"== {n} {len(t)}")
    for k in ["username","owner","video_view_count","video_play_count","play_count","view_count","comment_count","edge_media_to_comment","edge_followed_by","follower_count","og:description","og:title","EmbeddedMedia","Caption","commentCount","likeCount","UserInteractionCount"]:
        for m in list(re.finditer(re.escape(k),t))[:3]:
            out.append(f"{n} {k}: {t[max(0,m.start()-80):m.start()+220]!r}")
open("sonde/out/ig_extrait.txt","w").write("\n".join(out))
