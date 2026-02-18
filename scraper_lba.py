"""
=============================================================
  LA BONNE ALTERNANCE SCRAPER - Kader BELEM
  Récupère les entreprises via l'API officielle LBA
  et génère/met à jour entreprises.csv pour sender.py
=============================================================
  PRÉREQUIS :
    pip install requests pandas

  UTILISATION :
    python scraper_lba.py                 -> Nantes + Angers, rayon 30km
    python scraper_lba.py --ville nantes  -> Nantes uniquement
    python scraper_lba.py --rayon 50      -> Rayon 50km
    python scraper_lba.py --preview       -> Afficher sans sauvegarder
    python scraper_lba.py --stats         -> Stats du CSV actuel
=============================================================
"""

import requests
import pandas as pd
import json
import os
import argparse

# ─── CONFIGURATION ───────────────────────────────────────────

ROME_CODES = ["M1810", "M1802", "I1401"]

VILLES = {
    "nantes":         {"nom": "Nantes",         "lat": 47.2184, "lon": -1.5536},
    "angers":         {"nom": "Angers",          "lat": 47.4784, "lon": -0.5632},
    "saint-herblain": {"nom": "Saint-Herblain",  "lat": 47.2117, "lon": -1.6490},
}

OUTPUT_CSV   = "entreprises.csv"
TRACKER_FILE = "candidatures.json"
DEFAULT_RADIUS = 30

# Endpoints à essayer dans l'ordre
ENDPOINTS = [
    # Nouveau endpoint officiel 2025/2026
    "https://api.apprentissage.beta.gouv.fr/api/job_opportunity/search",
    # Ancien endpoint (fallback)
    "https://labonnealternance.apprentissage.beta.gouv.fr/api/V1/jobs",
]

# ─────────────────────────────────────────────────────────────

def _try_request(url, params, headers):
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_for_rome(rome, lat, lon, radius):
    """Appelle l'API LBA pour un code ROME et retourne la réponse brute."""
    headers = {"Accept": "application/json", "User-Agent": "kader-belem-bot/2.0"}

    # Nouveau endpoint
    try:
        data = _try_request(ENDPOINTS[0], {"romes": rome, "lat": lat, "lon": lon, "radius": radius}, headers)
        return data, "nouveau"
    except Exception as e1:
        pass

    # Ancien endpoint fallback
    try:
        data = _try_request(ENDPOINTS[1], {"romes": rome, "latitude": lat, "longitude": lon, "radius": radius, "caller": "kader_belem_bot"}, headers)
        return data, "ancien"
    except Exception as e2:
        raise RuntimeError(f"Les deux endpoints ont échoué. Dernier: {e2}")


def parse_response(data) -> list[dict]:
    """Parse la réponse API (compatible nouveau et ancien format) en liste normalisée."""
    results = []

    # ── Format liste directe ──
    if isinstance(data, list):
        items = data
    else:
        # Essayer toutes les clés possibles
        items = (
            data.get("jobs", []) or
            data.get("results", []) or
            data.get("opportunites", []) or
            data.get("data", []) or
            []
        )
        # Entreprises "recruteurs LBA" (marché caché) dans l'ancien format
        for c in data.get("companies", {}).get("results", []):
            email = (c.get("email") or "").strip()
            nom   = (c.get("name") or c.get("label") or c.get("enseigne") or "").strip()
            if nom and email:
                results.append({
                    "nom":               nom,
                    "email":             email,
                    "ville":             (c.get("city") or c.get("commune") or "").strip(),
                    "secteur":           (c.get("naf_text") or "IT / Réseaux").strip(),
                    "raison_specifique": "entreprise a fort potentiel detectee par La Bonne Alternance",
                })

    for job in items:
        company = job.get("company") or job.get("entreprise") or {}
        contact = job.get("contact") or job.get("apply") or {}
        title   = str(job.get("title") or job.get("intitule") or "Technicien IT")

        nom = str(
            company.get("name") or
            company.get("enseigne") or
            company.get("raison_sociale") or
            job.get("entreprise_libelle") or ""
        ).strip()

        email = str(
            contact.get("email") or
            company.get("email") or
            job.get("email") or ""
        ).strip()

        place = company.get("place") or {}
        ville = str(
            place.get("city") if isinstance(place, dict) else
            company.get("city") or
            company.get("commune") or
            job.get("lieu_travail", {}).get("libelle") or ""
        ).strip()

        if nom and email:
            results.append({
                "nom":               nom,
                "email":             email,
                "ville":             ville,
                "secteur":           title[:80],
                "raison_specifique": f"offre publiee sur La Bonne Alternance : {title[:60]}",
            })

    return results


def fetch_companies(lat, lon, radius) -> list[dict]:
    results = []
    for rome in ROME_CODES:
        try:
            print(f"      ROME {rome} ...", end=" ", flush=True)
            data, endpoint_used = fetch_for_rome(rome, lat, lon, radius)
            parsed = parse_response(data)
            print(f"OK ({len(parsed)} resultats, endpoint {endpoint_used})")
            results.extend(parsed)
        except requests.exceptions.ConnectionError:
            print("ERREUR - pas de connexion internet")
        except requests.exceptions.Timeout:
            print("ERREUR - timeout")
        except Exception as e:
            print(f"ERREUR - {e}")
    return results


