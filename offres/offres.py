"""Chercheur d'offres de stage : LinkedIn -> CV + lettre adaptés (Gemini) -> Telegram.
Tourne sur GitHub Actions. Un passage reste actif ~5 h 30 et vérifie toutes les 10 min.

Secrets : GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CV_TEL, CV_EMAIL
"""
import os, re, json, time, random, subprocess, datetime, urllib.parse
import requests
from bs4 import BeautifulSoup
import documents as D

# ---------------- RÉGLAGES ----------------
RECHERCHES = [
    "stage conception numérique", "stage FPGA", "stage ASIC", "stage VLSI", "stage microélectronique",
    "stage conception analogique", "stage circuits intégrés", "stage vérification RTL", "stage systèmes embarqués",
    "stage logiciel embarqué", "stage intelligence artificielle embarquée", "stage vision par ordinateur",
    "stage télécommunications", "stage semi-conducteurs", "stage fin d'études électronique",
    "FPGA internship", "ASIC design internship", "analog IC design internship", "embedded systems internship",
    "digital design internship", "machine learning hardware internship", "semiconductor internship",
]
LIEUX = ["France", "European Union", "Switzerland", "Canada"]
PAR_PASSAGE = 6          # recherches LinkedIn par vérification (on tourne dans la liste)
MAX_OFFRES = 6           # offres traitées max par vérification (limite gratuite Gemini)
ECART_MIN = 10           # minutes entre deux vérifications
DUREE_MAX_MIN = 330
DISPO = "1er novembre 2026"
# ------------------------------------------

ICI = os.path.dirname(os.path.abspath(__file__))
VUES = os.path.join(ICI, "vues.json")
TG = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
CHAT = os.environ["TELEGRAM_CHAT_ID"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}
MODELES = [os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-flash-lite-latest"]

def log(*a): print(*a, flush=True)

def tg_msg(text):
    try: requests.post(f"{TG}/sendMessage", data={"chat_id": CHAT, "text": text[:4000], "disable_web_page_preview": True}, timeout=30)
    except Exception as ex: log("Telegram KO", ex)

def tg_doc(path, caption=""):
    with open(path, "rb") as f:
        requests.post(f"{TG}/sendDocument", data={"chat_id": CHAT, "caption": caption[:1000]}, files={"document": f}, timeout=60)

# ---------- LinkedIn (pages publiques, sans connexion) ----------
def chercher(mots, lieu, periode):
    url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
           + urllib.parse.urlencode({"keywords": mots, "location": lieu, "f_TPR": periode, "f_JT": "I", "start": 0}))
    r = requests.get(url, headers=UA, timeout=30)
    if r.status_code != 200:
        log(f"::warning::LinkedIn {r.status_code} {mots} {lieu}"); return []
    soup = BeautifulSoup(r.text, "html.parser"); out = []
    for li in soup.select("li"):
        div = li.select_one("[data-entity-urn]")
        if not div: continue
        jid = div["data-entity-urn"].split(":")[-1]
        t = li.select_one(".base-search-card__title"); c = li.select_one(".base-search-card__subtitle")
        l = li.select_one(".job-search-card__location"); a = li.select_one("a.base-card__full-link")
        out.append({"id": jid, "titre": t.get_text(strip=True) if t else "", "entreprise": c.get_text(strip=True) if c else "",
                    "lieu": l.get_text(strip=True) if l else "", "lien": (a["href"].split("?")[0] if a else f"https://www.linkedin.com/jobs/view/{jid}")})
    return out

def description(jid):
    r = requests.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}", headers=UA, timeout=30)
    if r.status_code != 200: return ""
    soup = BeautifulSoup(r.text, "html.parser")
    d = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
    return d.get_text("\n", strip=True)[:9000] if d else ""

