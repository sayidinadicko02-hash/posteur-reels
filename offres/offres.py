"""Chercheur d'offres de stage : LinkedIn -> CV + lettre adaptés (Gemini) -> Telegram.
Tourne sur GitHub Actions. Un passage reste actif ~5 h 30 et vérifie toutes les 10 min.

Secrets : GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CV_TEL, CV_EMAIL
"""
import os, re, json, time, random, subprocess, datetime, urllib.parse, unicodedata
import requests
from bs4 import BeautifulSoup
import documents as D

# ---------------- RÉGLAGES ----------------
RECHERCHES = [
    "stage microélectronique", "stage conception numérique", "stage conception ASIC", "stage FPGA",
    "stage VHDL", "stage Verilog", "stage VLSI", "stage conception analogique", "stage circuits intégrés",
    "stage vérification numérique", "stage layout", "stage semi-conducteurs", "stage design RTL",
    "stage électronique embarquée", "stage systèmes embarqués électronique", "stage hardware",
    "stage radiofréquence", "stage traitement du signal FPGA", "stage IA embarquée FPGA",
    "stage IA embarquée", "stage edge AI", "stage logiciel embarqué microcontrôleur", "stage firmware",
    "embedded systems internship", "embedded AI internship",
    "FPGA internship", "ASIC internship", "analog design internship", "digital design internship",
    "RTL design internship", "semiconductor internship", "hardware engineer internship",
]
RECHERCHES_ALT = [         # alternances : LinkedIn ne les classe pas en "stage", on cherche sans filtre de contrat
    "alternance microélectronique", "alternance FPGA", "alternance conception ASIC", "alternance VHDL",
    "alternance conception numérique", "alternance conception analogique", "alternance électronique embarquée",
    "alternance systèmes embarqués", "alternance semi-conducteurs", "alternance hardware", "alternance radiofréquence",
    "apprentissage ingénieur électronique", "alternance ingénieur FPGA", "alternance vérification RTL",
    "alternance IA embarquée", "alternance logiciel embarqué",
]
LIEUX = ["France"]
PAR_PASSAGE = 12         # recherches LinkedIn par vérification (on tourne dans la liste)
MAX_OFFRES = 12          # offres traitées max par vérification (limite gratuite Gemini)
MAX_PAR_HEURE = 12       # liens envoyés max sur 1 heure glissante
ECART_MIN = 7            # minutes entre deux vérifications
DUREE_MAX_MIN = 330
DISPO = "1er novembre 2026"
# ------------------------------------------

ICI = os.path.dirname(os.path.abspath(__file__))
VUES = os.path.join(ICI, "vues.json")
TG = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
CHAT = os.environ["TELEGRAM_CHAT_ID"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}
MODELES = [os.environ.get("GEMINI_MODEL") or "gemini-flash-latest", "gemini-flash-lite-latest"]

def log(*a): print(*a, flush=True)

def tg_msg(text):
    try: requests.post(f"{TG}/sendMessage", data={"chat_id": CHAT, "text": text[:4000], "disable_web_page_preview": True}, timeout=30)
    except Exception as ex: log("Telegram KO", ex)

def tg_doc(path, caption=""):
    with open(path, "rb") as f:
        requests.post(f"{TG}/sendDocument", data={"chat_id": CHAT, "caption": caption[:1000]}, files={"document": f}, timeout=60)

# ---------- LinkedIn (pages publiques, sans connexion) ----------
def chercher(mots, lieu, periode, stage=True):
    params = {"keywords": mots, "location": lieu, "f_TPR": periode, "start": 0}
    if stage: params["f_JT"] = "I"
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + urllib.parse.urlencode(params)
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
            if "PerDay" in r.text: erreurs.append(f"{m} PerDay"); break   # quota du jour épuisé pour ce modèle
            time.sleep(attente)
    raise RuntimeError(" || ".join(erreurs)[-1500:])