def load_existing_csv():
    if os.path.exists(OUTPUT_CSV):
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8")
        for col in ["nom", "email", "ville", "secteur", "raison_specifique"]:
            if col not in df.columns:
                df[col] = ""
        df["nom"]   = df["nom"].fillna("").astype(str)
        df["email"] = df["email"].fillna("").astype(str)
        return df
    return pd.DataFrame(columns=["nom", "email", "ville", "secteur", "raison_specifique"])


def load_tracker_emails() -> set:
    if not os.path.exists(TRACKER_FILE):
        return set()
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {c["email"] for c in data.get("candidatures", []) if c.get("email")}
    except Exception:
        return set()


def already_in_csv(df, nom, email) -> bool:
    if df.empty:
        return False
    if email and len(df[df["email"].str.lower() == email.lower()]) > 0:
        return True
    if len(df[df["nom"].str.lower() == nom.lower()]) > 0:
        return True
    return False


def run_scraper(villes_cibles, radius, preview=False):
    print(f"\n{'='*62}")
    print("  LA BONNE ALTERNANCE SCRAPER - Kader BELEM")
    print(f"  Villes : {', '.join(villes_cibles)}  |  Rayon : {radius}km")
    print(f"  ROME   : {', '.join(ROME_CODES)}")
    print(f"  Mode   : {'PREVIEW (sans sauvegarde)' if preview else 'MISE A JOUR entreprises.csv'}")
    print(f"{'='*62}\n")

    existing_df     = load_existing_csv()
    already_contact = load_tracker_emails()

    print(f"   CSV actuel       : {len(existing_df)} entreprises")
    print(f"   Deja contactees  : {len(already_contact)}\n")

    all_new = []

    for ville_key in villes_cibles:
        ville = VILLES.get(ville_key.lower())
        if not ville:
            print(f"  Ville inconnue : '{ville_key}' (dispo: {', '.join(VILLES)})")
            continue

        print(f"  Recherche autour de {ville['nom']}...")
        companies = fetch_companies(ville["lat"], ville["lon"], radius)

        new_c = skip_dup = skip_mail = skip_cont = 0
        for c in companies:
            if not c["email"]:
                skip_mail += 1
            elif c["email"] in already_contact:
                skip_cont += 1
            elif already_in_csv(existing_df, c["nom"], c["email"]):
                skip_dup += 1
            else:
                all_new.append(c)
                new_c += 1

        print(f"   + {new_c} nouvelles | {skip_dup} doublons | {skip_mail} sans email | {skip_cont} deja contactees\n")

    if not all_new:
        print("  Aucune nouvelle entreprise avec email de contact trouvee.")
        print()
        print("  IMPORTANT : La Bonne Alternance masque souvent les emails pour")
        print("  forcer le passage par leur plateforme. Dans ce cas, postulez")
        print("  directement sur le site en cherchant M1810 / M1802 pres de Nantes/Angers.")
        print("  URL : https://labonnealternance.apprentissage.beta.gouv.fr")
        return

    new_df = pd.DataFrame(all_new).drop_duplicates(subset=["email"])
    print(f"  {len(new_df)} nouvelles entreprises trouvees :\n")
    print(f"  {'Entreprise':<36} {'Email':<32} Ville")
    print(f"  {'─'*36} {'─'*32} {'─'*15}")
    for _, r in new_df.head(30).iterrows():
        print(f"  {str(r['nom'])[:35]:<36} {str(r['email'])[:31]:<32} {r['ville']}")
    if len(new_df) > 30:
        print(f"  ... et {len(new_df) - 30} autres")

    if preview:
        print("\n  (Mode preview - rien n'a ete modifie)")
        return

    cols = ["nom", "email", "ville", "secteur", "raison_specifique"]
    combined = pd.concat([existing_df[cols], new_df[[c for c in cols if c in new_df.columns]]], ignore_index=True)
    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(f"\n  entreprises.csv mis a jour : {len(combined)} entreprises ({len(new_df)} nouvelles)")
    print(f"\n  Prochaine etape :")
    print(f"    python sender.py test entreprises.csv")
    print(f"    python sender.py send entreprises.csv 10")


def show_stats():
    df = load_existing_csv()
    if df.empty:
        print("  Aucune entreprise dans le CSV.")
        return
    contacted = load_tracker_emails()
    df["email"] = df["email"].fillna("")
    mask = df["email"].isin(contacted)
    print(f"\n  Statistiques entreprises.csv")
    print(f"    Total              : {len(df)}")
    print(f"    Deja contactees    : {mask.sum()}")
    print(f"    Restant a envoyer  : {(~mask).sum()}")
    if "ville" in df.columns:
        print(f"\n    Par ville :")
        for ville, n in df["ville"].value_counts().head(10).items():
            print(f"      {str(ville):<25} : {n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ville", nargs="+", default=["nantes", "angers"])
    parser.add_argument("--rayon", type=int, default=DEFAULT_RADIUS)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--stats",   action="store_true")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        run_scraper([v.lower() for v in args.ville], args.rayon, args.preview)
