#!/usr/bin/env python3
"""
=============================================================
  EMAIL REPLY CHECKER - Kader BELEM
  Récupère les réponses aux candidatures depuis Gmail
  et met à jour automatiquement candidatures.json
=============================================================
  PRÉREQUIS :
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

  CONFIGURATION (PREMIÈRE FOIS) :
    1. Aller sur https://console.cloud.google.com
    2. Créer un projet "Alternance Bot"
    3. Activer Gmail API
    4. Créer des identifiants OAuth 2.0 (Application de bureau)
    5. Télécharger le JSON et le renommer en credentials.json
    6. Le placer dans le même dossier que ce script

  UTILISATION :
    python check_replies.py              # Vérifier les nouveaux emails
    python check_replies.py --all        # Re-scanner tous les emails
    python check_replies.py --days 30    # Scanner les 30 derniers jours
=============================================================
"""

import os
import json
import re
import argparse
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# Google API
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("❌ Modules Google manquants. Installez-les avec :")
    print("   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    exit(1)

# ─── CONFIGURATION ───────────────────────────────────────────

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE = 'gmail_token.json'
CREDENTIALS_FILE = 'credentials.json'
TRACKER_FILE = 'candidatures.json'

POSITIVE_KEYWORDS = [
    'entretien', 'rdv', 'rendez-vous', 'rencontrer', 'disponible', 
    'intéressé', 'profil', 'cv', 'curriculum', 'poste', 'alternance',
    'planning', 'interview', 'échange', 'discuter', 'présenter',
    'proposition', 'opportunité', 'candidature retenue', 'suite favorable'
]

NEGATIVE_KEYWORDS = [
    'malheureusement', 'regret', 'ne correspond pas', 'ne convient pas',
    'ne sommes pas en mesure', 'autre profil', 'autre candidat',
    'déjà pourvu', 'clos', 'refus', 'ne pas donner suite',
    'ne retenons pas', 'profil ne correspond pas'
]

# ─── AUTHENTIFICATION GMAIL ──────────────────────────────────

def authenticate_gmail():
    """Authentifie avec Gmail API et retourne le service."""
    creds = None
    
    # Token existant
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # Rafraîchir ou obtenir nouveau token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"\n❌ Fichier {CREDENTIALS_FILE} introuvable !")
                print("\n📋 ÉTAPES POUR CONFIGURER :")
                print("   1. Aller sur https://console.cloud.google.com")
                print("   2. Créer un projet")
                print("   3. Activer Gmail API")
                print("   4. Créer des identifiants OAuth 2.0 (Application de bureau)")
                print("   5. Télécharger le JSON et le renommer en credentials.json")
                print("   6. Le placer dans ce dossier\n")
                exit(1)
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Sauvegarder le token
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)

# ─── CHARGEMENT TRACKER ──────────────────────────────────────

def load_tracker():
    """Charge candidatures.json."""
    if not os.path.exists(TRACKER_FILE):
        return {"candidatures": []}
    with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_tracker(data):
    """Sauvegarde candidatures.json."""
    with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── ANALYSE EMAIL ───────────────────────────────────────────

def classify_response(subject, body):
    """Classifie un email comme positif, négatif ou neutre."""
    text = (subject + ' ' + body).lower()
    
    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    
    if neg_count > pos_count and neg_count >= 2:
        return "réponse négative"
    elif pos_count > neg_count and pos_count >= 2:
        return "réponse positive"
    else:
        return "réponse reçue"

def extract_body(payload):
    """Extrait le corps du message Gmail."""
    body = ""
    
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    import base64
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                    break
    elif 'body' in payload and 'data' in payload['body']:
        import base64
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    
    return body[:500]  # Premiers 500 caractères

def get_header(headers, name):
    """Récupère un header spécifique."""
    for h in headers:
        if h['name'].lower() == name.lower():
            return h['value']
    return ''

# ─── RÉCUPÉRATION EMAILS ─────────────────────────────────────