PROMPT = """Tu es un expert en recrutement et en optimisation de CV pour les logiciels de filtrage ATS.
Tu aides Sayidina Dicko, étudiant ingénieur en dernière année (Polytech Marseille, Microélectronique et Télécommunications),
qui cherche un STAGE DE FIN D'ÉTUDES de 6 mois OU une ALTERNANCE, disponible dès le {dispo}, mobile partout en France.

Voici une offre LinkedIn :
TITRE : {titre}
ENTREPRISE : {entreprise}
LIEU : {lieu}
DESCRIPTION :
{desc}

Son résumé de base : {resume}
Ses compétences réelles (par catégorie) : {comp}
Ses projets académiques (dans cet ordre, à garder) : {projets}
Ses expériences (dans cet ordre, à garder) : {experiences}

RÈGLES ATS : analyse l'offre pour repérer les compétences clés (hard et soft skills), outils et expressions importants,
et intègre-les NATURELLEMENT dans le résumé, les puces des projets et des expériences et les compétences.
N'INVENTE JAMAIS d'expérience, de projet, de chiffre ou d'outil qu'il n'a pas utilisé : tu reformules seulement ce qui existe
(un outil demandé mais jamais utilisé peut seulement apparaître dans les compétences, jamais dans une puce de projet ou d'expérience).
Mets en avant les chiffres et résultats déjà présents (45 cellules, 27 µW, 3 corners PVT, sans violation DRC...).

Réponds UNIQUEMENT en JSON avec ces clés :
- "score": note de 0 à 10 de l'adéquation entre l'offre et son profil (électronique embarquée, conception de circuits numériques, IA embarquée). 9-10 = ses 3 cibles prioritaires : systèmes / électronique embarqués, conception de circuits numériques (ASIC, FPGA, VHDL/Verilog, RTL, VLSI, vérification), IA embarquée (edge AI, NPU, accélération matérielle). 7-8 = conception analogique, layout, semi-conducteurs, firmware, microcontrôleurs, PCB, RF, traitement du signal sur cible embarquée. 0-4 = logiciel pur, web, UX/UI, data, IT, cloud, mécanique, chimie, marketing, commercial, ou tout ce qui n'est pas de l'électronique.
- "type": "stage" (stage / internship / PFE / fin d'études), "alternance" (alternance / apprentissage / contrat de professionnalisation / work-study) ou "emploi" (CDI, CDD, poste d'ingénieur, jeune diplômé, VIE, freelance, thèse...). Une offre "Ingénieur X" ou "Concepteur X" sans les mots stage/alternance dans le titre ou la description est "emploi".
- "pertinent": true seulement si type vaut "stage" ou "alternance" ET score >= 7 ; sinon false.
- "langue": "fr" si l'offre est en français, sinon "en".
- "domaine": le domaine du stage en quelques mots, repris de l'offre (ex : "conception numérique ASIC/FPGA").
- "ville": la ville de l'offre ; "code_postal": son code postal (5 chiffres en France ; si seul le département est donné, celui de la préfecture ; code postal local si étranger, sinon "") ; "departement": en France "Nom (numéro)" ex. "Loiret (45)", à l'étranger la région/l'état ; "pays": le pays.
- "titre_cv": le titre du CV = EXACTEMENT l'intitulé du poste de l'offre (sans "H/F", sans référence).
- "resume": résumé du CV (3 phrases maximum, moins de 450 caractères, dans la langue de l'offre), qui reprend les mots-clés de l'offre, terminant par : "Recherche un stage de fin d'études de 6 mois en <domaine>, disponible dès le {dispo}." si c'est un stage, ou "Recherche une alternance en <domaine>, disponible dès le {dispo}." si c'est une alternance (ou l'équivalent anglais).
- "projets": tableau de 5 tableaux de puces (1 à 3 puces courtes chacun, moins de 120 caractères par puce ; le CV doit tenir sur UNE seule page), un par projet dans le même ordre, reformulées avec les mots-clés de l'offre, sans rien inventer.
- "experiences": tableau de 5 tableaux de puces, une entrée par expérience dans le même ordre (3 puces courtes pour le stage Senelec, 2 pour le stage AIME, 1 puce courte pour les autres), reformulées avec les mots-clés et soft skills utiles à l'offre, sans rien inventer.
- "competences": 5 à 6 lignes [catégorie, détail] (détail de moins de 160 caractères), dans la langue de l'offre : d'abord les compétences, outils et langages demandés dans l'offre (en reprenant leurs termes exacts), puis ses compétences réelles les plus proches ; la dernière ligne = savoir-être demandés dans l'offre.
- "lettre": une lettre de motivation de 4 paragraphes (tableau de chaînes), dans la langue de l'offre, sans formule d'appel ni signature : pourquoi cette entreprise et ce poste, ce qu'il apporte (en reliant ses projets et compétences aux missions), sa disponibilité dès le {dispo} (pour 6 mois si stage, au rythme de l'alternance si alternance), demande d'entretien. Ton professionnel, concret, pas de phrases creuses.
"""

