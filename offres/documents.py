"""CV (format ATS) et lettre de motivation de Sayidina Dicko, en PDF.

CV compatible ATS : une seule colonne, lecture linéaire, aucun tableau / colonne / icône / zone de texte,
puces standards, titres de sections universels. Pour chaque offre, l'IA adapte : le titre (= intitulé du poste),
le résumé, les puces des expériences et des projets (mots-clés de l'offre, sans rien inventer) et les compétences."""
import os, html, datetime
from playwright.sync_api import sync_playwright

TEL = os.environ.get("CV_TEL", "").strip()
EMAIL = os.environ.get("CV_EMAIL", "").strip()
NOM = "Sayidina Dicko"
TITRE_BASE = "Stage de fin d'études – Systèmes embarqués, IA et conception de circuits numériques"
MOBILITE = "Disponible dès le 1er novembre 2026 – Mobile partout en France"

# (intitulé, entreprise / lieu, dates, puces de base)
EXPERIENCE = [
    ("Réparateur d'appareils électroniques", "BFK Net Provence, Marseille", "Juillet 2025 à septembre 2025",
     ["Diagnostic de pannes et réparation d'appareils électroniques."]),
    ("Stage Technicien Supérieur en Électronique", "Senelec, Dakar (Sénégal)", "Juin 2023 à août 2023",
     ["Conception et test de circuits pour systèmes de distribution électrique.",
      "Tests et diagnostics sur des équipements électroniques pour identifier et résoudre les dysfonctionnements.",
      "Collaboration avec l'équipe d'ingénierie pour l'optimisation des performances des systèmes électroniques."]),
    ("Stagiaire", "AIME, Toulouse", "Stage",
     ["Assistance à la fabrication de cellules photovoltaïques."]),
    ("Professeur particulier", "Méthodik, Paris", "Octobre 2022 à juillet 2023",
     ["Cours particuliers : pédagogie et transmission des savoirs."]),
    ("Serveur / Barman", "Rodizio Brazil, Marseille", "Décembre 2023 à aujourd'hui",
     ["Travail en équipe sous pression, relation client."]),
]
# (titre, contexte, puces de base) — projets réellement réalisés
PROJETS = [
    ("Conception d'un bloc CRC-8 en ASIC, du VHDL au layout", "Projet individuel, 5e année, technologie AMS 0,35 µm",
     ["Description VHDL bit-série (polynôme 0x07) et testbench auto-vérifiant sous ModelSim.",
      "Synthèse sous Synopsys Design Vision : 45 cellules, 27 µW, timing validé sur 3 corners PVT.",
      "Placement-routage sous Cadence Innovus (floorplan, CTS) sans violation DRC ni antenne ; vérification post-P&R avec back-annotation SDF."]),
    ("Microprocesseur RISC 8 bits", "Projet de groupe",
     ["Conception d'une puce numérique complète : RTL, synthèse et implémentation physique."]),
    ("Conception sur FPGA Xilinx", "4e année",
     ["Description VHDL, simulation comportementale, synthèse et implémentation sous Vivado, test sur carte."]),
    ("Traitement d'image embarqué – caméra Pixy2, voiture autonome NXP CUP", "Projet en cours",
     ["Optimisation de l'algorithme de vision en C sur microcontrôleur NXP S32K144-Q100, sous contrainte de temps réel."]),
    ("Reconnaissance d'images par IA embarquée", "Carte DBX Modèle A avec NPU intégré",
     ["Classification d'images en 3 classes (avion, bateau, voiture) sur cible embarquée."]),
]
FORMATION = [
    ("Cycle ingénieur – Microélectronique et Télécommunications", "Polytech Marseille", "Septembre 2023 à aujourd'hui"),
    ("CPGE PTSI (classe préparatoire scientifique)", "Lycée Baggio, Lille", "Septembre 2020 à juillet 2022"),
    ("Baccalauréat", "Lycée KND", "Septembre 2019 à juillet 2020"),
]
LANGUES = "Français : langue maternelle | Anglais : B2"

