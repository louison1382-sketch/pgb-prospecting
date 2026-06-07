# icp.py — Génération d'ICP via Claude API
#
# Ce fichier prend une description de service et retourne un ICP structuré.
# Il appelle Claude (modèle Haiku, rapide et bon marché) avec un prompt précis
# et parse la réponse JSON.

import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ICP_PROMPT = """
Tu es un expert en marketing B2B et prospection commerciale.

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
  "outreach_angle": "Une phrase résumant l'angle d'approche cold email"
}}

Guidelines :
- sectors : 3 à 5 secteurs prioritaires en français
- job_titles : 3 à 5 titres de poste en français, les plus pertinents pour ce service
- job_departments : en anglais minuscule (ex: finance, operations, c-suite, marketing, sales)
- intent_signals : signaux observables qui indiquent un besoin (ex: recrutement d'un DAF, levée de fonds récente, expansion internationale)
- red_flags : critères qui disqualifient un prospect
- outreach_angle : une phrase précise, pas générique

Réponds UNIQUEMENT avec le JSON valide, sans texte avant ou après.
"""


def generate_icp(product_description: str) -> dict:
    """
    Génère un ICP structuré à partir d'une description de service.
    
    Args:
        product_description: La description du service ou produit à prospecter.
    
    Returns:
        Un dictionnaire avec les champs de l'ICP (sectors, job_titles, etc.)
    """
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": ICP_PROMPT.format(product_description=product_description)
            }
        ]
    )

    raw = message.content[0].text.strip()
    icp = json.loads(raw)
    return icp
