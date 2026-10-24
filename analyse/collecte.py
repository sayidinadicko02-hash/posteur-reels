"""Collecte toutes les stats Instagram du compte (réels + compte) -> analyse/data.json (chiffré ensuite par le workflow)."""
import os, json, time, requests
IG = "https://graph.instagram.com/v26.0"
TOK = os.environ["IG_TOKEN"].strip()
def get(path, **p):
    r = requests.get(f"{IG}/{path}", params=p, headers={"Authorization": f"Bearer {TOK}"}, timeout=60)
    return r.status_code, r.json()

out = {"erreurs": []}
c, me = get("me", fields="user_id,username,name,account_type,media_count,followers_count,follows_count,biography")
out["compte"] = me
print("me", c, {k: me.get(k) for k in ("username", "media_count", "followers_count")}, flush=True)
uid = me.get("user_id") or me.get("id")

# toutes les publications
medias, url, params = [], f"{uid}/media", dict(fields="id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count,media_url,thumbnail_url", limit=50)
while True:
    c, js = get(url, **params)
    if c != 200: out["erreurs"].append(["media", c, js]); break
    medias += js.get("data", [])
    nxt = js.get("paging", {}).get("cursors", {}).get("after")
    if not js.get("paging", {}).get("next") or not nxt: break
    params["after"] = nxt
print("medias", len(medias), flush=True)

METRIQUES = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
             "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "follows", "profile_visits"]
for m in medias:
    m["insights"] = {}
    for met in METRIQUES:           # une par une : si une métrique n'existe pas pour ce type, les autres passent quand même
        c, js = get(f"{m['id']}/insights", metric=met)
        if c == 200 and js.get("data"):
            d = js["data"][0]; v = d.get("values", [{}])[0].get("value", d.get("total_value", {}).get("value"))
            m["insights"][met] = v
        elif c != 200:
            m["insights"][met] = None
            if len(out["erreurs"]) < 40: out["erreurs"].append([m["id"], met, c, js.get("error", {}).get("message")])
    time.sleep(0.2)
out["medias"] = medias

# stats du compte sur 30 jours
for met, extra in [("reach", {"period": "day"}), ("follower_count", {"period": "day"}),
                   ("views", {"period": "day", "metric_type": "total_value"}),
                   ("profile_views", {"period": "day", "metric_type": "total_value"}),
                   ("follower_demographics", {"period": "lifetime", "metric_type": "total_value", "breakdown": "country"}),
                   ("engaged_audience_demographics", {"period": "lifetime", "metric_type": "total_value", "breakdown": "age", "timeframe": "this_month"})]:
    p = dict(metric=met, **extra)
    if extra.get("period") == "day":
        p["since"] = int(time.time()) - 29 * 86400; p["until"] = int(time.time())
    c, js = get(f"{uid}/insights", **p)
    out.setdefault("compte_insights", {})[met] = js if c == 200 else {"erreur": c, "detail": js.get("error", {}).get("message")}
json.dump(out, open("data.json", "w"), ensure_ascii=False)
ok = sum(1 for m in medias if m["insights"].get("views") is not None)
print(f"::notice::{len(medias)} publications, {ok} avec stats ; erreurs : {len(out['erreurs'])}", flush=True)
for e in out["erreurs"][:5]: print("::warning::" + json.dumps(e, ensure_ascii=False)[:300], flush=True)
