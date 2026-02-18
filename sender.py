"""
=============================================================
  ALTERNANCE BOT - Kader BELEM
  Script d'envoi automatique de candidatures par email
=============================================================
  PRÉREQUIS :
    pip install pandas openpyxl
  
  CONFIGURATION GMAIL :
    1. Aller sur https://myaccount.google.com/apppasswords
    2. Créer un "Mot de passe d'application" (type : Courrier)
    3. Copier le code 16 caractères dans GMAIL_APP_PASSWORD ci-dessous
    4. Activer la validation en 2 étapes si pas encore fait
=============================================================
"""

import smtplib
import os
import json
import csv
import time
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
import pandas as pd

# ─── CONFIGURATION ───────────────────────────────────────────
GMAIL_ADDRESS   = "Kaderbelem428@gmail.com"
GMAIL_APP_PASSWORD = "rjij owlt yjvo oarm"   # ← À remplacer
CV_PATH         = CV_PATH = "CV_Kader_Belem.pdf"               # ← Chemin vers votre CV PDF
TRACKER_FILE    = "candidatures.json"
DELAY_MIN       = 30   # Délai min entre emails (secondes) - évite le spam
DELAY_MAX       = 90   # Délai max entre emails (secondes)
# ─────────────────────────────────────────────────────────────

SIGNATURE = """
--
Kader BELEM
BTS CIEL – Cybersécurité, Informatique et Réseaux
📱 06 61 40 29 98
🌐 https://kablm.github.io/portfolio-kader
"""

# Template de lettre - personnalisé automatiquement par entreprise
def generate_email_body(entreprise: dict) -> str:
    nom        = str(entreprise.get("nom") or "l'entreprise").strip()
    secteur    = str(entreprise.get("secteur") or "l'informatique").strip()
    ville      = str(entreprise.get("ville") or "Nantes").strip()
    raison     = str(entreprise.get("raison_specifique") or
                   f"votre expertise dans {secteur} et votre présence à {ville}").strip()

    return f"""Madame, Monsieur,

Actuellement en BTS CIEL (Cybersécurité, Informatique et Réseaux, Électronique) \
au Lycée de l'Hyrôme, je me permets de vous adresser ma candidature spontanée \
pour un poste de Technicien Systèmes et Réseaux en alternance au sein de {nom}, \
pour la rentrée de septembre 2026.

Cette réorientation vers les réseaux et systèmes n'est pas le fruit d'un hasard : \
après deux années en développement logiciel (BTS SIO option SLAM), j'ai découvert \
ma véritable passion lors de mes stages en infrastructure IT. \
Cette double compétence dev/infra constitue aujourd'hui un atout concret : \
je comprends autant les contraintes réseau que les besoins applicatifs, \
et je suis capable de créer des scripts Python pour automatiser des tâches d'administration.

Ce qui m'attire particulièrement chez {nom} : {raison}. \
Vos activités correspondent exactement à l'environnement technique dans lequel \
je souhaite évoluer et progresser.

Mes 6 stages m'ont permis d'acquérir une expérience concrète en :
• Administration système : Windows Server 2019/2022, Active Directory, GPO, Ubuntu Server
• Réseaux : architecture LAN, DHCP, DNS, firewalling, câblage
• Outils : VMware, VirtualBox, Docker, GLPI
• Développement : Python, SQL, PHP, Git

Titulaire du permis B et véhiculé, je suis disponible pour des interventions sur site.

Je serais très heureux de vous rencontrer pour vous présenter ma motivation.
Mon portfolio est disponible à l'adresse : https://kablm.github.io/portfolio-kader

Dans l'attente de votre réponse, veuillez agréer, Madame, Monsieur, \
l'expression de mes salutations les plus respectueuses.

Kader BELEM
{SIGNATURE}"""

def generate_subject(entreprise: dict) -> str:
    nom = entreprise.get("nom", "votre entreprise")
    return f"Candidature spontanée – Alternance Technicien Systèmes & Réseaux – Kader BELEM"

