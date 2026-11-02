import requests, json, os
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9"}
os.makedirs("sonde/out",exist_ok=True)
def save(n,r):
    open(f"sonde/out/{n}","w").write(f"{r.status_code} {r.url}\n{dict(r.headers)}\n\n{r.text[:400000]}")
    print(n,r.status_code,len(r.text))
r=requests.get("https://www.hellowork.com/fr-fr/emploi/recherche.html",params={"k":"stage FPGA","c":"Stage"},headers=UA,timeout=30); save("hw_search.html",r)
r=requests.get("https://www.apec.fr/candidat/recherche-emploi.html/emploi",params={"motsCles":"stage FPGA"},headers=UA,timeout=30); save("apec_page.html",r)
body={"lieux":[],"fonctions":[],"statutPoste":[],"typesContrat":[],"typesConvention":[],"niveauxExperience":[],"idsEtablissement":[],"secteursActivite":[],"typesTeletravail":[],"idNomZonesDeplacement":[],"positionNumbersExcluded":[],"typeClient":"CADRE","sorts":[{"type":"DATE","direction":"DESCENDING"}],"pagination":{"range":20,"startIndex":0},"activeFiltre":True,"pointGeolocDeReference":{"distance":0},"motsCles":"stage FPGA"}
r=requests.post("https://www.apec.fr/cms/webservices/rechercheOffre",json=body,headers={**UA,"Content-Type":"application/json"},timeout=30); save("apec_api.json",r)
