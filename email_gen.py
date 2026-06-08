# email_gen.py — Génération de cold email personnalisé via Claude Haiku
# Voix PGB : manifesto, court, confiant. Phrases 6–12 mots max.

import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

COLD_EMAIL_PROMPT = """Tu es un expert en prospection B2B pour Pillet Grenié BUREAU, une agence d'intégration digitale haut de gamme.

Tu dois rédiger un cold email ultra-personnalisé pour ce prospect :

PROSPECT :
- Prénom : {first_name}
- Nom : {last_name}
- Poste : {poste}
- Entreprise : {entreprise}
- Secteur : {secteur}
- Taille : {taille}
- LinkedIn : {linkedin}
- Site web : {website}

ARGUMENTS DE MATCHING (pourquoi ce prospect est pertinent) :
{arguments}

NOTRE SERVICE :
{service_description}

ANGLE D'APPROCHE :
{outreach_angle}

Rédige un cold email en français avec la voix PGB :
- Manifesto. Court. Confiant.
- Phrases de 6–12 mots, jamais deux longues d'affilée.
- Accroche personnalisée sur le prospect (jamais générique)
- Corps : 3–4 phrases max. Une observation précise sur leur contexte, une proposition directe.
- CTA : une question courte ou un appel à action clair.
- Maximum 8 lignes de corps.
- Signe : "Louison\nPillet Grenié BUREAU."

À bannir absolument : "j'espère que vous allez bien", "je me permets de vous contacter", "je suis convaincu que", "synergies", "solution clé en main".

Format JSON :
{{
  "subject": "Sujet court, intrigant, personnalisé — sans spam words — max 8 mots",
  "body": "Corps complet de l'email avec salutation, corps, CTA et signature"
}}

Réponds UNIQUEMENT avec le JSON valide, sans markdown, sans texte avant ou après."""


def generate_cold_email(prospect: dict, icp: dict, service_description: str) -> dict:
    """
    Génère un cold email personnalisé pour un prospect.
    Returns: {"subject": str, "body": str}
    """
    nom = prospect.get("Nom", "")
    parts = nom.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    args = prospect.get("arguments") or []
    args_text = "\n".join(f"- {a.get('text', '')}" for a in args if a.get("text"))

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": COLD_EMAIL_PROMPT.format(
                first_name=first_name,
                last_name=last_name,
                poste=prospect.get("Poste", ""),
                entreprise=prospect.get("Entreprise", ""),
                secteur=prospect.get("Secteur", ""),
                taille=prospect.get("Taille", ""),
                linkedin=prospect.get("LinkedIn", ""),
                website=prospect.get("Website", ""),
                arguments=args_text or "Aucun argument disponible",
                service_description=service_description,
                outreach_angle=icp.get("outreach_angle", ""),
            )
        }]
    )

    raw = _clean_json(msg.content[0].text)
    result = json.loads(raw)

    if "subject" not in result or "body" not in result:
        raise ValueError("Réponse Claude incomplète : champs subject/body manquants")

    return result


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()
