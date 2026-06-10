# main.py — Serveur FastAPI PGB Prospecting

import hashlib
import io
import os
import secrets
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from typing import Any

from icp import generate_icp
from prospecting import search_prospects
from email_gen import generate_cold_email

# ── Config ────────────────────────────────────────────────────────────────────

ALLOWED_EMAILS: set[str] = {
    e.strip().lower()
    for e in os.getenv("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}
AUTH_SECRET = os.getenv("AUTH_SECRET", "pgb-prospecting-secret")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RAILWAY_URL = os.getenv("RAILWAY_URL", "https://pgb-prospecting.up.railway.app")

MAGIC_LINK_TOKENS: dict[str, dict] = {}  # {token: {email, expires}}
TOKEN_TTL = 900  # 15 minutes


def _make_session_token(email: str) -> str:
    """Token de session déterministe par email — survit aux redéploiements."""
    return hashlib.sha256(f"{email.lower()}:{AUTH_SECRET}".encode()).hexdigest()


def _send_magic_link(to_email: str, token: str) -> None:
    """Envoie le magic link par email via Gmail SMTP."""
    link = f"{RAILWAY_URL}/api/verify?token={token}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "PGB Prospecting — Lien de connexion"
    msg["From"] = GMAIL_EMAIL
    msg["To"] = to_email
    body = (
        f"Bonjour,\n\n"
        f"Voici ton lien de connexion à PGB Prospecting (valable 15 minutes) :\n\n"
        f"{link}\n\n"
        f"Si tu n'as pas demandé ce lien, ignore cet email.\n\n"
        f"— PGB Prospecting"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_EMAIL, to_email, msg.as_string())


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PGB Prospecting",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pgb-prospecting.up.railway.app"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Protège toutes les routes sauf /login, /api/magic-link, /api/verify.
    Si ALLOWED_EMAILS n'est pas défini (dev local), laisse tout passer.
    """
    public_paths = {"/login", "/api/magic-link", "/api/verify"}
    if request.url.path in public_paths or not ALLOWED_EMAILS:
        return await call_next(request)

    session_token = request.cookies.get("pgb_session")
    valid = session_token and any(
        secrets.compare_digest(session_token, _make_session_token(e))
        for e in ALLOWED_EMAILS
    )
    if not valid:
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Non authentifié"})
        return RedirectResponse(url="/login")

    return await call_next(request)


# ── Request models ────────────────────────────────────────────────────────────

class MagicLinkRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class GenerateRequest(BaseModel):
    product_description: str = Field(min_length=20, max_length=5000)
    country: str = Field(default="France", max_length=50)
    num_results: int = Field(default=15, ge=5, le=30)


class GenerateEmailRequest(BaseModel):
    prospect: dict[str, Any]
    icp: dict[str, Any]
    service_description: str


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


# ── Routes auth ───────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page():
    return FileResponse("login.html")


@app.post("/api/magic-link")
async def request_magic_link(req: MagicLinkRequest):
    """Envoie un magic link si l'email est dans la whitelist.
    Retourne toujours 200 pour ne pas révéler quels emails sont autorisés.
    """
    email = req.email.strip().lower()
    if email in ALLOWED_EMAILS and GMAIL_EMAIL and GMAIL_APP_PASSWORD:
        token = secrets.token_urlsafe(32)
        MAGIC_LINK_TOKENS[token] = {"email": email, "expires": time.time() + TOKEN_TTL}
        try:
            _send_magic_link(email, token)
        except Exception:
            pass  # Silent fail — ne pas révéler l'erreur
    return {"success": True}


@app.get("/api/verify")
async def verify_magic_link(token: str, response: Response):
    """Valide le magic link, pose le cookie de session, redirige vers /."""
    entry = MAGIC_LINK_TOKENS.pop(token, None)
    if not entry or time.time() > entry["expires"]:
        return RedirectResponse(url="/login?error=expired")

    response.set_cookie(
        key="pgb_session",
        value=_make_session_token(entry["email"]),
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=30 * 24 * 3600,  # 30 jours
    )
    return RedirectResponse(url="/")


@app.post("/api/logout")
async def api_logout(response: Response):
    response.delete_cookie("pgb_session")
    return {"success": True}


# ── Routes app ────────────────────────────────────────────────────────────────

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
        prospects = await search_prospects(icp, country=req.country, num_results=req.num_results)
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
