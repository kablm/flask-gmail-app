# server_complete.py
import os
import json
from flask import Flask, jsonify, send_from_directory
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# -----------------------------
# Configuration
# -----------------------------
APP_PORT = 8766
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDENTIALS_FILE = 'credentials.json'  # Client ID / secret téléchargé depuis Google Cloud
TOKEN_FILE = 'token.json'

app = Flask(__name__, static_folder='.')

# -----------------------------
# Fonction pour obtenir des credentials
# -----------------------------
def get_credentials():
    creds = None
    # Si token existe déjà, on le charge
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Sinon, on lance OAuth pour créer le token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=APP_PORT)  # ✅ même port que Flask
        # Sauvegarde du token
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

# -----------------------------
# Endpoint pour récupérer les emails
# -----------------------------
@app.route('/fetch_gmail')
def fetch_gmail():
    try:
        creds = get_credentials()
        service = build('gmail', 'v1', credentials=creds)

        # Récupère les 20 derniers emails
        results = service.users().messages().list(userId='me', maxResults=20).execute()
        messages = results.get('messages', [])

        emails = []
        for msg in messages:
            m = service.users().messages().get(
                userId='me', 
                id=msg['id'], 
                format='metadata', 
                metadataHeaders=['From','Subject','Date']
            ).execute()
            headers = {h['name']: h['value'] for h in m['payload']['headers']}
            emails.append({
                'from': headers.get('From'),
                'subject': headers.get('Subject'),
                'date': headers.get('Date')
            })

        return jsonify({"emails": emails})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------
# Servir le front-end (index.html ou autre)
# -----------------------------
@app.route('/')
@app.route('/<path:path>')
def serve(path='index.html'):
    return send_from_directory('.', path)

# -----------------------------
# Lancer le serveur
# -----------------------------
if __name__ == '__main__':
    print(f"🚀 Serveur démarré sur http://127.0.0.1:{APP_PORT}")
    app.run(host='127.0.0.1', port=APP_PORT, debug=True)
