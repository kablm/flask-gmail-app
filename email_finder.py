#!/usr/bin/env python3
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""
email_finder.py — Trouve automatiquement les emails manquants dans un CSV
Stratégie (dans l'ordre) :
  1. Google search "nom entreprise + contact + email"
  2. Scrape du site web de l'entreprise (page contact/accueil)
  3. Hunter.io API (50 crédits/mois gratuits)

Usage :
  python email_finder.py entreprises_alternance_it.csv
  python email_finder.py entreprises_alternance_it.csv --hunter-key VOTRE_CLE
  python email_finder.py entreprises_alternance_it.csv --limit 20
"""

import csv, re, sys, time, random, argparse, json, os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/121.0.0.0 Safari/537.36"
}
TIMEOUT = 8
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.I)

# Emails à ignorer (génériques sans valeur)
BLACKLIST_PATTERNS = [
    r"@duckduckgo\.", r"error-lite", r"error@",
    r"@example\.", r"@test\.", r"noreply", r"no-reply", r"donotreply",
    r"@sentry\.", r"@github\.", r"@wordpress", r"\.png@", r"\.jpg@",
    r"wixpress", r"@w3\.", r"schema\.org", r"@cloudflare", r"@google\.",
    r"@facebook\.", r"@twitter\.", r"@instagram\.", r"@microsoft\.",
    r"\.webp@", r"abuse@", r"spam@", r"mailer@", r"postmaster@",
]

CONTACT_PATHS = [
    "/contact", "/contact-us", "/nous-contacter", "/contactez-nous",
    "/about", "/a-propos", "/qui-sommes-nous",
    "/mentions-legales", "/legal",
    "/",
]

# ── UTILITAIRES ───────────────────────────────────────────────────────────────

def is_valid_email(email):
    email = email.lower().strip()
    for pattern in BLACKLIST_PATTERNS:
        if re.search(pattern, email, re.I):
            return False
    # Exclure les emails trop courts ou suspects
    local, _, domain = email.partition("@")
    if len(local) < 2 or "." not in domain:
        return False
    return True

def extract_emails_from_text(text):
    found = EMAIL_RE.findall(text)
    return [e.lower() for e in found if is_valid_email(e)]

def score_email(email, company_name=""):
    """Score un email : plus c'est professionnel, mieux c'est."""
    score = 0
    e = email.lower()
    name_kws = company_name.lower().split()

    # Bonus si le domaine correspond à l'entreprise
    domain = e.split("@")[-1]
    for kw in name_kws:
        if len(kw) > 3 and kw in domain:
            score += 10

    # Bonus selon le préfixe (contact > info > commercial > gmail)
    if any(p in e.split("@")[0] for p in ["contact", "recrutement", "rh", "rh@", "direction", "admin"]):
        score += 5
    if any(p in e.split("@")[0] for p in ["info", "bonjour", "hello", "accueil"]):
        score += 3
    if "gmail" in domain or "yahoo" in domain or "orange" in domain or "wanadoo" in domain:
        score -= 2  # acceptable mais moins professionnel

    return score

def best_email(emails, company_name=""):
    if not emails:
        return ""
    scored = sorted(emails, key=lambda e: score_email(e, company_name), reverse=True)
    return scored[0]

def delay():
    time.sleep(random.uniform(1.5, 3.5))

# ── MÉTHODE 1 : Scrape du site web ───────────────────────────────────────────

def get_domain_from_google(company_name, ville=""):
    """Cherche le site officiel via DuckDuckGo (pas de clé API requise)."""
    query = f"{company_name} {ville} site officiel informatique"
    url = f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select(".result__url"):
            href = a.get_text(strip=True)
            if href and "." in href:
                # Nettoyer l'URL
                if not href.startswith("http"):
                    href = "https://" + href
                parsed = urlparse(href)
                domain = parsed.netloc.replace("www.", "")
                # Exclure les gros sites génériques
                if not any(x in domain for x in [
                    "facebook", "linkedin", "twitter", "instagram", "youtube",
                    "leboncoin", "pagesjaunes", "societe.com", "verif.com",
                    "pappers", "infogreffe", "wikipedia", "gouvernement",
                    "laposte", "amazon", "google", "bing", "duckduckgo",
                ]):
                    return f"https://{domain}"
    except Exception:
        pass
    return ""

def scrape_emails_from_site(base_url, company_name=""):
    """Scrape les pages contact/accueil du site pour trouver des emails."""
    found_emails = []
    tried = set()

    for path in CONTACT_PATHS:
        url = urljoin(base_url, path)
        if url in tried:
            continue
        tried.add(url)
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code != 200:
                continue
            # Chercher dans le texte brut (pour les mailto:)
            emails = extract_emails_from_text(r.text)
            found_emails.extend(emails)

            # Chercher aussi dans les href mailto:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    if is_valid_email(email):
                        found_emails.append(email.lower())

            if found_emails:
                break  # On a trouvé sur cette page, pas besoin d'aller plus loin
            delay()
        except Exception:
            continue

    # Dédoublonner
    found_emails = list(dict.fromkeys(found_emails))
    return best_email(found_emails, company_name)

# ── MÉTHODE 2 : Google Search scrape (DuckDuckGo) ────────────────────────────

def search_email_duckduckgo(company_name, ville=""):
    """Cherche directement l'email via DuckDuckGo."""
    query = f'"{company_name}" {ville} email contact "@"'
    url = f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        emails = extract_emails_from_text(r.text)
        if emails:
            return best_email(emails, company_name)
    except Exception:
        pass
    return ""

# ── MÉTHODE 3 : Hunter.io API ─────────────────────────────────────────────────

def hunter_domain_search(domain, hunter_key):
    """Cherche les emails associés à un domaine via Hunter.io (50 crédits/mois gratuit)."""
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={hunter_key}&limit=5"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        data = r.json()
        emails_data = data.get("data", {}).get("emails", [])
        if emails_data:
            # Prioriser les emails de type "generic" (contact@, info@) ou les premiers
            contacts = [e["value"] for e in emails_data if e.get("type") == "generic"]
            if not contacts:
                contacts = [e["value"] for e in emails_data]
            return contacts[0] if contacts else ""
    except Exception:
        pass
    return ""

def hunter_email_finder(first_name, last_name, domain, hunter_key):
    """Trouve l'email d'une personne via Hunter.io."""
    url = (f"https://api.hunter.io/v2/email-finder?"
           f"domain={domain}&first_name={first_name}&last_name={last_name}"
           f"&api_key={hunter_key}")
    try:
        r = requests.get(url, timeout=TIMEOUT)
        data = r.json()
        email = data.get("data", {}).get("email", "")
        return email or ""
    except Exception:
        return ""

# ── MAIN ──────────────────────────────────────────────────────────────────────

def find_email_for_company(row, hunter_key="", verbose=True):
    name    = str(row.get("nom", "")).strip()
    ville   = str(row.get("ville", "")).strip()
    current = str(row.get("email", "")).strip()

    if current and "@" in current:
        if verbose:
            print(f"  [SKIP]  Déjà un email : {current}")
        return current

    if verbose:
        print(f"\n[?] Recherche email pour : {name} ({ville})")

    email = ""

    # ── Étape 1 : DuckDuckGo search direct ──
    if verbose: print("  [1/3] DuckDuckGo search...")
    email = search_email_duckduckgo(name, ville)
    if email:
        if verbose: print(f"  [OK] Trouvé via DDG : {email}")
        return email
    delay()

    # ── Étape 2 : Scrape du site web ──
    if verbose: print("  [2/3] Recherche site web...")
    site = get_domain_from_google(name, ville)
    if site:
        if verbose: print(f"       Site trouvé : {site}")
        email = scrape_emails_from_site(site, name)
        if email:
            if verbose: print(f"  [OK] Trouvé via site : {email}")
            return email
    delay()

    # ── Étape 3 : Hunter.io API ──
    if hunter_key and site:
        if verbose: print("  [3/3] Hunter.io API...")
        domain = urlparse(site).netloc.replace("www.", "")
        email = hunter_domain_search(domain, hunter_key)
        if email:
            if verbose: print(f"  [OK] Trouvé via Hunter : {email}")
            return email
        delay()

    if verbose: print(f"  [ERR] Email introuvable")
    return ""


def main():
    parser = argparse.ArgumentParser(description="Trouve les emails manquants dans un CSV")
    parser.add_argument("csv_file", help="Fichier CSV d'entrée")
    parser.add_argument("--hunter-key", default="", help="Clé API Hunter.io (optionnel, gratuit 50/mois)")
    parser.add_argument("--limit",      type=int, default=0, help="Nombre max d'entreprises à traiter")
    parser.add_argument("--only-missing", action="store_true", default=True, help="Traiter seulement les lignes sans email")
    parser.add_argument("--improve", action="store_true", default=False, help="Aussi améliorer les emails génériques (info@, contact@, etc.)")
    parser.add_argument("--output",     default="", help="Fichier de sortie (défaut: remplace l'entrée)")
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        print(f"[ERR] Fichier introuvable : {args.csv_file}")
        sys.exit(1)

    output_file = args.output or args.csv_file

    # Lire le CSV
    with open(args.csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or ["nom","email","ville","secteur","raison_specifique"]

    # Emails génériques à améliorer si --improve
    GENERIC_PREFIXES = ("info@", "contact@", "accueil@", "bonjour@", "hello@",
                        "webmaster@", "commercial@", "secretariat@", "administration@",
                        "mairie@", "commune@", "support@", "sav@", "magasin@")

    def needs_improvement(row):
        e = str(row.get("email", "")).strip().lower()
        if not e or "@" not in e:
            return True
        if args.improve:
            return any(e.startswith(p) for p in GENERIC_PREFIXES)
        return False

    missing = [r for r in rows if needs_improvement(r)]
    total_missing = len(missing)
    to_process = missing[:args.limit] if args.limit else missing

    print(f"\n[CSV] CSV : {len(rows)} lignes — {total_missing} sans email")
    print(f"[->] À traiter : {len(to_process)} entreprises\n")
    if args.hunter_key:
        print(f"[KEY] Hunter.io activé (clé : {args.hunter_key[:8]}...)\n")

    found_count = 0
    for i, row in enumerate(to_process, 1):
        name = str(row.get("nom","")).strip()
        print(f"[{i}/{len(to_process)}] {name}")
        email = find_email_for_company(row, hunter_key=args.hunter_key)
        if email:
            # Mettre à jour dans rows original
            for r in rows:
                if r.get("nom") == name:
                    r["email"] = email
                    break
            found_count += 1
        time.sleep(random.uniform(2, 4))

    # Sauvegarder
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*50}")
    print(f"[OK] Terminé !")
    print(f"[EMAIL] Emails trouvés : {found_count} / {len(to_process)}")
    print(f"[SAVE] Fichier mis à jour : {output_file}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()