"""Analyse approfondie du compte Instagram -> rapport PDF envoyé sur Telegram.

Entrée : data.json (produit par collecte.py).
Étapes : durées réelles des vidéos (ffprobe), lots de hooks, statistiques, analyse vidéo par Gemini
(meilleur et pire hook de chaque lot), synthèse Gemini, PDF (Playwright) -> Telegram.
Variables : GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID ; SANS_IA=1 pour tester sans Gemini.
"""
import os, re, json, time, math, html, subprocess, statistics as st, datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo
import requests

PARIS = ZoneInfo("Europe/Paris")
SANS_IA = os.environ.get("SANS_IA") == "1"
MODELES = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]
LOTS_VIDEO = int(os.environ.get("LOTS_VIDEO", "6"))       # nb de lots dont on analyse les vidéos
def log(*a): print(*a, flush=True)

# ---------------------------------------------------------------- données
D = json.load(open("data.json"))
COMPTE = D["compte"]
R = []
for m in D["medias"]:
    i = m.get("insights", {})
    t = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).astimezone(PARIS)
    R.append({"id": m["id"], "t": t, "cap": (m.get("caption") or "").strip(), "lien": m.get("permalink", ""),
              "url": m.get("media_url"), "vues": i.get("views") or 0, "portee": i.get("reach") or 0,
              "likes": i.get("likes") or 0, "com": i.get("comments") or 0, "part": i.get("shares") or 0,
              "enr": i.get("saved") or 0, "watch": (i.get("ig_reels_avg_watch_time") or 0) / 1000})
R.sort(key=lambda r: r["t"])

def duree(url):
    if not url: return None
    try:
        o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", url],
                           capture_output=True, text=True, timeout=60).stdout.strip()
        return float(o) if o else None
    except Exception:
        return None
if os.environ.get("SANS_DUREE") != "1":
    for r in R: r["duree"] = duree(r["url"])
else:
    for r in R: r["duree"] = None
for r in R:
    r["ret"] = min(1.5, r["watch"] / r["duree"]) if r.get("duree") else None   # part de la vidéo regardée en moyenne
    r["eng"] = r["likes"] + 2 * r["com"] + 3 * r["part"] + 3 * r["enr"]

# lots = même corps (même description de départ) publiés le même jour
def cle_lot(r):
    c = re.sub(r"\s+", " ", r["cap"])[:70].lower()
    return (re.search(r"commente\s*«?\s*([^»]+?)\s*»", c, re.I) or [None, c[:30]])[1].strip(" «»").upper() + " · " + r["t"].strftime("%d/%m")
LOTS = defaultdict(list)
for r in R: LOTS[cle_lot(r)].append(r)
for k, v in LOTS.items():
    for n, r in enumerate(sorted(v, key=lambda r: r["t"]), 1): r["rang"] = n; r["lot"] = k

def med(x): x = [v for v in x if v is not None]; return st.median(x) if x else 0
def moy(x): x = [v for v in x if v is not None]; return sum(x) / len(x) if x else 0

# ---------------------------------------------------------------- statistiques
S = {}
S["n"] = len(R); S["jours"] = (R[-1]["t"] - R[0]["t"]).days + 1 if R else 0
S["abonnes"] = COMPTE.get("followers_count")
S["vues_tot"] = sum(r["vues"] for r in R); S["vues_med"] = med([r["vues"] for r in R]); S["vues_max"] = max((r["vues"] for r in R), default=0)
S["likes_tot"] = sum(r["likes"] for r in R); S["com_tot"] = sum(r["com"] for r in R)
S["part_tot"] = sum(r["part"] for r in R); S["enr_tot"] = sum(r["enr"] for r in R)
S["par_jour"] = round(S["n"] / max(1, S["jours"]), 1)
# périodes : on coupe là où la médiane des vues s'effondre (chercher la meilleure coupure)
best = None
for k in range(10, len(R) - 10):
    a, b = med([r["vues"] for r in R[:k]]), med([r["vues"] for r in R[k:]])
    if best is None or a - b > best[0]: best = (a - b, k)
