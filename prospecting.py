# prospecting.py — Sourcing de prospects via Apollo.io API

import os
import requests
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
APOLLO_BASE_URL = "https://api.apollo.io/v1"

# Régions → liste de pays pour Apollo
REGION_MAP = {
    "Europe":                  ["France", "Belgium", "Switzerland", "Germany", "United Kingdom",
                                "Netherlands", "Spain", "Italy", "Portugal", "Sweden",
                                "Denmark", "Norway", "Finland", "Austria", "Luxembourg"],
    "Moyen-Orient":            ["United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait",
                                "Bahrain", "Oman", "Jordan", "Israel", "Lebanon"],
    "Asie-Pacifique":          ["Japan", "Singapore", "India", "South Korea", "Hong Kong",
                                "Taiwan", "Thailand", "Malaysia", "Indonesia", "Vietnam",
                                "Australia", "New Zealand"],
    "US / Canada / Mexique":   ["United States", "Canada", "Mexico"],
    "Amérique du Sud":         ["Brazil", "Argentina", "Colombia", "Chile", "Peru",
                                "Ecuador", "Uruguay"],
    "Afrique & Océan Indien":  ["Mauritius", "South Africa", "Kenya", "Morocco", "Senegal",
                                "Tunisia", "Egypt", "Ivory Coast", "Ghana", "Nigeria"],
}

# Correspondance taille → format Apollo
SIZE_MAP = {
    "1-10":    "1,10",
    "11-50":   "11,50",
    "51-200":  "51,200",
    "201-500": "201,500",
    "500+":    "500,10000"
}


def search_prospects(icp: dict, country: str = "Europe", num_results: int = 25) -> list:
    """
    Recherche des prospects via Apollo.io.
    Le paramètre `country` correspond à une région du REGION_MAP.
    """
    if not APOLLO_API_KEY:
        raise ValueError(
            "APOLLO_API_KEY manquante. "
            "Ajoute-la dans le fichier .env (app.apollo.io > Settings > API)"
        )

    locations = REGION_MAP.get(country, REGION_MAP["Europe"])

    payload = {
        "api_key":              APOLLO_API_KEY,
        "page":                 1,
        "per_page":             num_results,
        "person_titles":        icp.get("job_titles", []),
        "organization_locations": locations,
        "contact_email_status": ["verified", "guessed"],
    }

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
        raise Exception(f"Erreur Apollo API {response.status_code} : {response.text[:200]}")

    people = response.json().get("people", [])

    prospects = []
    for person in people:
        org = person.get("organization") or {}
        prospects.append({
            "Nom":        f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
            "Poste":      person.get("title", ""),
            "Entreprise": org.get("name", ""),
            "Secteur":    org.get("industry", ""),
            "Taille":     org.get("estimated_num_employees", ""),
            "Email":      person.get("email", ""),
            "LinkedIn":   person.get("linkedin_url", ""),
            "Ville":      person.get("city", ""),
        })

    return prospects