# ---------- Gemini ----------
def gemini(prompt):
    """Essaie plusieurs modèles ; sur 429 (quota/minute) attend le délai demandé par Google."""
    key = os.environ["GEMINI_API_KEY"].strip(); erreurs = []
    for m in MODELES:
        for essai in range(3):
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                              params={"key": key}, timeout=120,
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}})
            if r.status_code == 200:
                try:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt)
                except Exception as ex:
                    erreurs.append(f"{m} réponse illisible {ex}"); continue
            msg = r.text[:300].replace("\n", " ")
            erreurs.append(f"{m} {r.status_code} {msg}")
            if r.status_code in (400, 401, 403, 404): break          # modèle indispo ou clé refusée -> modèle suivant
            attente = 20 * (essai + 1)
            mt = re.search(r'"retryDelay":\s*"(\d+)s"', r.text)
            if mt: attente = min(90, int(mt.group(1)) + 2)
            if "PerDay" in r.text: break                              # quota du jour épuisé pour ce modèle
            time.sleep(attente)
    raise RuntimeError(" || ".join(erreurs)[-1500:])

PROMPT = """Tu aides Sayidina Dicko, étudiant ingénieur en 5e année (Polytech Marseille, Microélectronique et Télécommunications),
qui cherche un STAGE DE FIN D'ÉTUDES de 6 mois, disponible dès le {dispo}.

Voici une offre LinkedIn :
TITRE : {titre}
ENTREPRISE : {entreprise}
LIEU : {lieu}
DESCRIPTION :
{desc}

Son résumé de base : {resume}
Ses compétences de base : {comp}
Ses projets : microprocesseur 8 bits RISC conçu en groupe (puce), optimisation de l'algorithme caméra Pixy2 sur voiture NXP CUP (S32K144), reconnaissance d'images sur carte avec NPU.
Ses expériences : réparateur d'appareils électroniques (BFK Net Provence), stage chez AIME Toulouse (fabrication de cellules photovoltaïques), professeur particulier, serveur.

Réponds UNIQUEMENT en JSON avec ces clés :
- "pertinent": true si c'est un stage (stage / internship / PFE / fin d'études, pas un CDI, pas une alternance) lié à l'électronique, la microélectronique, FPGA/ASIC/VLSI, l'analogique, l'embarqué, les télécoms, l'IA ou le logiciel technique ; sinon false.
- "langue": "fr" si l'offre est en français, sinon "en".
- "domaine": le domaine du stage en quelques mots, repris de l'offre (ex : "conception numérique ASIC/FPGA").
- "ville": la ville de l'offre ; "code_postal": son code postal (5 chiffres en France ; si seul le département est donné, celui de la préfecture ; code postal local si étranger, sinon "") ; "departement": en France "Nom (numéro)" ex. "Loiret (45)", à l'étranger la région/l'état ; "pays": le pays.
- "resume": résumé du CV (4 à 5 phrases, dans la langue de l'offre), calé sur le profil recherché en reprenant ses mots-clés, terminant par : "Recherche un stage de fin d'études de 6 mois en <domaine>, disponible dès le {dispo}." (ou l'équivalent anglais).
- "competences": 14 à 16 compétences courtes (moins de 45 caractères chacune), dans la langue de l'offre : d'abord EXACTEMENT les compétences, outils et langages demandés dans l'offre (même s'ils ne sont pas dans ses compétences de base), puis ses compétences de base les plus proches.
- "lettre": une lettre de motivation de 4 paragraphes (tableau de chaînes), dans la langue de l'offre, sans formule d'appel ni signature : pourquoi cette entreprise et ce poste, ce qu'il apporte (en reliant ses projets et compétences aux missions), sa disponibilité dès le {dispo} pour 6 mois, demande d'entretien. Ton professionnel, concret, pas de phrases creuses.
"""

def adapter(o, desc):
    return gemini(PROMPT.format(dispo=DISPO, titre=o["titre"], entreprise=o["entreprise"], lieu=o["lieu"], desc=desc,
                                resume=D.RESUME_BASE, comp=", ".join(D.COMPETENCES_BASE)))