def fetch_replies(service, days=14, fetch_all=False):
    """Récupère les réponses reçues depuis X jours."""
    
    tracker = load_tracker()
    sent_emails = {c['email'].lower(): c for c in tracker['candidatures'] if c.get('email')}
    
    if not sent_emails:
        print("❌ Aucune candidature envoyée dans le tracker.")
        return
    
    # Construction de la requête Gmail
    query_parts = []
    
    # Limiter aux emails des entreprises contactées
    if len(sent_emails) <= 10:
        # Si peu d'entreprises, chercher directement leurs emails
        for email in list(sent_emails.keys())[:10]:
            query_parts.append(f'from:{email}')
        query = ' OR '.join(query_parts)
    else:
        # Sinon, chercher tous les emails reçus récemment
        if not fetch_all:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
            query = f'after:{date_limit} -from:me'
        else:
            query = '-from:me'
    
    print(f"\n🔍 Recherche des réponses (derniers {days} jours)...\n")
    
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            print("✅ Aucun nouvel email trouvé.")
            return
        
        print(f"📧 {len(messages)} emails trouvés, analyse en cours...\n")
        
        updated_count = 0
        new_replies = 0
        
        for msg_data in messages:
            msg = service.users().messages().get(
                userId='me',
                id=msg_data['id'],
                format='full'
            ).execute()
            
            headers = msg['payload']['headers']
            from_email = get_header(headers, 'From')
            subject = get_header(headers, 'Subject')
            date_str = get_header(headers, 'Date')
            
            # Extraire l'email de l'expéditeur
            email_match = re.search(r'<(.+?)>', from_email)
            sender_email = (email_match.group(1) if email_match else from_email).lower().strip()
            
            # Vérifier si c'est une entreprise qu'on a contactée
            if sender_email not in sent_emails:
                continue
            
            candidature = sent_emails[sender_email]
            
            # Si déjà une réponse enregistrée, ignorer
            if candidature.get('reponse') and not fetch_all:
                continue
            
            # Extraire le corps
            body = extract_body(msg['payload'])
            
            # Classifier
            classification = classify_response(subject, body)
            
            # Formater la date
            try:
                date_obj = parsedate_to_datetime(date_str)
                date_formatted = date_obj.strftime('%Y-%m-%d %H:%M')
            except:
                date_formatted = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Mettre à jour
            candidature['statut'] = classification
            candidature['reponse'] = f"Reçu le {date_formatted}"
            candidature['notes'] = f"{subject}\n\n{body[:300]}..."
            
            icon = "🎉" if "positive" in classification else "❌" if "négative" in classification else "📨"
            print(f"{icon} {candidature['entreprise']}")
            print(f"   De: {sender_email}")
            print(f"   Objet: {subject}")
            print(f"   Type: {classification}\n")
            
            updated_count += 1
            if not candidature.get('reponse_checked'):
                new_replies += 1
                candidature['reponse_checked'] = True
        
        if updated_count > 0:
            save_tracker(tracker)
            print(f"\n{'='*60}")
            print(f"✅ Tracker mis à jour !")
            print(f"   Nouvelles réponses : {new_replies}")
            print(f"   Total mis à jour   : {updated_count}")
            print(f"{'='*60}\n")
        else:
            print("ℹ️  Aucune nouvelle réponse détectée.\n")
    
    except Exception as e:
        print(f"❌ Erreur : {e}")

# ─── MAIN ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Vérifie les réponses Gmail")
    parser.add_argument('--days', type=int, default=14, help="Nombre de jours à scanner (défaut: 14)")
    parser.add_argument('--all', action='store_true', help="Scanner tous les emails (ignore --days)")
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("  EMAIL REPLY CHECKER - Kader BELEM")
    print("="*60)
    
    service = authenticate_gmail()
    fetch_replies(service, days=args.days, fetch_all=args.all)

if __name__ == '__main__':
    main()