K = best[1] if best else len(R) // 2
P1, P2 = R[:K], R[K:]
S["coupure"] = R[K]["t"].strftime("%d/%m") if R else ""
def resume(P):
    return {"n": len(P), "du": P[0]["t"].strftime("%d/%m"), "au": P[-1]["t"].strftime("%d/%m"),
            "vues_med": med([r["vues"] for r in P]), "vues_moy": round(moy([r["vues"] for r in P])),
            "plus100": sum(r["vues"] >= 100 for r in P), "moins20": sum(r["vues"] < 20 for r in P),
            "watch_med": round(med([r["watch"] for r in P]), 1), "ret_med": round(100 * med([r["ret"] for r in P]), 0) if any(r["ret"] for r in P) else None,
            "duree_med": round(med([r["duree"] for r in P]), 1) if any(r["duree"] for r in P) else None,
            "eng_100": round(100 * sum(r["eng"] for r in P) / max(1, sum(r["vues"] for r in P)), 2),
            "ecart_min": round(med([(P[i]["t"] - P[i-1]["t"]).total_seconds() / 60 for i in range(1, len(P))]), 0) if len(P) > 1 else None,
            "par_jour": round(len(P) / max(1, (P[-1]["t"] - P[0]["t"]).days + 1), 1)}
S["p1"], S["p2"] = resume(P1), resume(P2)
# lots
L = []
for k, v in LOTS.items():
    vs = sorted(v, key=lambda r: -r["vues"])
    L.append({"lot": k, "n": len(v), "date": min(r["t"] for r in v), "vues_med": med([r["vues"] for r in v]), "vues_max": vs[0]["vues"],
              "vues_min": vs[-1]["vues"], "ret_med": round(100 * med([r["ret"] for r in v])) if any(r["ret"] for r in v) else None,
              "duree": round(med([r["duree"] for r in v]), 1) if any(r["duree"] for r in v) else None,
              "meilleur": vs[0], "pire": vs[-1], "rang_corr": None})
    # les premiers hooks d'un lot font-ils mieux que les derniers ? (fatigue / doublons)
    if len(v) >= 5:
        xs = [r["rang"] for r in v]; ys = [r["vues"] for r in v]
        mx, my = moy(xs), moy(ys); sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        L[-1]["rang_corr"] = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 2) if sx and sy else None
L.sort(key=lambda l: l["date"])
S["ecart_hook"] = round(med([l["vues_max"] / max(1, l["vues_min"]) for l in L if l["n"] >= 5]), 1)
# heure de publication
H = defaultdict(list)
for r in R: H[r["t"].hour // 3 * 3].append(r["vues"])
S["heures"] = {f"{h:02d}h-{h+3:02d}h": (len(v), med(v)) for h, v in sorted(H.items())}
# vidéos publiées à moins de 5 min d'intervalle
S["rafales"] = sum(1 for i in range(1, len(R)) if (R[i]["t"] - R[i-1]["t"]).total_seconds() < 300)
# ce qui est corrélé aux vues (rétention, durée)
def corr(a, b):
    p = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(p) < 8: return None
    mx, my = moy([x for x, _ in p]), moy([y for _, y in p])
    sx = math.sqrt(sum((x - mx) ** 2 for x, _ in p)); sy = math.sqrt(sum((y - my) ** 2 for _, y in p))
    return round(sum((x - mx) * (y - my) for x, y in p) / (sx * sy), 2) if sx and sy else None
S["corr_ret_vues"] = corr([r["ret"] for r in R], [r["vues"] for r in R])
S["corr_duree_vues"] = corr([r["duree"] for r in R], [r["vues"] for r in R])
CI = D.get("compte_insights", {})
def serie(nom):
    try: return [(v["end_time"][:10], v["value"]) for v in CI[nom]["data"][0]["values"]]
    except Exception: return []
S["abonnes_30j"] = serie("follower_count")
TOP = sorted(R, key=lambda r: -r["vues"])[:10]; FLOP = sorted(R, key=lambda r: r["vues"])[:10]

# ---------------------------------------------------------------- Gemini
def gemini(parts, json_out=True, temp=0.4):
    key = os.environ["GEMINI_API_KEY"].strip(); err = []
    for m in MODELES:
        for essai in range(3):
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", params={"key": key}, timeout=300,
                              json={"contents": [{"parts": parts}], "generationConfig": dict({"temperature": temp}, **({"responseMimeType": "application/json"} if json_out else {}))})
            if r.status_code == 200:
                try:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt) if json_out else txt
                except Exception as ex: err.append(f"{m} illisible {ex}"); continue
            err.append(f"{m} {r.status_code} {r.text[:200]}")
            if r.status_code in (400, 401, 403, 404) or "PerDay" in r.text: break
            mt = re.search(r'"retryDelay":\s*"(\d+)s"', r.text); time.sleep(min(90, int(mt.group(1)) + 2) if mt else 20 * (essai + 1))
    raise RuntimeError(" || ".join(err)[-1200:])