# ─── TRACKER ─────────────────────────────────────────────────

def load_tracker() -> dict:
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"candidatures": []}

def save_tracker(data: dict):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def already_sent(tracker: dict, entreprise_email: str) -> bool:
    for c in tracker["candidatures"]:
        if c["email"] == entreprise_email and c["statut"] != "erreur":
            return True
    return False

def add_to_tracker(tracker: dict, entreprise: dict, statut: str, erreur: str = ""):
    tracker["candidatures"].append({
        "id": len(tracker["candidatures"]) + 1,
        "date_envoi": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "entreprise": str(entreprise.get("nom") or ""),
        "email": str(entreprise.get("email") or ""),
        "ville": str(entreprise.get("ville") or ""),
        "secteur": str(entreprise.get("secteur") or ""),
        "statut": statut,
        "erreur": erreur,
        "date_relance": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
        "reponse": "",
        "notes": ""
    })

# ─── ENVOI EMAIL ─────────────────────────────────────────────

def send_email(entreprise: dict, dry_run: bool = False) -> tuple[bool, str]:
    """Envoie un email de candidature. dry_run=True pour tester sans envoyer."""
    
    dest_email = str(entreprise.get("email") or "").strip()
    if not dest_email:
        return False, "Pas d'email renseigné"

    subject = generate_subject(entreprise)
    body    = generate_email_body(entreprise)

    if dry_run:
        print(f"\n{'='*60}")
        print(f"[DRY RUN] À : {dest_email}")
        print(f"Objet : {subject}")
        print(f"Corps :\n{body[:300]}...")
        print(f"Pièce jointe CV : {CV_PATH}")
        return True, "dry_run"

    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = dest_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Joindre le CV si disponible
        if os.path.exists(CV_PATH):
            with open(CV_PATH, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                          f'attachment; filename="CV_Kader_BELEM.pdf"')
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, dest_email, msg.as_string())

        return True, "envoyé"

    except smtplib.SMTPAuthenticationError:
        return False, "Erreur authentification Gmail – vérifiez GMAIL_APP_PASSWORD"
    except smtplib.SMTPRecipientsRefused:
        return False, f"Email refusé par le serveur : {dest_email}"
    except Exception as e:
        return False, str(e)

# ─── CHARGEMENT LISTE ENTREPRISES ────────────────────────────

def load_companies(filepath: str) -> list[dict]:
    """
    Charge les entreprises depuis un fichier CSV ou JSON.
    Format CSV attendu :
      nom,email,ville,secteur,raison_specifique
    """
    if not os.path.exists(filepath):
        print(f"❌ Fichier introuvable : {filepath}")
        return []

    ext = filepath.lower().split(".")[-1]

    if ext == "json":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("entreprises", [])

    elif ext in ("csv", "xlsx", "xls"):
        if ext == "csv":
            df = pd.read_csv(filepath, encoding="utf-8")
        else:
            df = pd.read_excel(filepath)
        return df.to_dict(orient="records")

    else:
        print(f"❌ Format non supporté : {ext} (utilisez .csv, .xlsx ou .json)")
        return []

# ─── CAMPAGNE D'ENVOI ────────────────────────────────────────

