# prospecting.py — Sourcing de prospects via Apollo.io API
#
# Ce fichier prend un ICP (généré par icp.py) et retourne une liste
# de prospects correspondants avec leurs coordonnées.
#
# Apollo.io tier gratuit : 50 crédits/mois (suffisant pour tester)
# Apollo.io tier basic : ~49€/mois pour un volume plus important

import os
import requests
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
APOLLO_BASE_URL = "https://api.apollo.io/v1"

# Correspondance pays → code pour Apollo
COUNTRY_CODES = {
    "France": "France",
    "Belgique": "Belgium",
    "Suisse": "Switzerland",
    "Luxembourg": "Luxembourg"
}

# Correspondance taille → format Apollo
SIZE_MAP = {
    "1-10":    "1,10",
    "11-50":   "11,50",
    "51-200":  "51,200",
    "201-500": "201,500",
    "500+":    "500,10000"
}


def search_prospects(icp: dict, country: str = "France", num_results: int = 25) -> list:
    """
    Recherche des prospects correspondant à l'ICP via Apollo.io.
    
    Args:
        icp: Dictionnaire ICP généré par icp.py
        country: Pays cible (France, Belgique, Suisse, Luxembourg)
        num_results: Nombre de prospects à retourner (max 25 sur tier gratuit)
    
    Returns:
        Liste de dicts avec les infos de chaque prospect.
    """
    if not APOLLO_API_KEY:
        raise ValueError(
            "APOLLO_API_KEY manquante. "
            "Ajoute-la dans le fichier .env (app.apollo.io > Settings > API)"
        )

    payload = {
        "api_key": APOLLO_API_KEY,
        "page": 1,
        "per_page": num_results,
        "person_titles": icp.get("job_titles", []),
        "organization_locations": [COUNTRY_CODES.get(country, "France")],
        "contact_email_status": ["verified", "guessed"],
    }

    # Filtre taille d'entreprise
    sizes = icp.get("company_size", ["11-50", "51-200"])
    if sizes:
        payload["organization_num_employees_ranges"] = [
            SIZE_MAP[s] for s in sizes if s in SIZE_MAP
        ]

    response = requests.post(
        f"{APOLLO_BASE_URL}/mixed_people/search",
        json=payload,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        raise Exception(
            f"Erreur Apollo API {response.status_code} : {response.text[:200]}"
        )

    people = response.json().get("people", [])

    # Mise en forme pour affichage Streamlit
    prospects = []
    for person in people:
        org = person.get("organization") or {}
        email = person.get("email", "")
        prospects.append({
            "Nom":        f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
            "Poste":      person.get("title", ""),
            "Entreprise": org.get("name", ""),
            "Secteur":    org.get("industry", ""),
            "Taille":     org.get("estimated_num_employees", ""),
            "Email":      email,
            "LinkedIn":   person.get("linkedin_url", ""),
            "Ville":      person.get("city", ""),
        })

    return prospects
