# prospecting.py — Sourcing via Explorium API + enrichissement score/arguments via Claude
# Pipeline : fetch prospects → bulk enrich emails (vérifiés) → score Python + args Claude Haiku (async)

import asyncio
import json
import os

import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

EXPLORIUM_API_KEY = os.getenv("EXPLORIUM_API_KEY")
EXPLORIUM_BASE_URL = "https://api.explorium.ai/v1"

claude = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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

# Catégories valides pour le filtre job_department de l'API Explorium
# (toute autre valeur provoque une erreur 422 "value is not a valid enumeration member")
VALID_JOB_DEPARTMENTS = {
    "administration", "real estate", "healthcare", "partnerships", "c-suite",
    "design", "human resources", "engineering", "education", "strategy",
    "product", "sales", "r&d", "retail", "customer success", "security",
    "public service", "creative", "it", "support", "marketing", "trade",
    "legal", "operations", "procurement", "data", "manufacturing", "logistics",
    "finance",
}


def _headers() -> dict:
    return {
        "api_key": EXPLORIUM_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _filter_valid_departments(departments: list[str]) -> list[str]:
    """Ne garde que les départements reconnus par l'enum Explorium (insensible à la casse)."""
    valid = []
    for d in departments:
        d_norm = (d or "").strip().lower()
        if d_norm in VALID_JOB_DEPARTMENTS:
            valid.append(d_norm)
    return valid


async def _autocomplete(client: httpx.AsyncClient, field: str, query: str) -> str | None:
    """Returns the first standardized value from Explorium autocomplete, or None."""
    try:
        r = await client.get(
            f"{EXPLORIUM_BASE_URL}/prospects/autocomplete",
            params={"field": field, "query": query, "semantic_search": "false"},
            timeout=10,
        )
        items = r.json()
        return items[0]["value"] if items else None
    except Exception:
        return None


async def _standardize_job_titles(client: httpx.AsyncClient, titles: list[str]) -> list[str]:
    """Standardize job titles via autocomplete — appels en parallèle."""
    tasks = [_autocomplete(client, "job_title", t) for t in titles[:5]]
    results = await asyncio.gather(*tasks)
    return [val if val else titles[i] for i, val in enumerate(results)]


async def _standardize_intent_topics(client: httpx.AsyncClient, signals: list[str]) -> list[str]:
    """Standardize intent topics via autocomplete — appels en parallèle."""
    tasks = [_autocomplete(client, "business_intent_topics", s) for s in signals[:3]]
    results = await asyncio.gather(*tasks)
    return [val for val in results if val]


def _calculate_score(prospect: dict, icp: dict) -> int:
    """Score de matching ICP calculé en Python. Reproductible et explicable.

    Pondération :
    - Titre de poste  40 pts (match fort=40, match partiel=20)
    - Secteur         30 pts (match fort=30, match partiel=15)
    - Taille          20 pts (match exact=20, taille présente=10)
    - Email vérifié   10 pts
    """
    score = 0

    # Titre (40 pts)
    job_titles_icp = [t.lower() for t in icp.get("job_titles", [])]
    poste = (prospect.get("Poste") or "").lower()
    if poste and any(t in poste or poste in t for t in job_titles_icp):
        score += 40
    elif poste and any(
        any(word in poste for word in t.split() if len(word) > 3)
        for t in job_titles_icp
    ):
        score += 20

    # Secteur (30 pts)
    sectors_icp = [s.lower() for s in icp.get("sectors", [])]
    secteur = (prospect.get("Secteur") or "").lower()
    if secteur and any(s in secteur or secteur in s for s in sectors_icp):
        score += 30
    elif secteur and any(
        any(word in secteur for word in s.split() if len(word) > 3)
        for s in sectors_icp
    ):
        score += 15

    # Taille (20 pts)
    sizes_icp = icp.get("company_size", [])
    taille = prospect.get("Taille") or ""
    if taille and any(s in taille or taille in s for s in sizes_icp):
        score += 20
    elif taille:
        score += 10

    # Email vérifié (10 pts)
    email = prospect.get("Email") or ""
    if email and "@" in email:
        score += 10

    return min(score, 100)


async def enrich_prospects_with_arguments(prospects: list, icp: dict) -> list:
    """Ajoute score Python reproductible + 3 arguments sourcés via Claude Haiku (async)."""
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

Pour chaque prospect, génère 3 arguments concrets et personnalisés expliquant pourquoi il matche l'ICP.

Prospects :
{json.dumps(prospect_data, ensure_ascii=False)}

Réponds UNIQUEMENT avec un JSON array dans le même ordre :
[{{"arguments": [{{"text": "Argument précis basé sur les données du prospect", "source_label": "LinkedIn", "source_url": "https://linkedin.com/in/..."}}, {{"text": "...", "source_label": "Site entreprise", "source_url": "https://..."}}, {{"text": "...", "source_label": null, "source_url": null}}]}}]

Règles :
- Arguments : spécifiques à ce prospect (titre, secteur, taille, ville), jamais génériques
- source_url : utilise les champs linkedin/website fournis si disponibles, sinon null — ne jamais inventer une URL
- source_label : "LinkedIn", "Site entreprise", ou null si aucune source réelle disponible
- Exactement 3 arguments par prospect
- UNIQUEMENT le JSON, sans markdown"""

    message = await claude.messages.create(
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
            prospect["score"] = _calculate_score(prospect, icp)
            if i < len(enriched):
                prospect["arguments"] = enriched[i].get("arguments", [])
            else:
                prospect.setdefault("arguments", [])
    except (json.JSONDecodeError, IndexError):
        for p in prospects:
            p["score"] = _calculate_score(p, icp)
            p.setdefault("arguments", [])

    return prospects


async def search_prospects(icp: dict, country: str = "France", num_results: int = 15) -> list:
    """
    Recherche des prospects via Explorium API et les enrichit avec score + arguments.

    Pipeline :
    1. Autocomplete job_titles + intent_topics en parallèle (asyncio.gather)
    2. POST /v1/prospects → liste de prospects
    3. POST /v1/prospects/contacts_information/bulk_enrich → emails (guessés filtrés)
    4. Score Python reproductible + arguments Claude Haiku (async)
    """
    if not EXPLORIUM_API_KEY:
        raise ValueError(
            "EXPLORIUM_API_KEY manquante. "
            "Ajoute-la dans les variables d'environnement Railway."
        )

    async with httpx.AsyncClient(headers=_headers()) as client:
        # ── 1. Standardisation des filtres (parallèle) ──────────────────────
        job_titles, intent_topics = await asyncio.gather(
            _standardize_job_titles(client, icp.get("job_titles", [])),
            _standardize_intent_topics(client, icp.get("intent_signals", [])),
        )

        # Géographie
        country_codes = ["FR"] if country == "France" else REGION_MAP.get(country, ["FR"])

        # Taille d'entreprise
        sizes = [SIZE_MAP[s] for s in icp.get("company_size", ["11-50", "51-200"]) if s in SIZE_MAP]

        # ── 2. Fetch prospects ───────────────────────────────────────────────
        filters: dict = {"has_email": {"value": True}}
        if job_titles:
            filters["job_title"] = {"values": job_titles}
        departments = _filter_valid_departments(icp.get("job_departments", []))
        if departments:
            filters["job_department"] = {"values": departments}
        if sizes:
            filters["company_size"] = {"values": sizes}
        if country_codes:
            filters["company_country_code"] = {"values": country_codes}
        if intent_topics:
            filters["business_intent_topics"] = {"values": intent_topics}

        page_size = max(1, min(num_results, 100))

        fetch_resp = await client.post(
            f"{EXPLORIUM_BASE_URL}/prospects",
            json={
                "mode": "full",
                "size": num_results,
                "page_size": page_size,
                "page": 1,
                "filters": filters,
            },
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

        # ── 3. Bulk enrich contacts — filtre les emails guessés ─────────────
        # Les emails guessés ont un bounce rate de 20-40% → classent la boîte en spam
        enrich_resp = await client.post(
            f"{EXPLORIUM_BASE_URL}/prospects/contacts_information/bulk_enrich",
            json={"prospect_ids": prospect_ids, "parameters": {"contact_types": ["email"]}},
            timeout=30,
        )

        email_map: dict[str, str] = {}
        if enrich_resp.status_code == 200:
            for ep in enrich_resp.json().get("prospects", enrich_resp.json().get("data", [])):
                pid = ep.get("prospect_id")
                emails = ep.get("emails") or []
                if pid and emails:
                    verified = [e for e in emails if e.get("type", "").lower() != "guessed"]
                    if verified:
                        email_map[pid] = verified[0].get("email", "")

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
            "Email":      email_map.get(pid, ""),  # vide si email guessé ou absent
            "LinkedIn":   p.get("linkedin_url", ""),
            "Website":    org.get("website") or p.get("company_website", ""),
            "Ville":      p.get("city") or p.get("city_name", ""),
        })

    # ── 5. Score Python + arguments Claude Haiku ─────────────────────────────
    prospects = await enrich_prospects_with_arguments(prospects, icp)
    prospects.sort(key=lambda p: p.get("score", 0), reverse=True)

    return prospects
