import requests, json
H = {"x-ig-app-id": "936619743392459", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
for u in ["n8n.io", "instagram"]:
    r = requests.get("https://i.instagram.com/api/v1/users/web_profile_info/", params={"username": u}, headers=H, timeout=30)
    try:
        us = r.json()["data"]["user"]; ed = us["edge_owner_to_timeline_media"]["edges"]
        print(f"::notice::{u} OK {r.status_code} abonnés={us['edge_followed_by']['count']} posts={len(ed)} exemple_vues={[e['node'].get('video_view_count') for e in ed[:5]]}")
    except Exception as ex:
        print(f"::warning::{u} KO {r.status_code} {r.text[:150]}")
