# main.py — Serveur FastAPI PGB Prospecting

import hashlib
import io
import os
import secrets
import smtplib
import time
from contextlib import asynccontextmanager
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Any

from database import AsyncSessionLocal, DBProspect, DBSession, init_db
from icp import generate_icp
from prospecting import search_prospects
from email_gen import generate_cold_email

# ── Config ────────────────────────────────────────────────────────────────────

ALLOWED_EMAILS: set[str] = {
    e.strip().lower()
    for e in os.getenv("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
AUTH_SECRET = os.getenv("AUTH_SECRET", "pgb-prospecting-secret")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "PGB Prospecting <onboarding@resend.dev>")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RAILWAY_URL = os.getenv("RAILWAY_URL", "https://pgb-prospecting.up.railway.app")

MAGIC_LINK_TOKENS: dict[str, dict] = {}  # {token: {email, expires}}
TOKEN_TTL = 900  # 15 minutes
STATUS_ORDER = ["waiting", "followup", "replied", "signed", "lost"]

# Auth active si au moins un des deux mécanismes est configuré
AUTH_ENABLED = bool(ALLOWED_EMAILS or AUTH_PASSWORD)


def _make_session_token(seed: str) -> str:
    """Token de session déterministe — survit aux redéploiements."""
    return hashlib.sha256(f"{seed}:{AUTH_SECRET}".encode()).hexdigest()


def _valid_session(session_token: str | None) -> bool:
    """Vérifie si le cookie de session est valide (email ou mot de passe)."""
    if not session_token:
        return False
    for email in ALLOWED_EMAILS:
        if secrets.compare_digest(session_token, _make_session_token(email)):
            return True
    if AUTH_PASSWORD and secrets.compare_digest(session_token, _make_session_token(AUTH_PASSWORD)):
        return True
    return False


async def _send_magic_link(to_email: str, token: str) -> None:
    """Envoie le magic link via Resend API."""
    link = f"{RAILWAY_URL}/api/verify?token={token}"
    body = (
        f"Bonjour,\n\n"
        f"Voici ton lien de connexion à PGB Prospecting (valable 15 minutes) :\n\n"
        f"{link}\n\n"
        f"Si tu n'as pas demandé ce lien, ignore cet email.\n\n"
        f"— PGB Prospecting"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_FROM,
                "to": [to_email],
                "subject": "PGB Prospecting — Lien de connexion",
                "text": body,
            },
            timeout=10,
        )
        resp.raise_for_status()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PGB Prospecting",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pgb-prospecting.up.railway.app"],
    allow_methods=["POST", "GET", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    public_paths = {"/login", "/api/magic-link", "/api/verify", "/api/login"}
    if request.url.path in public_paths or not AUTH_ENABLED:
        return await call_next(request)
    if not _valid_session(request.cookies.get("pgb_session")):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Non authentifié"})
        return RedirectResponse(url="/login")
    return await call_next(request)


# ── Request models ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str


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


class StatusUpdateRequest(BaseModel):
    action: str | None = None   # 'cycle'
    status: str | None = None   # direct status set


# ── Routes auth ───────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page():
    return FileResponse("login.html")


@app.post("/api/login")
async def api_login(req: LoginRequest):
    if not AUTH_PASSWORD:
        raise HTTPException(status_code=404, detail="Not found")
    if not secrets.compare_digest(req.password, AUTH_PASSWORD):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")
    redirect = RedirectResponse(url="/")
    redirect.set_cookie(
        key="pgb_session",
        value=_make_session_token(AUTH_PASSWORD),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return redirect


@app.post("/api/magic-link")
async def request_magic_link(req: MagicLinkRequest):
    email = req.email.strip().lower()
    if email in ALLOWED_EMAILS and RESEND_API_KEY:
        token = secrets.token_urlsafe(32)
        MAGIC_LINK_TOKENS[token] = {"email": email, "expires": time.time() + TOKEN_TTL}
        try:
            await _send_magic_link(email, token)
        except Exception:
            pass
    return {"success": True}


@app.get("/api/verify")
async def verify_magic_link(token: str):
    entry = MAGIC_LINK_TOKENS.pop(token, None)
    if not entry or time.time() > entry["expires"]:
        return RedirectResponse(url="/login?error=expired")
    redirect = RedirectResponse(url="/")
    redirect.set_cookie(
        key="pgb_session",
        value=_make_session_token(entry["email"]),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return redirect


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

    # Persist to database
    session_id = str(int(time.time() * 1000))
    if AsyncSessionLocal:
        try:
            campaign_name = (
                req.product_description[:50].strip()
                + ("…" if len(req.product_description) > 50 else "")
                + " — " + req.country
            )
            async with AsyncSessionLocal() as db:
                db_session = DBSession(
                    id=session_id,
                    ts=int(time.time() * 1000),
                    date_fr=datetime.now().strftime("%d/%m/%Y"),
                    service=req.product_description[:100],
                    region=req.country,
                    campaign_name=campaign_name,
                    icp=icp,
                )
                db.add(db_session)
                for i, p in enumerate(prospects):
                    db.add(DBProspect(
                        session_id=session_id,
                        idx=i,
                        data=p,
                        status="waiting",
                        note="",
                    ))
                await db.commit()
        except Exception:
            pass  # Ne pas bloquer la réponse si la DB est indisponible

    return {"icp": icp, "prospects": prospects, "session_id": session_id}


@app.get("/api/sessions")
async def get_sessions():
    """Retourne toutes les sessions avec leurs prospects — pour Historique et Campagnes."""
    if not AsyncSessionLocal:
        return []
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBSession)
            .options(selectinload(DBSession.prospects))
            .order_by(DBSession.ts.desc())
        )
        sessions = result.scalars().all()
        return [
            {
                "id": s.id,
                "date": s.date_fr,
                "ts": s.ts,
                "service": s.service,
                "region": s.region,
                "icp": s.icp,
                "campaign_name": s.campaign_name,
                "prospects": [
                    {**p.data, "status": p.status, "note": p.note}
                    for p in s.prospects
                ],
            }
            for s in sessions
        ]


@app.patch("/api/sessions/{session_id}/prospects/{idx}/status")
async def update_prospect_status(session_id: str, idx: int, req: StatusUpdateRequest):
    """Met à jour le statut d'un prospect (cycle ou valeur directe)."""
    if not AsyncSessionLocal:
        raise HTTPException(status_code=503, detail="Base de données non configurée.")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DBProspect).where(
                DBProspect.session_id == session_id,
                DBProspect.idx == idx,
            )
        )
        prospect = result.scalar_one_or_none()
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect non trouvé.")

        if req.action == "cycle":
            cur = prospect.status or "waiting"
            next_idx = (STATUS_ORDER.index(cur) + 1) % len(STATUS_ORDER) if cur in STATUS_ORDER else 0
            prospect.status = STATUS_ORDER[next_idx]
        elif req.status and req.status in STATUS_ORDER:
            prospect.status = req.status

        await db.commit()
        return {"status": prospect.status}


@app.post("/api/generate-email")
async def generate_email_endpoint(req: GenerateEmailRequest):
    if not req.service_description.strip():
        raise HTTPException(status_code=400, detail="Description du service requise.")
    try:
        result = generate_cold_email(req.prospect, req.icp, req.service_description)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur génération email : {str(e)}")


@app.post("/api/send-email")
async def send_email_endpoint(req: SendEmailRequest):
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
