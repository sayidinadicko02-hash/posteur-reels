import os, requests
T=os.environ["IG_TOKEN_CTA"].strip()
print("Jeton", len(T), repr(T[:3]))
for base in ["https://graph.instagram.com/v26.0","https://graph.facebook.com/v26.0"]:
    for path,f in [("me","id,username,user_id,name"),("17841415914105749","id,username"),("me/accounts","id,name,instagram_business_account")]:
        r=requests.get(f"{base}/{path}",params={"fields":f,"access_token":T},timeout=30)
        print(base.split('/')[2],path,r.status_code,r.text[:250])
r=requests.get("https://graph.facebook.com/debug_token",params={"input_token":T,"access_token":T},timeout=30)
print("debug",r.status_code,r.text[:600])
