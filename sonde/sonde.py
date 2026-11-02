import requests, os
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9"}
os.makedirs("sonde/out",exist_ok=True)
r=requests.get("https://www.hellowork.com/fr-fr/emplois/82538756.html",headers=UA,timeout=30)
open("sonde/out/hw_detail.html","w").write(r.text); print(r.status_code,len(r.text))
r=requests.get("https://www.hellowork.com/fr-fr/emploi/recherche.html",params={"k":"FPGA","c":"Alternance","p":2},headers=UA,timeout=30)
open("sonde/out/hw_alt_p2.html","w").write(r.text); print(r.status_code,len(r.text))
