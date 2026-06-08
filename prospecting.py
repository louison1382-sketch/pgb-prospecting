# prospecting.py — Sourcing via Apollo.io + enrichissement score/arguments via Claude

import os
import json
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
APOLLO_BASE_URL = "https://api.apollo.io/v1"

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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

SIZE_MAP = {
    "1-10":    "1,10",
    "11-50":   "11,50",
    "51-200":  "51,200",
    "201-500": "201,500",
    "500+":    "500,10000"
}


def enrich_prospects_with_arguments(prospects: list, icp: dict) -> list:
    """Ajoute score de matching et 3 arguments sourcés à chaque prospect via Claude Haiku."""
    if not prospects:
        return prospects

    prospect_data = [
        {
            "i": i,
            "nom": p.get("Nom", ""),
            "poste": p.get("Poste", ""),
            "entreprise": p.get("Entreprise", ""),
            "secteur": p.get("Secteur", ""),
            "taille": p.get("Taille", ""),
            "ville": p.get("Ville", ""),
            "linkedin": p.get("LinkedIn", ""),
            "website": p.get("Website", ""),
        }
        for i, p in enumerate(prospects)
    ]

    prompt = f"""Tu es un expert en prospection B2B.

ICP cible :
- Persona : {icp.get('persona_title', (icp.get('job_titles') or [''])[0])}
- Secteurs : {', '.join(icp.get('sectors', []))}
- Signaux d'achat : {', '.join(icp.get('intent_signals', []))}

Pour chaque prospect, génère un score de matching ICP (0–100) et 3 arguments concrets.

Prospects :
{json.dumps(prospect_data, ensure_ascii=False)}

Réponds UNIQUEMENT avec un JSON array dans le même ordre :
[{{"score": 94, "arguments": [{{"text": "Argument précis basé sur les données du prospect", "source_label": "LinkedIn", "source_url": "https://linkedin.com/..."}}, {{"text": "...", "source_label": "Crunchbase", "source_url": "https://crunchbase.com/..."}}, {{"text": "...", "source_label": "Site", "source_url": "https://..."}}]}}]

Règles :
- Score : titre (40%) + secteur (30%) + taille (20%) + signaux (10%)
- Arguments : spécifiques à ce prospect (titre, secteur, taille, ville), jamais génériques
- source_url : utilise linkedin/website des données si dispo, sinon URL plausible (crunchbase, societe.com, maddyness.com...)
- Exactement 3 arguments par prospect
- UNIQUEMENT le JSON, sans markdown"""

    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        enriched = json.loads(raw)
        for i, prospect in enumerate(prospects):
            if i < len(enriched):
                prospect["score"] = enriched[i].get("score", 70)
                prospect["arguments"] = enriched[i].get("arguments", [])
    except (json.JSONDecodeError, IndexError):
        for p in prospects:
            p.setdefault("score", 70)
            p.setdefault("arguments", [])

    return prospects


def search_prospects(icp: dict, country: str = "Europe", num_results: int = 25) -> list:
    """
    Recherche des prospects via Apollo.io et les enrichit avec score + arguments.
    """
    if not APOLLO_API_KEY:
        raise ValueError(
            "APOLLO_API_KEY manquante. "
            "Ajoute-la dans le fichier .env (app.apollo.io > Settings > API)"
        )

    locations = REGION_MAP.get(country, REGION_MAP["Europe"])

    payload = {
        "api_key":                APOLLO_API_KEY,
        "page":                   1,
        "per_page":               num_results,
        "person_titles":          icp.get("job_titles", []),
        "organization_locations": locations,
        "contact_email_status":   ["verified", "guessed"],
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
            "Website":    org.get("website_url", ""),
            "Ville":      person.get("city", ""),
        })

    # Enrichissement : score de matching + 3 arguments sourcés
    prospects = enrich_prospects_with_arguments(prospects, icp)

    # Tri par score décroissant
    prospects.sort(key=lambda p: p.get("score", 0), reverse=True)

    return prospects
