# main.py — Serveur FastAPI PGB Prospecting

import os, io
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from icp import generate_icp
from prospecting import search_prospects

app = FastAPI(title="PGB Prospecting")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    product_description: str
    country: str = "France"
    num_results: int = 15


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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