def adapter(o, desc):
    comp = " ; ".join(f"{c} : {d}" for c, d in D.COMPETENCES_BASE)
    projets = " ; ".join(f"{i}) {t} ({c}) : {' '.join(bl)}" for i, (t, c, bl) in enumerate(D.PROJETS, 1))
    experiences = " ; ".join(f"{i}) {t}, {o_} ({d}) : {' '.join(bl)}" for i, (t, o_, d, bl) in enumerate(D.EXPERIENCE, 1))
    return gemini(PROMPT.format(dispo=DISPO, titre=o["titre"], entreprise=o["entreprise"], lieu=o["lieu"], desc=desc,
                                resume=D.RESUME_BASE, comp=comp, projets=projets, experiences=experiences))

# ---------- état ----------
def charger():
    st = json.load(open(VUES)) if os.path.exists(VUES) else {}
    st.setdefault("vues", []); st.setdefault("tour", 0); st.setdefault("envois", []); st.setdefault("cles", [])
    return st

def sauver(st):
    st["vues"] = st["vues"][-5000:]; st["cles"] = st["cles"][-5000:]
    json.dump(st, open(VUES, "w"))
    subprocess.run("git add offres/vues.json && git commit -qm 'Offres vues' && git pull -q --rebase && git push -q",
                   shell=True, cwd=os.path.dirname(ICI))

MOTS_DOMAINE = ["microélectron", "microelectron", "asic", "fpga", "vhdl", "verilog", "systemverilog", "vlsi", "rtl",
    "analog", "analogique", "circuit", "semi-conduct", "semiconduct", "silicium", "silicon", "layout", "cadence", "synopsys",
    "virtuoso", "innovus", "électroniq", "electroniq", "electronic", "hardware", "embarqu", "embedded", "microcontr",
    "firmware", " rf ", "radiofréquence", "radio-fréquence", "signal", "soc", "chip", "puce", "pcb", "uvm"]

def dans_domaine(o, desc):
    t = (" " + o["titre"] + " " + desc + " ").lower()
    return sum(m in t for m in MOTS_DOMAINE) >= 2

TYPE_STAGE = re.compile(r"\bstag(e|es|iaire)\b|intern(ship)?\b|\bpfe\b|fin d.?[ée]tudes|trainee", re.I)
TYPE_ALT = re.compile(r"alternan(ce|t)|apprenti(e|ssage)?\b|work.?study|contrat de pro", re.I)
EMPLOI = re.compile(r"\bcdi\b|\bcdd\b|senior|confirm[ée]|exp[ée]riment[ée]|jeune dipl[ôo]m|graduate program|\bv\.?i\.?e\b|th[èe]se|phd|freelance", re.I)

def type_offre(o, desc):
    """'stage', 'alternance' ou None (emploi d'ingénieur, CDI...)."""
    t = o["titre"]
    if TYPE_ALT.search(t): return "alternance"
    if TYPE_STAGE.search(t): return "stage"
    if EMPLOI.search(t): return None
    debut = desc[:1500]                                  # titre neutre : on regarde le début de l'annonce
    if EMPLOI.search(debut): return None
    if TYPE_ALT.search(debut): return "alternance"
    if TYPE_STAGE.search(debut): return "stage"
    return None

