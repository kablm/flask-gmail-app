# server_env.py
import os
from flask import Flask, send_from_directory, jsonify
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__, static_folder='.')

# -----------------------------
# Récupérer les secrets depuis les variables d'environnement
# -----------------------------
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN")

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Vérification rapide des variables d'environnement
if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    raise Exception("⚠️ Une ou plusieurs variables d'environnement sont manquantes !")

# -----------------------------
# Endpoint pour récupérer Gmail
# -----------------------------
@app.route('/fetch_gmail')
def fetch_gmail():
    try:
        # Créer les credentials depuis les variables d'environnement
        creds = Credentials(
            token=None,
            refresh_token=REFRESH_TOKEN,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES
        )

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
# Servir le front-end
# -----------------------------
@app.route('/')
@app.route('/<path:path>')
def serve(path='index.html'):
    return send_from_directory('.', path)

# -----------------------------
# Lancer le serveur
# -----------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8765))  # Render fournit la variable PORT
    app.run(host='0.0.0.0', port=port, debug=True)
