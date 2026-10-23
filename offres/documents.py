"""CV et lettre de motivation de Sayidina Dicko, en PDF.
Seuls la ville, le résumé et les compétences changent d'une offre à l'autre."""
import os, html, datetime
from playwright.sync_api import sync_playwright

TEL = os.environ.get("CV_TEL", "").strip()
EMAIL = os.environ.get("CV_EMAIL", "").strip()
NOM = "Sayidina Dicko"

EXPERIENCE = [
    ("07/2025 –<br>09/2025", "Réparateur d'appareils électroniques", "BFK Net Provence", "Marseille", []),
    ("", "Stagiaire", "AIME", "Toulouse", ["Assisté à la fabrication de cellules photovoltaïques."]),
    ("10/2022 –<br>07/2023", "Professeur particulier", "Méthodik", "Paris", []),
    ("12/2023 –<br>Présent", "Serveur/Barman", "Rodizio Brazil", "Marseille", []),
]
PROJETS = [
    ("Optimisation de l'algorithme de la caméra Pixy2 d'une voiture NXP CUP",
     "Microcontrôleur S32K144-Q100 (projet en cours)."),
    ("Réalisation d'une puce électronique en groupe : microprocesseur 8 bits RISC",
     "Conception de circuits intégrés numériques, programmation de microcontrôleurs."),
]
FORMATION = [
    ("09/2023 –<br>Présent", "Polytech", "Cycle ingénieur, Microélectronique et Télécommunications", "Marseille"),
    ("09/2020 –<br>07/2022", "Lycée Baggio", "CPGE, PTSI", "Lille"),
    ("09/2019 –<br>07/2020", "Lycée KND", "Baccalauréat", ""),
]
LANGUES = [("Français", "langue maternelle", 100), ("Anglais", "B2", 62)]

