# icp.py — Génération d'ICP via Claude API

import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ICP_PROMPT = """Tu es un expert en marketing B2B et prospection commerciale.

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
  }},
  "proof": [
    {{
      "stat": "78%",
      "description": "des PME françaises citent la productivité comme priorité d'investissement digital. Les DAF sont signataires directs sur ce type de budget.",
      "source": "France Num / Bpifrance — Baromètre Digital PME 2024"
    }},
    {{
      "stat": "2,4×",
      "description": "plus de taux de closing sur des comptes ayant effectué une levée de fonds dans les 18 mois — fenêtre de dépense active.",
      "source": "Gartner B2B Sales Benchmark — Q3 2023"
    }},
    {{
      "stat": "45k€",
      "description": "budget digital moyen d'une PME 50–200 salariés. Positionné sur la tranche basse — sans négociation longue.",
      "source": "Bpifrance Le Lab — Étude PME & Numérique 2023"
    }}
  ],
  "reasoning": "Explication courte et directe : pourquoi cet ICP précis, pas un autre. Voix affirmative."
}}

Guidelines :
- sectors : 3 à 5 secteurs prioritaires en français
- job_titles : 3 à 5 titres de poste en français, les plus pertinents pour ce service
- job_departments : en anglais minuscule (ex: finance, operations, c-suite, marketing, sales)
- intent_signals : signaux observables qui indiquent un besoin
- red_flags : critères qui disqualifient un prospect
- outreach_angle : une phrase précise, pas générique
- persona_title : format court type "DAF / DG" ou "Head of Ops / COO"
- proof : exactement 3 statistiques réelles et vérifiables avec source précise
- reasoning : paragraphe court, affirmatif, sans jargon

Réponds UNIQUEMENT avec le JSON valide, sans texte avant ou après."""


def generate_icp(product_description: str) -> dict:
    """
    Génère un ICP structuré à partir d'une description de service.
    """
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": ICP_PROMPT.format(product_description=product_description)
            }
        ]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    icp = json.loads(raw)
    return icp