# ---------- état ----------
def charger():
    return json.load(open(VUES)) if os.path.exists(VUES) else {"vues": [], "tour": 0}

def sauver(st):
    st["vues"] = st["vues"][-5000:]
    json.dump(st, open(VUES, "w"))
    subprocess.run("git add offres/vues.json && git commit -qm 'Offres vues' && git pull -q --rebase && git push -q",
                   shell=True, cwd=os.path.dirname(ICI))

def nettoie(s): return re.sub(r"[^A-Za-z0-9]+", "_", s)[:40].strip("_")

def verification(st, premiere):
    periode = "r86400" if premiere else "r3600"
    combos = [(m, l) for m in RECHERCHES for l in LIEUX]
    debut = st.get("tour", 0) % len(combos)
    lot = [combos[(debut + k) % len(combos)] for k in range(PAR_PASSAGE)]
    st["tour"] = debut + PAR_PASSAGE
    vues = set(st["vues"]); nouvelles = {}
    for mots, lieu in lot:
        for o in chercher(mots, lieu, periode):
            if o["id"] not in vues: nouvelles[o["id"]] = o
        time.sleep(random.uniform(2, 5))
    log(f"::notice::{len(nouvelles)} nouvelle(s) offre(s) sur {len(lot)} recherches")
    traitees = 0; changed = False
    for o in list(nouvelles.values()):
        if traitees >= MAX_OFFRES: break
        st["vues"].append(o["id"]); changed = True
        desc = description(o["id"])
        if not desc: continue
        time.sleep(7)                                   # reste sous la limite gratuite par minute
        try:
            a = adapter(o, desc)
        except Exception as ex:
            log(f"::warning::Gemini KO {ex}"); st["vues"].remove(o["id"]); break
        traitees += 1
        if not a.get("pertinent"):
            log("Hors sujet :", o["titre"]); continue
        nom = f"{nettoie(o['entreprise'])}_{o['id']}"
        cv, lm = f"/tmp/CV_Sayidina_Dicko_{nom}.pdf", f"/tmp/Lettre_Sayidina_Dicko_{nom}.pdf"
        ville, cp, pays = a.get("ville", ""), a.get("code_postal", ""), a.get("pays", "")
        D.pdfs([(D.cv_html(a["resume"], a["competences"], ville, cp, pays), cv),
                (D.lettre_html(a["lettre"], o["entreprise"], o["titre"], ville, cp, pays, a.get("langue", "fr")), lm)])
        tg_msg(f"🎯 {o['titre']}\n🏢 {o['entreprise']}\n📍 {o['lieu']}\n🧩 {a.get('domaine','')}\n\n"
               f"🏠 Adresse à indiquer (comme sur le CV) :\n• Ville : {ville or '-'}\n• Code postal : {cp or '-'}\n"
               f"• Département : {a.get('departement','') or '-'}\n• Pays : {pays or '-'}\n\n👉 Postuler : {o['lien']}")
        tg_doc(cv, "CV adapté"); tg_doc(lm, "Lettre de motivation")
        log(f"::notice::Envoyé : {o['titre']} - {o['entreprise']}")
    sauver(st)

def main():
    if not (os.environ.get("CV_TEL", "").strip() and os.environ.get("CV_EMAIL", "").strip()):
        log("Secrets CV_TEL / CV_EMAIL manquants : on attend qu'ils soient ajoutés."); return
    t0 = time.time(); st = charger(); premiere = not st["vues"]
    while True:
        try:
            verification(st, premiere)
        except Exception as ex:
            log(f"::error::Erreur : {ex}")
        premiere = False
        if (time.time() - t0) / 60 > DUREE_MAX_MIN - ECART_MIN: return
        time.sleep(ECART_MIN * 60)

if __name__ == "__main__":
    main()
