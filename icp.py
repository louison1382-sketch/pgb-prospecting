# icp.py — Génération d'ICP via Claude API (avec cache en mémoire)
# Structure ICP : Claude Haiku (rapide, pas de raisonnement complexe requis)
# Proof stats    : Claude Sonnet (meilleure fiabilité sur les citations factuelles)

import hashlib
import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU_LABEL = "Claude Haiku 4.5"
MODEL_SONNET_LABEL = "Claude Sonnet 4.6"

# Cache en mémoire — évite de rebrûler des crédits sur les mêmes tests
# Reset au redémarrage Railway (acceptable pour 3 utilisateurs internes)
_icp_cache: dict[str, dict] = {}

# ── PROMPT 1 — Structure ICP (Haiku) ──────────────────────────────────────────────────────────────────

ICP_STRUCTURE_PROMPT = """Tu es un expert en marketing B2B et prospection commerciale.

À partir de la description de service ci-dessous, génère un ICP (Ideal Customer Profile) structuré.
L'ICP doit être fondé sur la réalité du service décrit — pas sur des généralités.

SERVICE :
{product_description}

Génère un ICP au format JSON avec exactement ces champs :
{{
  "sectors": ["secteur1", "secteur2"],
  "company_size": ["11-50", "51-200"],
  "job_titles": ["Directeur Général", "CEO"],
  "job_departments": ["operations", "c-suite"],
  "intent_signals": ["signal d'achat 1", "signal d'achat 2"],
  "red_flags": ["signal d'exclusion 1"],
  "outreach_angle": "Une phrase résumant l'angle d'approche cold email",
  "persona_title": "DAF / Directeur Général",
  "persona_subtitle": "Décideur direct sur les outils d'efficacité opérationnelle",
  "company_profile": {{
    "taille": "20 – 200 employés",
    "secteur": "Services B2B / Tech",
    "signal": "Description du signal d'achat clé",
    "geo": "France (IDF prioritaire)",
    "maturite": "Exploration / Pilote",
    "budget": "30 000 – 80 000 €/an"
  }}
}}

Guidelines :
- sectors : 3 à 5 secteurs prioritaires en français
- job_titles : 3 à 5 titres de poste en français, les plus pertinents pour ce service
- job_departments : en anglais minuscule (ex: finance, operations, c-suite, marketing, sales)
- intent_signals : signaux observables qui indiquent un besoin
- red_flags : critères qui disqualifient un prospect
- outreach_angle : une phrase précise, pas générique
- persona_title : format court type "DAF / DG" ou "Head of Ops / COO"

Réponds UNIQUEMENT avec le JSON valide, sans texte avant ou après."""


# ── PROMPT 2 — Proof stats + reasoning (Sonnet) ─────────────────────────────────────

PROOF_PROMPT = """Tu es un expert en marketing B2B.

On vient de générer l'ICP suivant pour ce service :

SERVICE :
{product_description}

ICP :
- Persona : {persona_title}
- Secteurs : {sectors}
- Signaux d'achat : {intent_signals}

Génère exactement 3 statistiques ou observations de marché qui justifient cet ICP,
plus un paragraphe de reasoning.

Format JSON :
{{
  "proof": [
    {{
      "stat": "78%",
      "description": "des PME françaises citent la productivité comme priorité d'investissement digital.",
      "source": "France Num / Bpifrance — Baromètre Digital PME 2024"
    }},
    {{
      "stat": "2,4×",
      "description": "plus de taux de closing sur des comptes ayant effectué une levée de fonds dans les 18 mois.",
      "source": "Gartner B2B Sales Benchmark — Q3 2023"
    }},
    {{
      "stat": "45k€",
      "description": "budget digital moyen d'une PME 50–200 salariés.",
      "source": "Bpifrance Le Lab — Étude PME & Numérique 2023"
    }}
  ],
  "reasoning": "Explication courte et directe : pourquoi cet ICP précis, pas un autre. Voix affirmative."
}}

Guidelines :
- Les stats sont issues de la connaissance générale du modèle (sans accès web temps réel) — elles sont illustratives
- Cite des sources crédibles et plausibles (Gartner, McKinsey, Bpifrance, INSEE, Forrester, etc.)
- Chiffres précis, pas de fourchettes vagues
- reasoning : paragraphe court, affirmatif, sans jargon

Réponds UNIQUEMENT avec le JSON valide, sans texte avant ou après."""


# ── GÉNÉRATION ───────────────────────────────────────────────────────────────

PROOF_DISCLAIMER = (
    "Données illustratives issues de la connaissance générale du modèle "
    "(sans accès web temps réel). À vérifier avant usage commercial."
)


def generate_icp(product_description: str) -> dict:
    """
    Génère un ICP complet en deux appels Claude.
    Résultat mis en cache (hashlib.md5) pour éviter de rebrûler des crédits sur les mêmes tests.
    """
    cache_key = hashlib.md5(product_description.strip().lower().encode()).hexdigest()
    if cache_key in _icp_cache:
        return _icp_cache[cache_key]

    logs: list[dict] = []

    # Appel 1 — Haiku pour la structure
    structure_prompt = ICP_STRUCTURE_PROMPT.format(product_description=product_description)
    structure_msg = client.messages.create(
        model=MODEL_HAIKU,
        max_tokens=1024,
        messages=[{"role": "user", "content": structure_prompt}]
    )
    raw = _clean_json(structure_msg.content[0].text)
    icp = json.loads(raw)

    logs.append({
        "step": "Génération ICP — structure",
        "model": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "input": structure_prompt,
        "output": raw,
    })

    # Appel 2 — Sonnet pour les preuves
    proof_prompt = PROOF_PROMPT.format(
        product_description=product_description,
        persona_title=icp.get("persona_title", ""),
        sectors=", ".join(icp.get("sectors", [])),
        intent_signals=", ".join(icp.get("intent_signals", [])),
    )
    proof_msg = client.messages.create(
        model=MODEL_SONNET,
        max_tokens=1024,
        messages=[{"role": "user", "content": proof_prompt}]
    )
    raw_proof = _clean_json(proof_msg.content[0].text)
    proof_data = json.loads(raw_proof)

    logs.append({
        "step": "Génération ICP — preuves & raisonnement",
        "model": f"{MODEL_SONNET_LABEL} ({MODEL_SONNET})",
        "input": proof_prompt,
        "output": raw_proof,
    })

    # Merge — avec disclaimer explicite sur les stats
    icp["proof"] = proof_data.get("proof", [])
    icp["reasoning"] = proof_data.get("reasoning", "")
    icp["proof_disclaimer"] = PROOF_DISCLAIMER

    # Provenance — quel modèle a produit quels champs
    icp["_sources"] = {
        "persona_title": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "persona_subtitle": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "sectors": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "company_size": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "job_titles": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "job_departments": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "intent_signals": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "company_profile": f"{MODEL_HAIKU_LABEL} ({MODEL_HAIKU})",
        "proof": f"{MODEL_SONNET_LABEL} ({MODEL_SONNET})",
        "reasoning": f"{MODEL_SONNET_LABEL} ({MODEL_SONNET})",
    }
    icp["_logs"] = logs

    _icp_cache[cache_key] = icp
    return icp


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()