def envoyer_video(path):
    """Upload sur l'API Fichiers de Gemini, attend l'état ACTIVE, renvoie l'URI."""
    key = os.environ["GEMINI_API_KEY"].strip(); size = os.path.getsize(path)
    r = requests.post("https://generativelanguage.googleapis.com/upload/v1beta/files", params={"key": key}, timeout=60,
                      headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                               "X-Goog-Upload-Header-Content-Length": str(size), "X-Goog-Upload-Header-Content-Type": "video/mp4", "Content-Type": "application/json"},
                      json={"file": {"display_name": os.path.basename(path)}})
    up = r.headers["X-Goog-Upload-URL"]
    f = requests.post(up, data=open(path, "rb").read(), timeout=300,
                      headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"}).json()["file"]
    for _ in range(60):
        if f.get("state") == "ACTIVE": return f["uri"]
        time.sleep(5); f = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{f['name']}", params={"key": key}, timeout=60).json()
    raise RuntimeError("vidéo jamais prête chez Gemini")

PROMPT_VIDEO = """Tu es un expert en croissance Instagram (Reels) dans la niche IA / automatisation (n8n, agents IA) pour entrepreneurs francophones.
Analyse ce réel image par image. Chiffres réels : {vues} vues, temps de visionnage moyen {watch:.1f} s sur {duree} s ({ret}), {likes} likes, {com} commentaires, {part} partages, {enr} enregistrements.
Dans son lot (même corps de vidéo, seul le hook change) ce réel est le {statut} (médiane du lot : {lot_med} vues).
Réponds en JSON, en français, concret, sans phrases creuses :
- "hook_texte": les mots exacts dits et/ou écrits dans les 3 premières secondes
- "hook_visuel": ce qu'on voit dans les 3 premières secondes (cadrage, mouvement, texte à l'écran)
- "hook_type": ex. promesse, curiosité, chiffre choc, problème, démonstrative...
- "note_hook": 0-10 (capacité à arrêter le scroll d'un entrepreneur)
- "rythme": description du rythme (coupes, blancs, longueur des plans), note 0-10
- "clarte": est-ce qu'on comprend en 5 s ce que la vidéo va apporter ? note 0-10
- "decrochage": à quel moment (en secondes) et pourquoi le spectateur décroche probablement, en t'appuyant sur le temps de visionnage moyen
- "qualite_image_son": problèmes visibles/audibles (lumière, son, cadrage, sous-titres)
- "valeur": que gagne le spectateur ? y a-t-il une raison de partager/enregistrer ?
- "cta": comment est fait l'appel à l'action et s'il est efficace
- "points_forts": liste
- "points_faibles": liste (les plus graves d'abord)
"""
def analyser_videos():
    choix = []
    for l in sorted([l for l in L if l["n"] >= 3], key=lambda l: l["date"]):
        choix.append(l)
    # répartir : premiers lots (quand ça marchait) et derniers lots
    if len(choix) > LOTS_VIDEO: choix = choix[:LOTS_VIDEO // 2] + choix[-(LOTS_VIDEO - LOTS_VIDEO // 2):]
    out = []
    os.makedirs("/tmp/v", exist_ok=True)
    for l in choix:
        for statut, r in (("MEILLEUR hook", l["meilleur"]), ("PIRE hook", l["pire"])):
            try:
                p = f"/tmp/v/{r['id']}.mp4"
                with open(p, "wb") as fh: fh.write(requests.get(r["url"], timeout=120).content)
                uri = envoyer_video(p)
                a = gemini([{"file_data": {"mime_type": "video/mp4", "file_uri": uri}},
                            {"text": PROMPT_VIDEO.format(vues=r["vues"], watch=r["watch"], duree=f"{r['duree']:.0f}" if r["duree"] else "?",
                                                         ret=f"{100*r['ret']:.0f} % regardés" if r["ret"] else "durée inconnue", likes=r["likes"], com=r["com"],
                                                         part=r["part"], enr=r["enr"], statut=statut, lot_med=l["vues_med"])}])
                out.append({"lot": l["lot"], "statut": statut, "id": r["id"], "vues": r["vues"], "lien": r["lien"], "analyse": a})
                log("vidéo analysée", l["lot"], statut, r["vues"])
                time.sleep(4)
            except Exception as ex:
                log(f"::warning::analyse vidéo KO {r['id']} {ex}")
    return out

PROMPT_SYNTHESE = """Tu es un stratège de croissance Instagram de haut niveau (Reels, niche IA / automatisation n8n pour entrepreneurs francophones).
Tu écris le rapport d'audit du compte @{user} ({abonnes} abonnés). Objectif du créateur : percer (abonnés + ventes d'une formation), lead magnet = templates n8n envoyés à ceux qui commentent un mot-clé.
Pratique actuelle : il tourne un corps de vidéo + 15 hooks différents, et publie les 15 versions le même jour (une toutes les 10-20 min, parfois plusieurs dans la même minute), même description pour toutes.

STATISTIQUES CALCULÉES (fiables) :
{stats}

LOTS (un lot = même corps + même description, hooks différents) :
{lots}

TOP 10 et FLOP 10 :
{topflop}

ANALYSES VIDÉO (meilleur et pire hook de plusieurs lots, faites par une IA qui a regardé les vidéos) :
{videos}

Écris un audit HONNÊTE, direct et profond, en français, sans flatterie ni généralités. Chaque affirmation doit s'appuyer sur un chiffre ou une observation ci-dessus ; distingue ce qui est prouvé par les données de ce qui est une hypothèse.
Réponds en JSON :
- "verdict": 3-4 phrases : la situation en vrai, sans détour
- "pourquoi_avant": pourquoi ses premières vidéos étaient poussées (100-200 vues) — liste d'explications argumentées
- "pourquoi_maintenant": pourquoi ça s'est effondré — liste d'explications argumentées, la plus probable en premier
- "ce_qui_marche": liste (preuves à l'appui)
- "ce_qui_ne_marche_pas": liste (preuves à l'appui)
- "hooks": {{"gagnants": [ce qui caractérise les meilleurs hooks], "perdants": [ce qui caractérise les pires], "exemples_a_reprendre": [3 hooks réécrits, prêts à dire face caméra]}}
- "methode_15_hooks": analyse franche de la stratégie "15 hooks le même jour" et ce qu'il faut faire à la place (fréquence, test des hooks, etc.)
- "plan_7_jours": liste de 7 actions concrètes et mesurables, dans l'ordre
- "a_mesurer": les 3-4 indicateurs à suivre et le seuil à viser pour chacun
- "concurrents": ce que les créateurs qui percent dans cette niche font typiquement différemment (formats, hooks, démonstration, preuve, fréquence), en le reliant à ses chiffres
"""

# ---------------------------------------------------------------- graphiques SVG
def svg_points(W=900, Hh=300):
    if not R: return ""
    t0, t1 = R[0]["t"].timestamp(), R[-1]["t"].timestamp(); vmax = max(r["vues"] for r in R) * 1.1
    X = lambda t: 50 + (W - 70) * (t - t0) / max(1, t1 - t0); Y = lambda v: Hh - 30 - (Hh - 50) * v / vmax
    o = [f'<svg viewBox="0 0 {W} {Hh}" width="100%"><rect width="{W}" height="{Hh}" fill="#fff"/>']
    for g in range(0, int(vmax) + 1, 50):
        o.append(f'<line x1="50" x2="{W-20}" y1="{Y(g):.0f}" y2="{Y(g):.0f}" stroke="#eee"/><text x="44" y="{Y(g)+4:.0f}" font-size="11" text-anchor="end" fill="#888">{g}</text>')
    xc = X(R[K]["t"].timestamp())
    o.append(f'<line x1="{xc:.0f}" x2="{xc:.0f}" y1="15" y2="{Hh-30}" stroke="#e5484d" stroke-dasharray="5 4"/><text x="{xc+6:.0f}" y="28" font-size="12" fill="#e5484d">effondrement ({S["coupure"]})</text>')
    d = R[0]["t"].date()
    while d <= R[-1]["t"].date():
        if d.day % 3 == 1:
            x = X(dt.datetime.combine(d, dt.time(12), PARIS).timestamp()); o.append(f'<text x="{x:.0f}" y="{Hh-10}" font-size="11" text-anchor="middle" fill="#888">{d:%d/%m}</text>')
        d += dt.timedelta(days=1)
    for r in R:
        c = "#2f6fde" if r["vues"] >= 100 else ("#9aa7bd" if r["vues"] >= 20 else "#e5484d")
        o.append(f'<circle cx="{X(r["t"].timestamp()):.1f}" cy="{Y(r["vues"]):.1f}" r="4" fill="{c}" opacity="0.8"/>')
    o.append("</svg>"); return "".join(o)

def svg_lots(W=900):
    n = len(L); Hh = 26 * n + 40; vmax = max(l["vues_max"] for l in L) * 1.05
    X = lambda v: 230 + (W - 260) * v / vmax
    o = [f'<svg viewBox="0 0 {W} {Hh}" width="100%"><rect width="{W}" height="{Hh}" fill="#fff"/>']
    for i, l in enumerate(L):
        y = 20 + i * 26
        o.append(f'<text x="222" y="{y+13}" font-size="12" text-anchor="end" fill="#333">{html.escape(l["lot"])} ({l["n"]})</text>')
        o.append(f'<line x1="{X(l["vues_min"]):.0f}" x2="{X(l["vues_max"]):.0f}" y1="{y+9}" y2="{y+9}" stroke="#c9d3e6" stroke-width="10" stroke-linecap="round"/>')
        o.append(f'<circle cx="{X(l["vues_med"]):.0f}" cy="{y+9}" r="6" fill="#2f6fde"/><text x="{X(l["vues_max"])+10:.0f}" y="{y+13}" font-size="11" fill="#888">{l["vues_min"]}–{l["vues_max"]} (méd. {l["vues_med"]:.0f})</text>')
    o.append("</svg>"); return "".join(o)

# ---------------------------------------------------------------- PDF
CSS = """@page{size:A4;margin:14mm 13mm}body{font-family:'Liberation Sans',Arial,sans-serif;color:#1b1f2a;font-size:10.4pt;line-height:1.45}
h1{font-size:22pt;margin:0}h2{font-size:14pt;margin:22px 0 8px;padding-bottom:4px;border-bottom:2px solid #2f6fde;page-break-after:avoid}h3{font-size:11.5pt;margin:14px 0 6px}
.sub{color:#667;margin:4px 0 14px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0}.k{background:#f3f6fc;border-radius:10px;padding:9px 10px}
.k b{display:block;font-size:17pt;color:#2f6fde}.k span{font-size:8.6pt;color:#556}.verdict{background:#fff4e5;border-left:5px solid #ff9f1a;padding:10px 12px;border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:9pt;margin:6px 0}th,td{border-bottom:1px solid #e3e7ef;padding:4px 5px;text-align:left;vertical-align:top}th{background:#f3f6fc}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.box{background:#f7f8fb;border-radius:8px;padding:8px 10px}.bad{color:#c62f34}.good{color:#1c8a4a}
ul{margin:4px 0 6px 18px;padding:0}li{margin:2px 0}.vid{border:1px solid #e3e7ef;border-radius:8px;padding:8px 10px;margin:8px 0;page-break-inside:avoid}.small{font-size:8.6pt;color:#667}
a{color:#2f6fde;text-decoration:none}"""
def e(x): return html.escape(str(x))
def ul(xs): return "<ul>" + "".join(f"<li>{e(x)}</li>" for x in (xs or [])) + "</ul>"

def construire_html(A, V):
    p1, p2 = S["p1"], S["p2"]
    k = [("Réels analysés", S["n"]), ("Abonnés", S["abonnes"]), ("Vues médianes", f'{S["vues_med"]:.0f}'), ("Meilleur réel", f'{S["vues_max"]} vues'),
         ("Réels / jour", S["par_jour"]), ("Commentaires", S["com_tot"]), ("Partages", S["part_tot"]), ("Enregistrements", S["enr_tot"])]
    h = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>",
         f"<h1>Audit Instagram — @{e(COMPTE.get('username',''))}</h1><div class='sub'>Rapport du {dt.datetime.now(PARIS):%d/%m/%Y à %H:%M} · {S['n']} réels du {R[0]['t']:%d/%m} au {R[-1]['t']:%d/%m}</div>",
         "<div class='kpis'>" + "".join(f"<div class='k'><b>{e(v)}</b><span>{e(t)}</span></div>" for t, v in k) + "</div>"]
    if A.get("verdict"): h.append(f"<div class='verdict'><b>Verdict.</b> {e(A['verdict'])}</div>")
    h.append("<h2>1. L'évolution des vues</h2>" + svg_points() +
             "<div class='small'>Bleu : ≥ 100 vues · gris : 20-99 · rouge : &lt; 20. Chaque point = un réel.</div>")
    h.append("<table><tr><th></th><th>Avant le " + e(S["coupure"]) + "</th><th>Depuis le " + e(S["coupure"]) + "</th></tr>" + "".join(
        f"<tr><td>{t}</td><td>{e(a)}</td><td>{e(b)}</td></tr>" for t, a, b in [
            ("Réels publiés", p1["n"], p2["n"]), ("Réels / jour", p1["par_jour"], p2["par_jour"]), ("Écart médian entre 2 réels", f'{p1["ecart_min"]:.0f} min', f'{p2["ecart_min"]:.0f} min'),
            ("Vues médianes", f'{p1["vues_med"]:.0f}', f'{p2["vues_med"]:.0f}'), ("Réels ≥ 100 vues", p1["plus100"], p2["plus100"]), ("Réels < 20 vues", p1["moins20"], p2["moins20"]),
            ("Durée médiane des vidéos", f'{p1["duree_med"]} s' if p1["duree_med"] else "?", f'{p2["duree_med"]} s' if p2["duree_med"] else "?"),
            ("Temps de visionnage médian", f'{p1["watch_med"]} s', f'{p2["watch_med"]} s'),
            ("Part de la vidéo regardée (méd.)", f'{p1["ret_med"]:.0f} %' if p1["ret_med"] is not None else "?", f'{p2["ret_med"]:.0f} %' if p2["ret_med"] is not None else "?"),
            ("Interactions pour 100 vues", p1["eng_100"], p2["eng_100"])]) + "</table>")
    if A.get("pourquoi_avant") or A.get("pourquoi_maintenant"):
        h.append("<div class='two'><div class='box'><h3 class='good'>Pourquoi c'était poussé avant</h3>" + ul(A.get("pourquoi_avant")) +
                 "</div><div class='box'><h3 class='bad'>Pourquoi ça s'est effondré</h3>" + ul(A.get("pourquoi_maintenant")) + "</div></div>")
    h.append("<h2>2. Les lots de hooks (même corps, hook différent)</h2>" + svg_lots() +
             f"<div class='small'>Barre = du pire au meilleur hook du lot ; point = médiane. Dans un même lot, le meilleur hook fait en médiane ×{S['ecart_hook']} les vues du pire.</div>")
    rc = [l for l in L if l["rang_corr"] is not None]
    if rc:
        neg = sum(1 for l in rc if l["rang_corr"] < -0.2)
        h.append(f"<p>Ordre de publication dans le lot : dans <b>{neg} lots sur {len(rc)}</b>, les versions publiées en dernier font moins de vues que les premières (corrélation rang/vues négative), signe qu'Instagram limite les doublons publiés à la chaîne.</p>")
    h.append(f"<p>{S['rafales']} réels ont été publiés moins de 5 minutes après le précédent.</p>")
    if A.get("hooks"):
        hk = A["hooks"]
        h.append("<div class='two'><div class='box'><h3 class='good'>Hooks gagnants</h3>" + ul(hk.get("gagnants")) + "</div><div class='box'><h3 class='bad'>Hooks perdants</h3>" + ul(hk.get("perdants")) + "</div></div>")
        if hk.get("exemples_a_reprendre"): h.append("<h3>Hooks à tester (réécrits)</h3>" + ul(hk["exemples_a_reprendre"]))
    h.append("<h2>3. Top 10 et flop 10</h2><div class='two'>")
    for titre, lst in (("Top 10", TOP), ("Flop 10", FLOP)):
        h.append(f"<div><h3>{titre}</h3><table><tr><th>Date</th><th>Lot</th><th>Vues</th><th>Regardé</th></tr>" + "".join(
            f"<tr><td><a href='{e(r['lien'])}'>{r['t']:%d/%m %Hh%M}</a></td><td>{e(r['lot'].split(' · ')[0])}</td><td>{r['vues']}</td><td>{(f'{100*r['ret']:.0f} %' if r['ret'] else f'{r['watch']:.1f} s')}</td></tr>" for r in lst) + "</table></div>")
    h.append("</div>")
    if A.get("ce_qui_marche") or A.get("ce_qui_ne_marche_pas"):
        h.append("<h2>4. Ce qui marche / ce qui ne marche pas</h2><div class='two'><div class='box'><h3 class='good'>Ce qui marche</h3>" + ul(A.get("ce_qui_marche")) +
                 "</div><div class='box'><h3 class='bad'>Ce qui ne marche pas</h3>" + ul(A.get("ce_qui_ne_marche_pas")) + "</div></div>")
    h.append("<h2>5. Heure de publication</h2><table><tr><th>Créneau</th><th>Réels</th><th>Vues médianes</th></tr>" +
             "".join(f"<tr><td>{k}</td><td>{n}</td><td>{m:.0f}</td></tr>" for k, (n, m) in S["heures"].items()) + "</table>")
    if V:
        h.append("<h2>6. Ce que l'IA voit dans tes vidéos</h2><div class='small'>Meilleur et pire hook de plusieurs lots, vidéo regardée en entier par l'IA.</div>")
        for v in V:
            a = v["analyse"]
            h.append(f"<div class='vid'><b>{e(v['lot'])} — {e(v['statut'])}</b> · {v['vues']} vues · <a href='{e(v['lien'])}'>voir le réel</a>"
                     f"<p><b>Hook :</b> « {e(a.get('hook_texte',''))} » — {e(a.get('hook_type',''))} · note {e(a.get('note_hook','?'))}/10<br><b>Visuel :</b> {e(a.get('hook_visuel',''))}</p>"
                     f"<p><b>Décrochage :</b> {e(a.get('decrochage',''))}<br><b>Clarté :</b> {e(a.get('clarte',''))}<br><b>Rythme :</b> {e(a.get('rythme',''))}</p>"
                     f"<div class='two'><div><b class='good'>Forces</b>{ul(a.get('points_forts'))}</div><div><b class='bad'>Faiblesses</b>{ul(a.get('points_faibles'))}</div></div></div>")
    if A.get("methode_15_hooks"): h.append(f"<h2>7. La méthode « 15 hooks le même jour »</h2><p>{e(A['methode_15_hooks'])}</p>")
    if A.get("concurrents"): h.append(f"<h2>8. Ce que font différemment ceux qui percent</h2><p>{e(A['concurrents'])}</p>")
    if A.get("plan_7_jours"): h.append("<h2>9. Plan d'action — 7 jours</h2><ol>" + "".join(f"<li>{e(x)}</li>" for x in A["plan_7_jours"]) + "</ol>")
    if A.get("a_mesurer"): h.append("<h3>Ce qu'on mesure</h3>" + ul(A["a_mesurer"]))
    h.append(f"<p class='small'>Données : API Instagram (vues, portée, temps de visionnage moyen, interactions). Instagram ne fournit pas la courbe de rétention seconde par seconde : les moments de décrochage sont estimés. Corrélation part regardée / vues : {S['corr_ret_vues']} · durée / vues : {S['corr_duree_vues']}.</p></body></html>")
    return "".join(h)

def pdf(html_str, out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.set_content(html_str, wait_until="load"); pg.pdf(path=out, format="A4", print_background=True); b.close()

def telegram(path, texte):
    tg = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"; chat = os.environ["TELEGRAM_CHAT_ID"]
    requests.post(f"{tg}/sendMessage", data={"chat_id": chat, "text": texte[:4000], "disable_web_page_preview": True}, timeout=30)
    with open(path, "rb") as f: requests.post(f"{tg}/sendDocument", data={"chat_id": chat}, files={"document": f}, timeout=120)

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    log("::notice::" + json.dumps({k: S[k] for k in ("n", "coupure", "vues_med", "ecart_hook", "rafales")}, ensure_ascii=False))
    A, V = {}, []
    if not SANS_IA:
        V = analyser_videos()
        lots_txt = "\n".join(f"- {l['lot']} : {l['n']} versions, vues {l['vues_min']}-{l['vues_max']} (méd. {l['vues_med']:.0f}), durée {l['duree']} s, part regardée méd. {l['ret_med']} %, corr. rang/vues {l['rang_corr']}" for l in L)
        tf = "\n".join(f"TOP {r['t']:%d/%m %Hh%M} {r['lot']} rang {r['rang']} : {r['vues']} vues, {r['watch']:.1f}s regardées / {r['duree'] or '?'}s, {r['likes']} likes {r['part']} partages {r['enr']} enr." for r in TOP)
        tf += "\n" + "\n".join(f"FLOP {r['t']:%d/%m %Hh%M} {r['lot']} rang {r['rang']} : {r['vues']} vues, {r['watch']:.1f}s / {r['duree'] or '?'}s" for r in FLOP)
        stats = {k: v for k, v in S.items() if k not in ("abonnes_30j",)}
        try:
            A = gemini([{"text": PROMPT_SYNTHESE.format(user=COMPTE.get("username"), abonnes=S["abonnes"], stats=json.dumps(stats, ensure_ascii=False, default=str),
                                                        lots=lots_txt, topflop=tf, videos=json.dumps([{k: v[k] for k in ("lot", "statut", "vues", "analyse")} for v in V], ensure_ascii=False))}], temp=0.5)
        except Exception as ex:
            log(f"::warning::synthèse KO {ex}")
    out = f"/tmp/Audit_Instagram_{dt.datetime.now(PARIS):%Y-%m-%d}.pdf"
    open("/tmp/rapport.html", "w").write(construire_html(A, V)); pdf(open("/tmp/rapport.html").read(), out)
    log("PDF prêt", out)
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        resume_txt = (f"📊 Audit Instagram @{COMPTE.get('username')}\n\n{A.get('verdict','')}\n\n"
                      f"Avant le {S['coupure']} : {S['p1']['vues_med']:.0f} vues médianes · depuis : {S['p2']['vues_med']:.0f}.\nLe rapport complet est dans le PDF 👇")
        telegram(out, resume_txt)
