# main.py — Serveur FastAPI PGB Prospecting

import os
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any

from icp import generate_icp
from prospecting import search_prospects
from email_gen import generate_cold_email

app = FastAPI(title="PGB Prospecting")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


# ── Request models ────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    product_description: str
    country: str = "France"
    num_results: int = 15


class GenerateEmailRequest(BaseModel):
    prospect: dict[str, Any]
    icp: dict[str, Any]
    service_description: str


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("index.html")


@app.post("/api/parse-document")
async def parse_document(file: UploadFile = File(...)):
    filename = file.filename or ""
    content = await file.read()

    if filename.endswith(".md") or filename.endswith(".txt"):
        try:
            text = content.decode("utf-8")
        except Exception:
            raise HTTPException(status_code=400, detail="Impossible de lire le fichier texte.")

    elif filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p for p in pages if p.strip())
            if not text.strip():
                raise HTTPException(status_code=422, detail="PDF vide ou non lisible (scanné ?).")
        except ImportError:
            raise HTTPException(status_code=500, detail="pypdf non installé.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur lecture PDF : {str(e)}")
    else:
        raise HTTPException(status_code=415, detail="Format non supporté. Utilise un PDF ou un fichier .md")

    return {"text": text.strip()}


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    if not req.product_description.strip():
        raise HTTPException(status_code=400, detail="Description du service requise.")

    try:
        icp = generate_icp(req.product_description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur ICP : {str(e)}")

    try:
        prospects = search_prospects(icp, country=req.country, num_results=req.num_results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur sourcing : {str(e)}")

    return {"icp": icp, "prospects": prospects}


@app.post("/api/generate-email")
async def generate_email_endpoint(req: GenerateEmailRequest):
    """Génère un cold email personnalisé pour un prospect via Claude Haiku."""
    if not req.service_description.strip():
        raise HTTPException(status_code=400, detail="Description du service requise.")
    try:
        result = generate_cold_email(req.prospect, req.icp, req.service_description)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur génération email : {str(e)}")


@app.post("/api/send-email")
async def send_email_endpoint(req: SendEmailRequest):
    """Envoie un email via Gmail SMTP (app password)."""
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="GMAIL_EMAIL ou GMAIL_APP_PASSWORD manquant dans les variables d'environnement."
        )
    if not req.to or "@" not in req.to:
        raise HTTPException(status_code=400, detail="Adresse email destinataire invalide.")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = req.subject
        msg["From"] = GMAIL_EMAIL
        msg["To"] = req.to
        msg.attach(MIMEText(req.body, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_EMAIL, req.to, msg.as_string())

        return {"success": True, "from": GMAIL_EMAIL, "to": req.to}
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="Authentification Gmail échouée. Vérifie GMAIL_EMAIL et GMAIL_APP_PASSWORD."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur envoi email : {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