VIDES = {"stage", "stagiaire", "internship", "intern", "alternance", "alternant", "apprenti", "apprentissage",
         "ingenieur", "engineer", "pfe", "h", "f", "m", "x", "de", "des", "du", "la", "le", "les", "en", "et", "pour",
         "d", "l", "un", "une", "sur", "a", "au", "aux", "the", "of", "and", "for", "in"}

def mots_cle(titre, entreprise):
    t = unicodedata.normalize("NFKD", (titre + " " + entreprise).lower()).encode("ascii", "ignore").decode()
    return {m for m in re.split(r"[^a-z0-9]+", t) if m and m not in VIDES}

def deja_envoyee(o, st):
    """Même offre republiée (autre numéro, titre légèrement modifié) chez la même entreprise."""
    ent = o["entreprise"].lower().strip(); m = mots_cle(o["titre"], "")
    if not m: return False
    for c in st["cles"]:
        titre, _, e = c.rpartition("|")
        if e.strip() != ent: continue
        m2 = mots_cle(titre, "")
        if m2 and len(m & m2) / len(m | m2) >= 0.6: return True
    return False

def nettoie(s): return re.sub(r"[^A-Za-z0-9]+", "_", s)[:40].strip("_")

def verification(st, premiere):
    periode = "r604800"                                  # offres publiées dans les 7 derniers jours (les déjà vues sont ignorées)
    maintenant = time.time()
    st["envois"] = [t for t in st["envois"] if maintenant - t < 3600]
    quota = MAX_PAR_HEURE - len(st["envois"])
    if quota <= 0:
        log(f"::notice::Déjà {MAX_PAR_HEURE} liens envoyés cette heure, on attend."); return
    combos = [(m, l, True) for m in RECHERCHES for l in LIEUX] + [(m, l, False) for m in RECHERCHES_ALT for l in LIEUX]
    debut = st.get("tour", 0) % len(combos)
    lot = [combos[(debut + k) % len(combos)] for k in range(PAR_PASSAGE)]
    st["tour"] = debut + PAR_PASSAGE
    vues = set(st["vues"]); cles = set(st["cles"]); nouvelles = {}
    for mots, lieu, stage in lot:
        for o in chercher(mots, lieu, periode, stage):
            cle = (o["titre"] + "|" + o["entreprise"]).lower()   # même offre republiée sous un autre numéro
            if o["id"] in vues or cle in cles or deja_envoyee(o, st): continue
            nouvelles[o["id"]] = o
        time.sleep(random.uniform(2, 5))
    log(f"::notice::{len(nouvelles)} nouvelle(s) offre(s) sur {len(lot)} recherches")
    traitees = 0; envoyes = 0
    for o in list(nouvelles.values()):
        if traitees >= MAX_OFFRES or envoyes >= quota: break
        st["vues"].append(o["id"])
        desc = description(o["id"])
        if not desc: continue
        if not dans_domaine(o, desc):
            log("Hors domaine (mots-clés) :", o["titre"]); continue
        genre = type_offre(o, desc)
        if not genre:
            log("Pas un stage ni une alternance :", o["titre"]); continue
        time.sleep(7)                                   # reste sous la limite gratuite par minute
        try:
            a = adapter(o, desc)
        except Exception as ex:
            log(f"::warning::Gemini KO {ex}"); st["vues"].remove(o["id"])
            jour = datetime.date.today().isoformat()
            if "PerDay" in str(ex) and st.get("alerte_quota") != jour:
                st["alerte_quota"] = jour
                tg_msg("⚠️ Chercheur d'offres : quota gratuit Gemini du jour épuisé, les CV reprennent demain matin.")
            break
        traitees += 1
        if a.get("type") not in ("stage", "alternance") or not a.get("pertinent") or int(a.get("score", 0) or 0) < 7:
            log("Hors sujet :", o["titre"]); continue
        if "france" not in (a.get("pays", "") + " " + o["lieu"]).lower():
            log("Hors France :", o["titre"], o["lieu"]); continue
        nom = f"{nettoie(o['entreprise'])}_{o['id']}"
        cv, lm = f"/tmp/CV_Sayidina_Dicko_{nom}.pdf", f"/tmp/Lettre_Sayidina_Dicko_{nom}.pdf"
        ville, cp, pays = a.get("ville", ""), a.get("code_postal", ""), a.get("pays", "")
        D.pdfs([(D.cv_html(a.get("resume"), a.get("competences"), ville, cp, pays, a.get("titre_cv") or o["titre"], a.get("experiences"), a.get("projets")), cv),
                (D.lettre_html(a["lettre"], o["entreprise"], o["titre"], ville, cp, pays, a.get("langue", "fr")), lm)])
        genre = a.get("type", genre)
        tg_msg(f"{'🎓 ALTERNANCE' if genre == 'alternance' else '🎯 STAGE'} : {o['titre']}\n🏢 {o['entreprise']}\n📍 {o['lieu']}\n🧩 {a.get('domaine','')} (adéquation {a.get('score','?')}/10)\n\n"
               f"🏠 Adresse à indiquer (comme sur le CV) :\n• Ville : {ville or '-'}\n• Code postal : {cp or '-'}\n"
               f"• Département : {a.get('departement','') or '-'}\n• Pays : {pays or '-'}\n\n👉 Postuler : {o['lien']}")
        tg_doc(cv, "CV adapté"); tg_doc(lm, "Lettre de motivation")
        st["envois"].append(time.time()); st["cles"].append((o["titre"] + "|" + o["entreprise"]).lower()); envoyes += 1
        log(f"::notice::Envoyé : {o['titre']} - {o['entreprise']}")
    sauver(st)