# Compétences réelles (base) : l'IA les reformule et ajoute ce que l'offre demande.
COMPETENCES_BASE = [
    "Conception numérique VHDL/Verilog", "Flot complet VLSI numérique (RTL → layout)",
    "Synthèse logique (Synopsys Design Vision)", "Placement et routage ASIC (Cadence Innovus)",
    "Vérifications physiques (DRC, LVS, Calibre)", "Analyse temporelle statique (STA)",
    "Conception analogique (Cadence Virtuoso)", "Simulation analogique (AC/DC, transitoire, bruit, Monte Carlo)",
    "Programmation en C, C++ et Python", "Systèmes embarqués et microcontrôleurs (NXP S32K144)",
    "IA / accélération matérielle (NPU)", "Reconnaissance d'images embarquée",
    "QuestaSim", "TCAD Sentaurus", "SolidWorks", "Linux",
]
RESUME_BASE = ("Étudiant ingénieur en microélectronique et télécommunications avec une solide expertise en conception "
               "numérique, VHDL/Verilog, et flot complet VLSI. Maîtrise des outils tels que Synopsys Design Vision et "
               "Cadence Innovus pour la synthèse logique, le placement/routage et les vérifications physiques. Possède "
               "des compétences en programmation C/C++/Python et systèmes embarqués, avec un intérêt pour l'IA et "
               "l'accélération matérielle.")

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Liberation Sans', Arial, sans-serif; font-size: 9.6pt; color: #111; }
.page { width: 210mm; min-height: 297mm; padding: 11mm 14mm 10mm 14mm; }
h1 { text-align: center; font-size: 17pt; margin: 0 0 3px; }
.contact { text-align: center; font-size: 8.8pt; margin-bottom: 9px; }
.contact a { color: #1a56c4; }
.sec { display: grid; grid-template-columns: 37mm 1fr; border-top: 1.2px solid #222; padding: 7px 0 8px; }
.lab { font-size: 8.4pt; color: #555; text-transform: uppercase; letter-spacing: .2px; padding-top: 1px; }
.row { display: grid; grid-template-columns: 37mm 1fr auto; margin: 0 0 7px; }
.row .d { font-size: 8.4pt; color: #555; }
.row b { display: block; }
.row ul { margin: 2px 0 0 18px; padding: 0; }
.resume { line-height: 1.32; }
.proj b { display: block; } .proj div { margin-bottom: 5px; }
.skills { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 16px; }
.lang { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.bar { height: 6px; background: #ddd; margin-top: 3px; } .bar i { display: block; height: 100%; background: #222; }
.lettre { padding: 20mm 22mm; font-size: 10.5pt; line-height: 1.45; }
.lettre p { margin: 0 0 9px; text-align: justify; }
"""
e = html.escape

def adresse(ville, cp, pays):
    return ", ".join(x for x in [ville, cp, pays] if x)

def contact_html(ville, cp, pays):
    parts = [e(adresse(ville, cp, pays))]
    if TEL: parts.append(e(TEL))
    if EMAIL: parts.append(f'<a href="mailto:{e(EMAIL)}">{e(EMAIL)}</a>')
    return ", ".join(parts)

def cv_html(resume, competences, ville, cp, pays):
    exp = "".join(
        f'<div class="row"><div class="d">{d}</div><div><b>{e(t)}</b>{e(o)}'
        + (f"<ul>{''.join(f'<li>{e(x)}</li>' for x in bl)}</ul>" if bl else "")
        + f'</div><div>{e(v)}</div></div>' for d, t, o, v, bl in EXPERIENCE)
    form = "".join(f'<div class="row"><div class="d">{d}</div><div><b>{e(t)}</b>{e(o)}</div><div>{e(v)}</div></div>'
                   for d, t, o, v in FORMATION)
    proj = "".join(f"<div><b>{e(t)}</b>{e(s)}</div>" for t, s in PROJETS)
    comp = "".join(f"<div>{e(c)}</div>" for c in competences)
    lang = "".join(f'<div><b>{e(n)}</b> ({e(l)})<div class="bar"><i style="width:{p}%"></i></div></div>' for n, l, p in LANGUES)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="page">
<h1>{NOM}</h1><div class="contact">{contact_html(ville, cp, pays)}</div>
<div class="sec"><div class="lab">Résumé</div><div class="resume">{e(resume)}</div></div>
<div class="sec" style="display:block"><div class="lab" style="margin-bottom:6px">Expérience<br>professionnelle</div>{exp}</div>
<div class="sec" style="display:block"><div class="lab" style="margin-bottom:6px">Formation</div>{form}</div>
<div class="sec"><div class="lab">Projets<br>académiques</div><div class="proj">{proj}</div></div>
<div class="sec"><div class="lab">Connaissances</div><div class="skills">{comp}</div></div>
<div class="sec"><div class="lab">Langues</div><div class="lang">{lang}</div></div>
</div></body></html>"""

def lettre_html(paragraphes, entreprise, poste, ville, cp, pays, langue="fr"):
    mois = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    d = datetime.date.today()
    date = f"{ville or 'Marseille'}, le {d.day} {mois[d.month-1]} {d.year}" if langue == "fr" else d.strftime("%B %d, %Y")
    objet = (f"Objet : Candidature au stage de fin d'études – {poste}" if langue == "fr"
             else f"Subject: Application for the internship – {poste}")
    salut = "Madame, Monsieur," if langue == "fr" else "Dear Hiring Manager,"
    fin = "Sayidina Dicko"
    corps = "".join(f"<p>{e(p)}</p>" for p in paragraphes)
    coord = "<br>".join(e(x) for x in [NOM, adresse(ville, cp, pays), TEL, EMAIL] if x)
    return f"""<!doctype html><html lang="{langue}"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="lettre">
<div>{coord}</div><div style="margin:14px 0 0 auto;width:60%;text-align:right"><b>{e(entreprise)}</b></div>
<div style="text-align:right;margin:14px 0 18px">{e(date)}</div>
<p><b>{e(objet)}</b></p><p>{salut}</p>{corps}<p style="margin-top:18px">{e(fin)}</p></div></body></html>"""

def pdfs(jobs):
    """jobs : liste de (html, chemin_pdf)."""
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        for h, out in jobs:
            pg.set_content(h); pg.pdf(path=out, format="A4", print_background=True)
        b.close()
