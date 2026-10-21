"""
main.py — FastAPI application entry point for AutoHLD.

Responsibilities:
  - Create the FastAPI app with metadata
  - Initialise the SQLite database on startup
  - Register all API routers
  - Serve the frontend as static files
  - Configure logging
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import threading

from backend.database.sqlite_db import init_db
from backend.pipeline.embedder import warm_up_embedder
from backend.pipeline.llm_client import warm_up_llm
from backend.routers import ingest, query, analysis

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt = "%H:%M:%S",
    stream  = sys.stdout,
)
logger = logging.getLogger("autohld")


# ── Startup / shutdown ────────────────────────────────────────────────────────
def _warmup_background():
    """Run warm-up routines asynchronously so server starts instantly without blocking requests."""
    logger.info("Starting background pipeline pre-warmup...")
    warm_up_embedder()
    warm_up_llm()
    logger.info("Pipeline pre-warmup completed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources before the server starts accepting requests."""
    logger.info("AutoHLD starting up …")
    init_db()
    logger.info("SQLite database ready.")
    threading.Thread(target=_warmup_background, daemon=True, name="autohld-warmup").start()
    yield
    logger.info("AutoHLD shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "AutoHLD API",
    description = "AUTOSAR HLD Document Analysis Assistant — Backend API",
    version     = "0.1.0",
    lifespan    = lifespan,
)

# Allow the browser to call the API even when running on different ports
# (relevant during development when the frontend is served separately)
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(analysis.router)

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "version": "0.1.0"}


# ── Approach justification endpoint ───────────────────────────────────────────
@app.get("/api/approach", tags=["system"])
async def get_approach_info() -> dict:
    """
    Return documented design decisions: RAG approach rationale, hyperparameter
    choices, and embedding model comparison. Useful for panel/audit transparency.
    """
    from backend.config import (
        RAG_APPROACH_RATIONALE,
        EMBEDDING_MODEL_OPTIONS,
        CHUNK_SIZE_VARIANTS,
        TOP_K_VARIANTS,
        CHUNK_SIZE_CHARS,
        CHUNK_OVERLAP_CHARS,
        TOP_K_RESULTS,
        EMBEDDING_MODEL,
        LLM_PROVIDER,
        OLLAMA_MODEL,
    )
    return {
        "approach": RAG_APPROACH_RATIONALE,
        "hyperparameters": {
            "active": {
                "chunk_size_chars":    CHUNK_SIZE_CHARS,
                "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
                "top_k_results":       TOP_K_RESULTS,
                "embedding_model":     EMBEDDING_MODEL,
                "llm_provider":        LLM_PROVIDER,
                "ollama_model":        OLLAMA_MODEL,
            },
            "variants_studied": {
                "chunk_size":  CHUNK_SIZE_VARIANTS,
                "top_k":       TOP_K_VARIANTS,
            },
        },
        "embedding_models_compared": EMBEDDING_MODEL_OPTIONS,
        "rag_pipeline_stages": [
            "1. PDF upload → pdfplumber text+table extraction (doc_processor.py)",
            "2. Scanned-page detection → image_count + empty text ⇒ OCR warning",
            "3. Sliding-window chunking 1800 chars / 200 overlap (chunker.py)",
            "4. Sentence-transformer embedding all-MiniLM-L6-v2 384-dim (embedder.py)",
            "5. ChromaDB cosine similarity storage → persistent local vector store",
            "6. Query embedding → top-5 chunk retrieval (retriever.py)",
            "7. MIN_RELEVANCE=0.30 threshold filtering (rag.py)",
            "8. Grounded prompt assembly with [Page N | Section] labels (prompt_builder.py)",
            "9. Local LLM inference via Ollama (llm_client.py)",
            "10. Citation assembly from retriever metadata — NOT from LLM output",
            "11. Q&A + citations persisted to SQLite (sqlite_db.py)",
        ],
        "evaluation_endpoints": [
            "GET /api/eda/{doc_id}           — chunk stats, vocabulary, AUTOSAR keyword freq",
            "GET /api/evaluate/{doc_id}      — Precision@K, Recall@K, MRR, HitRate + TF-IDF baseline",
            "POST /api/evaluate/{doc_id}/answer — faithfulness + relevance scoring",
        ],
    }

# ── Frontend static files ─────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info("Serving frontend from: %s", FRONTEND_DIR)
else:
    logger.warning("Frontend directory not found at %s — UI will not be served.", FRONTEND_DIR)
