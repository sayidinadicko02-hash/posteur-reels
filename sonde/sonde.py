import requests, os
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9"}
os.makedirs("sonde/out",exist_ok=True)
sc="DPwIYReAYR7"
for n,u,h in [("embed","https://www.instagram.com/reel/%s/embed/captioned/"%sc,UA),
              ("page","https://www.instagram.com/reel/%s/"%sc,UA),
              ("api","https://www.instagram.com/api/v1/media/shortcode/%s/"%sc,{**UA,"X-IG-App-ID":"936619743392459"})]:
    try:
        r=requests.get(u,headers=h,timeout=30); open(f"sonde/out/ig_{n}.txt","w").write(f"{r.status_code}\n{r.text[:300000]}"); print(n,r.status_code,len(r.text))
    except Exception as e: print(n,e)