def test_cv():
    """Test : reprend une offre déjà envoyée sur Telegram et renvoie le CV adapté (format ATS)."""
    st = charger(); cles = set(st["cles"])
    for mots in RECHERCHES:
        for o in chercher(mots, "France", "r2592000"):
            if (o["titre"] + "|" + o["entreprise"]).lower() not in cles: continue
            desc = description(o["id"])
            if not desc: continue
            a = adapter(o, desc)
            nom = f"{nettoie(o['entreprise'])}_{o['id']}"
            cv, lm = f"/tmp/CV_Sayidina_Dicko_{nom}.pdf", f"/tmp/Lettre_Sayidina_Dicko_{nom}.pdf"
            ville, cp, pays = a.get("ville", ""), a.get("code_postal", ""), a.get("pays", "")
            D.pdfs([(D.cv_html(a.get("resume"), a.get("competences"), ville, cp, pays, a.get("titre_cv") or o["titre"], a.get("experiences"), a.get("projets")), cv),
                    (D.lettre_html(a["lettre"], o["entreprise"], o["titre"], ville, cp, pays, a.get("langue", "fr")), lm)])
            tg_msg(f"🧪 TEST CV ATS (offre déjà reçue) : {o['titre']}\n🏢 {o['entreprise']}\n📍 {o['lieu']}\n👉 {o['lien']}")
            tg_doc(cv, "CV adapté (format ATS)"); tg_doc(lm, "Lettre de motivation")
            log(f"::notice::Test envoyé : {o['titre']} - {o['entreprise']}"); return
        time.sleep(3)
    log("::warning::Aucune offre déjà envoyée retrouvée sur LinkedIn")

def code_modifie():
    """Vrai si offres.py / documents.py ont changé sur GitHub depuis le lancement (évite de tourner 5 h sur un vieux code)."""
    racine = os.path.dirname(ICI)
    try:
        subprocess.run("git fetch -q origin main", shell=True, cwd=racine, timeout=60)
        r = subprocess.run("git diff --quiet HEAD origin/main -- offres/offres.py offres/documents.py", shell=True, cwd=racine)
        return r.returncode == 1
    except Exception:
        return False

def main():
    if os.environ.get("TEST_CV") == "1":
        test_cv(); return
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
        if code_modifie():
            log("::notice::Nouvelle version du code : on s'arrête, le prochain passage utilisera la nouvelle version."); return
        time.sleep(ECART_MIN * 60)

if __name__ == "__main__":
    main()
