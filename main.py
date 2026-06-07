# main.py — Serveur FastAPI PGB Prospecting

import os
from fastapi import FastAPI, HTTPException
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