# Compétences réelles (base), par catégorie : l'IA les réordonne et ajoute les mots-clés de l'offre.
COMPETENCES_BASE = [
    ("Conception numérique", "VHDL, Verilog, flot ASIC complet (RTL → layout), Synopsys Design Vision, Cadence Innovus (P&R, CTS), DRC / LVS, analyse temporelle statique (STA), scripting Tcl (SDC)"),
    ("Conception analogique", "Cadence Virtuoso (schéma, layout), simulation DC / AC / transitoire / bruit / Monte Carlo, Sentaurus TCAD"),
    ("FPGA et vérification", "Xilinx Vivado, Intel Quartus, HLS IP Gen Compiler Altera, ModelSim / QuestaSim, testbenchs auto-vérifiants"),
    ("Systèmes embarqués et IA", "C, C++, Python, microcontrôleurs NXP S32K144, traitement d'image et du signal, IA embarquée sur NPU"),
    ("Outils", "Linux, Git, SolidWorks"),
    ("Savoir-être", "Rigueur, autonomie, esprit d'analyse, travail en équipe, rédaction technique en anglais"),
]
RESUME_BASE = ("Étudiant ingénieur en dernière année de Microélectronique et Télécommunications à Polytech Marseille. "
               "Maîtrise du flot complet de conception de circuits intégrés, du VHDL au layout (synthèse, placement-routage, "
               "DRC/LVS, STA), de la conception analogique sous Cadence Virtuoso et du développement FPGA sous Vivado. "
               "Compétences en programmation C/C++/Python, systèmes embarqués et IA embarquée. "
               "Recherche un stage de fin d'études de 6 mois en systèmes embarqués, IA et conception de circuits numériques, "
               "disponible dès le 1er novembre 2026.")

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: Arial, 'Liberation Sans', sans-serif; font-size: 9.4pt; color: #000; line-height: 1.27; }
.page { width: 210mm; padding: 10mm 15mm 9mm 15mm; }
h1 { font-size: 18pt; margin: 0; }
.titre { font-size: 11.5pt; font-weight: bold; margin: 2px 0 3px; }
.contact { margin: 0 0 2px; }
h2 { font-size: 11pt; text-transform: uppercase; border-bottom: 1px solid #000; margin: 8px 0 4px; padding-bottom: 1px; }
h3 { font-size: 10pt; margin: 5px 0 0; }
.m { margin: 0 0 1px; }
ul { margin: 1px 0 0 17px; padding: 0; } li { margin: 0 0 1px; }
p { margin: 0; }
.lettre { padding: 20mm 22mm; font-size: 10.5pt; line-height: 1.45; }
.lettre p { margin: 0 0 9px; text-align: justify; }
"""
e = html.escape

def adresse(ville, cp, pays):
    return ", ".join(x for x in [ville, cp, pays] if x)

def ul(items):
    return f"<ul>{''.join(f'<li>{e(x)}</li>' for x in items if x)}</ul>" if items else ""

def cv_html(resume, competences, ville, cp, pays, titre=None, experiences=None, projets=None):
    """competences : liste de [catégorie, détail] (ou liste de chaînes, ancien format).
    experiences / projets : listes de listes de puces, dans le même ordre que EXPERIENCE / PROJETS (optionnel)."""
    contact = " | ".join(x for x in [adresse(ville, cp, pays), TEL, EMAIL] if x)
    exp = "".join(
        f"<h3>{e(t)}</h3><p class='m'>{e(o)} | {e(d)}</p>"
        + ul((experiences[i] if experiences and i < len(experiences) and experiences[i] else bl))
        for i, (t, o, d, bl) in enumerate(EXPERIENCE))
    form = "".join(f"<h3>{e(t)}</h3><p class='m'>{e(o)} | {e(d)}</p>" for t, o, d in FORMATION)
    proj = "".join(
        f"<h3>{e(t)}</h3><p class='m'>{e(c)}</p>"
        + ul((projets[i] if projets and i < len(projets) and projets[i] else bl))
        for i, (t, c, bl) in enumerate(PROJETS))
    comp_items = []
    for c in (competences or COMPETENCES_BASE):
        if isinstance(c, (list, tuple)) and len(c) == 2: comp_items.append(f"{c[0]} : {c[1]}")
        elif isinstance(c, dict): comp_items.append(f"{c.get('categorie', '')} : {c.get('detail', '')}")
        else: comp_items.append(str(c))
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>CV {NOM}</title><style>{CSS}</style></head><body><div class="page">
<h1>{NOM}</h1>
<p class="titre">{e(titre or TITRE_BASE)}</p>
<p class="contact">{e(contact)}</p>
<p class="contact">{e(MOBILITE)}</p>
<h2>Résumé</h2><p>{e(resume or RESUME_BASE)}</p>
<h2>Formation</h2>{form}
<h2>Projets académiques</h2>{proj}
<h2>Expérience professionnelle</h2>{exp}
<h2>Compétences</h2>{ul(comp_items)}
<h2>Langues</h2><p>{e(LANGUES)}</p>
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
    """jobs : liste de (html, chemin_pdf). Le CV est ramené à une page si besoin (réduction légère)."""
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        for h, out in jobs:
            pg.set_content(h)
            haut = pg.evaluate("document.body.scrollHeight")
            echelle = min(1.0, 1122 / haut) if haut else 1.0          # 1122 px ≈ hauteur d'une page A4
            pg.pdf(path=out, format="A4", print_background=True, scale=max(0.8, echelle))
        b.close()
