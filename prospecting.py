# prospecting.py — Sourcing via Explorium API + enrichissement score/arguments via Claude
# Pipeline : fetch prospects (ICP filters) → bulk enrich contacts (emails) → score + args (Claude Haiku)

import os
import json
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

EXPLORIUM_API_KEY = os.getenv("EXPLORIUM_API_KEY")
EXPLORIUM_BASE_URL = "https://api.explorium.ai/v1"

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

REGION_MAP = {
    "Europe":                ["FR", "BE", "CH", "DE", "GB", "NL", "ES", "IT", "PT",
                              "SE", "DK", "NO", "FI", "AT", "LU"],
    "Moyen-Orient":          ["AE", "SA", "QA", "KW", "BH", "OM", "JO", "IL", "LB"],
    "Asie-Pacifique":        ["JP", "SG", "IN", "KR", "HK", "TW", "TH", "MY", "ID",
                              "VN", "AU", "NZ"],
    "US / Canada / Mexique": ["US", "CA", "MX"],
    "Amérique du Sud":       ["BR", "AR", "CO", "CL", "PE", "EC", "UY"],
    "Afrique & Océan Indien":["MU", "ZA", "KE", "MA", "SN", "TN", "EG", "CI", "GH", "NG"],
}

SIZE_MAP = {
    "1-10":    "1-10",
    "11-50":   "11-50",
    "51-200":  "51-200",
    "201-500": "201-500",
    "500+":    "501-1000",
}


def _headers() -> dict:
    return {
        "X-API-Key": EXPLORIUM_API_KEY,
        "Content-Type": "application/json",
    }


def _autocomplete(field: str, query: str) -> str | None:
    """Returns the first standardized value from Explorium autocomplete, or None."""
    try:
        r = requests.get(
            f"{EXPLORIUM_BASE_URL}/prospects/autocomplete",
            params={"field": field, "query": query, "semantic_search": "false"},
            headers=_headers(),
            timeout=10,
        )
        items = r.json()
        return items[0]["value"] if items else None
    except Exception:
        return None


def _standardize_job_titles(titles: list[str]) -> list[str]:
    """Standardize job titles via autocomplete. Falls back to raw value if no match."""
    result = []
    for title in titles[:5]:  # limit to 5 to avoid latency
        val = _autocomplete("job_title", title)
        result.append(val if val else title)
    return result


def _standardize_intent_topics(signals: list[str]) -> list[str]:
    """Standardize intent topics via autocomplete."""
    result = []
    for signal in signals[:3]:
        val = _autocomplete("business_intent_topics", signal)
        if val:
            result.append(val)
    return result


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
- source_url : utilise linkedin/website des données si dispo, sinon URL plausible
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


def search_prospects(icp: dict, country: str = "France", num_results: int = 15) -> list:
    """
    Recherche des prospects via Explorium API et les enrichit avec score + arguments.

    Pipeline :
    1. Autocomplete job_titles + intent_topics → valeurs standardisées Explorium
    2. POST /v1/prospects → liste de prospects (avec prospect_id)
    3. POST /v1/prospects/contacts_information/bulk_enrich → emails
    4. Enrich avec Claude Haiku → score + 3 arguments par prospect
    """
    if not EXPLORIUM_API_KEY:
        raise ValueError(
            "EXPLORIUM_API_KEY manquante. "
            "Ajoute-la dans les variables d'environnement Railway."
        )

    # ── 1. Standardisation des filtres ──────────────────────────────────────
    job_titles_raw = icp.get("job_titles", [])
    job_titles = _standardize_job_titles(job_titles_raw)

    intent_signals_raw = icp.get("intent_signals", [])
    intent_topics = _standardize_intent_topics(intent_signals_raw)

    # Géographie
    if country == "France":
        country_codes = ["FR"]
    else:
        country_codes = REGION_MAP.get(country, ["FR"])

    # Taille d'entreprise
    sizes_raw = icp.get("company_size", ["11-50", "51-200"])
    sizes = [SIZE_MAP[s] for s in sizes_raw if s in SIZE_MAP]

    # ── 2. Fetch prospects ───────────────────────────────────────────────────
    filters: dict = {
        "has_email": True,
    }

    if job_titles:
        filters["job_title"] = {"values": job_titles}

    # Utilise job_level comme filet de sécurité si les titres sont peu précis
    departments = icp.get("job_departments", [])
    if departments:
        filters["job_department"] = {"values": departments}

    if sizes:
        filters["company_size"] = {"values": sizes}

    if country_codes:
        filters["company_country_code"] = {"values": country_codes}

    if intent_topics:
        filters["business_intent_topics"] = {"values": intent_topics}

    fetch_payload = {
        "filters": filters,
        "number_of_results": num_results,
        "mode": "full",
    }

    fetch_resp = requests.post(
        f"{EXPLORIUM_BASE_URL}/prospects",
        json=fetch_payload,
        headers=_headers(),
        timeout=30,
    )

    if fetch_resp.status_code != 200:
        raise Exception(
            f"Erreur Explorium fetch {fetch_resp.status_code} : {fetch_resp.text[:300]}"
        )

    fetch_data = fetch_resp.json()
    raw_prospects = fetch_data.get("prospects", fetch_data.get("data", []))

    if not raw_prospects:
        return []

    prospect_ids = [p["prospect_id"] for p in raw_prospects if p.get("prospect_id")]

    # ── 3. Bulk enrich contacts (emails) ────────────────────────────────────
    enrich_payload = {
        "prospect_ids": prospect_ids,
        "parameters": {"contact_types": ["email"]},
    }

    enrich_resp = requests.post(
        f"{EXPLORIUM_BASE_URL}/prospects/contacts_information/bulk_enrich",
        json=enrich_payload,
        headers=_headers(),
        timeout=30,
    )

    email_map: dict[str, str] = {}
    if enrich_resp.status_code == 200:
        enrich_data = enrich_resp.json()
        enriched_list = enrich_data.get("prospects", enrich_data.get("data", []))
        for ep in enriched_list:
            pid = ep.get("prospect_id")
            emails = ep.get("emails") or []
            if pid and emails:
                email_map[pid] = emails[0].get("email", "")

    # ── 4. Normalisation en format interne ──────────────────────────────────
    prospects = []
    for p in raw_prospects:
        pid = p.get("prospect_id", "")
        org = p.get("organization") or p.get("company") or {}
        prospects.append({
            "Nom":        f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "Poste":      p.get("job_title") or p.get("title", ""),
            "Entreprise": org.get("name") or p.get("company_name", ""),
            "Secteur":    org.get("industry") or p.get("industry", ""),
            "Taille":     org.get("number_of_employees_range") or p.get("company_size", ""),
            "Email":      email_map.get(pid, p.get("email", "")),
            "LinkedIn":   p.get("linkedin_url", ""),
            "Website":    org.get("website") or p.get("company_website", ""),
            "Ville":      p.get("city") or p.get("city_name", ""),
        })

    # ── 5. Score + arguments (Claude Haiku) ─────────────────────────────────
    prospects = enrich_prospects_with_arguments(prospects, icp)
    prospects.sort(key=lambda p: p.get("score", 0), reverse=True)

    return prospects