def run_campaign(companies_file: str, dry_run: bool = False, limit: int = None):
    """Lance une campagne d'envoi de candidatures."""

    print(f"\n{'='*60}")
    print("  ALTERNANCE BOT – Kader BELEM")
    print(f"  Mode : {'DRY RUN (test)' if dry_run else '🚀 ENVOI RÉEL'}")
    print(f"{'='*60}\n")

    companies = load_companies(companies_file)
    if not companies:
        print("Aucune entreprise chargée. Arrêt.")
        return

    tracker = load_tracker()
    sent_count = 0
    skip_count = 0
    error_count = 0

    for i, company in enumerate(companies):
        if limit and sent_count >= limit:
            print(f"\n⏹ Limite de {limit} envois atteinte.")
            break

        email = str(company.get("email") or "").strip()
        nom   = str(company.get("nom") or f"Entreprise {i+1}").strip()

        if not email:
            print(f"⚠️  [{i+1}] {nom} – pas d'email, ignorée")
            skip_count += 1
            continue

        if already_sent(tracker, email):
            print(f"⏭  [{i+1}] {nom} – déjà contactée, ignorée")
            skip_count += 1
            continue

        print(f"📧 [{i+1}] Envoi à {nom} ({email})...", end=" ", flush=True)
        success, message = send_email(company, dry_run=dry_run)

        if success:
            print(f"✅ {message}")
            add_to_tracker(tracker, company, "envoyé")
            sent_count += 1
        else:
            print(f"❌ {message}")
            add_to_tracker(tracker, company, "erreur", message)
            error_count += 1

        save_tracker(tracker)

        # Délai aléatoire entre les envois (évite le blocage Gmail)
        if not dry_run and i < len(companies) - 1:
            delay = random.randint(DELAY_MIN, DELAY_MAX)
            print(f"   ⏳ Attente {delay}s avant le prochain envoi...")
            time.sleep(delay)

    # Résumé
    print(f"\n{'='*60}")
    print(f"  RÉSUMÉ DE LA CAMPAGNE")
    print(f"  ✅ Envoyés    : {sent_count}")
    print(f"  ⏭  Ignorés   : {skip_count}")
    print(f"  ❌ Erreurs   : {error_count}")
    print(f"  📄 Tracker   : {TRACKER_FILE}")
    print(f"{'='*60}\n")

# ─── RELANCES ────────────────────────────────────────────────

def check_relances():
    """Affiche les candidatures à relancer (pas de réponse depuis 14 jours)."""
    tracker = load_tracker()
    today = datetime.now().strftime("%Y-%m-%d")
    
    to_relance = [
        c for c in tracker["candidatures"]
        if c["statut"] == "envoyé"
        and c.get("reponse", "") == ""
        and c.get("date_relance", "9999-99-99") <= today
    ]

    if not to_relance:
        print("✅ Aucune relance nécessaire aujourd'hui.")
        return

    print(f"\n🔔 {len(to_relance)} candidature(s) à relancer :\n")
    for c in to_relance:
        print(f"  • {c['entreprise']} ({c['email']}) – envoyé le {c['date_envoi']}")

# ─── STATS ───────────────────────────────────────────────────

def show_stats():
    """Affiche les statistiques des candidatures."""
    tracker = load_tracker()
    candidatures = tracker["candidatures"]
    
    if not candidatures:
        print("Aucune candidature enregistrée.")
        return

    total    = len(candidatures)
    envoyes  = sum(1 for c in candidatures if c["statut"] == "envoyé")
    reponses = sum(1 for c in candidatures if c.get("reponse"))
    erreurs  = sum(1 for c in candidatures if c["statut"] == "erreur")

    print(f"\n📊 STATISTIQUES")
    print(f"   Total candidatures  : {total}")
    print(f"   Envoyées            : {envoyes}")
    print(f"   Réponses reçues     : {reponses}")
    print(f"   Taux de réponse     : {reponses/envoyes*100:.1f}%" if envoyes else "   Taux de réponse     : -")
    print(f"   Erreurs             : {erreurs}")

# ─── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
Usage :
  python sender.py test      entreprises.csv    # Test sans envoyer
  python sender.py send      entreprises.csv    # Envoyer pour de vrai
  python sender.py send      entreprises.csv 5  # Envoyer max 5
  python sender.py relances                     # Voir les relances
  python sender.py stats                        # Voir les stats
        """)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "test" and len(sys.argv) >= 3:
        run_campaign(sys.argv[2], dry_run=True)
    elif cmd == "send" and len(sys.argv) >= 3:
        limit = int(sys.argv[3]) if len(sys.argv) >= 4 else None
        run_campaign(sys.argv[2], dry_run=False, limit=limit)
    elif cmd == "relances":
        check_relances()
    elif cmd == "stats":
        show_stats()
    else:
        print("Commande inconnue. Lancez sans argument pour voir l'aide.")