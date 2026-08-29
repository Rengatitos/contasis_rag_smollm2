from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from src.rag_engine import ContasisRAG

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("CONTASIS_DATA_DIR", str(ROOT / "data")))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "contasis-smollm2")
DEFAULT_USE_LLM = os.getenv("DEFAULT_USE_LLM", "true").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    title="Contasis Code API",
    version="1.1.0",
    description=(
        "API restringida para devolver códigos Contasis. "
        "El RAG recupera códigos reales y Ollama/SmolLM2 solo puede seleccionar entre candidatos válidos."
    ),
)

rag = ContasisRAG(DATA_DIR, ollama_host=OLLAMA_HOST, model=OLLAMA_MODEL)


class CodigoRequest(BaseModel):
    texto: str = Field(min_length=1, description="Texto, tipo de documento o glosa a clasificar")
    modo: str = Field(default="auto", description="auto | comprobante | identidad | cuenta")
    empresa: Optional[str] = Field(default=None, description="Empresa para priorizar su histórico")
    registro: str = Field(default="COMPRA", description="COMPRA o VENTA")
    use_llm: bool = Field(default=DEFAULT_USE_LLM, description="Usar SmolLM2 como selector entre candidatos recuperados")


def _resolve(req: CodigoRequest) -> str:
    try:
        return rag.responder(
            req.texto,
            modo=req.modo,
            empresa=req.empresa,
            registro=req.registro,
            use_llm=req.use_llm,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="No se pudo resolver el código") from exc


@app.get("/health")
def health():
    ollama_ok = False
    model_available = False
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if r.ok:
            ollama_ok = True
            names = {m.get("name", "") for m in r.json().get("models", [])}
            model_available = OLLAMA_MODEL in names or any(n.startswith(OLLAMA_MODEL + ":") for n in names)
    except requests.RequestException:
        pass
    return {
        "status": "ok",
        "rag_loaded": True,
        "ollama": ollama_ok,
        "model": OLLAMA_MODEL,
        "model_available": model_available,
        "historicos": len(rag.historicos),
        "plan_cuentas": len(rag.plan),
    }


@app.post(
    "/v1/codigo",
    response_class=PlainTextResponse,
    summary="Devuelve únicamente el código",
)
def codigo_post(req: CodigoRequest):
    return PlainTextResponse(_resolve(req), media_type="text/plain; charset=utf-8")


@app.get(
    "/v1/codigo",
    response_class=PlainTextResponse,
    summary="Devuelve únicamente el código mediante query string",
)
def codigo_get(
    texto: str = Query(min_length=1),
    modo: str = "auto",
    empresa: Optional[str] = None,
    registro: str = "COMPRA",
    use_llm: bool = DEFAULT_USE_LLM,
):
    req = CodigoRequest(texto=texto, modo=modo, empresa=empresa, registro=registro, use_llm=use_llm)
    return PlainTextResponse(_resolve(req), media_type="text/plain; charset=utf-8")
