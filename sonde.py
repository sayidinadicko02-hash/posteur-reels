import os, requests
T=os.environ["IG_TOKEN_CTA"].strip(); B="https://graph.facebook.com/v26.0"; IG="17841415914105749"
def g(p,**k):
    k["access_token"]=T; r=requests.get(f"{B}/{p}",params=k,timeout=30); print("S",p,r.status_code,r.text[:400]); return r.json()
g("me",fields="id,username,name")
m=g(f"{IG}/media",fields="id,caption,timestamp",limit=3)
for x in m.get("data",[])[:3]:
    g(f"{x['id']}/comments",fields="id,text,timestamp,username,from,replies{username,from}",limit=3)
g(f"{IG}/conversations",platform="instagram",fields="participants,messages.limit(2){from,message}",limit=2)
g("me/conversations",platform="instagram",fields="participants",limit=2)
