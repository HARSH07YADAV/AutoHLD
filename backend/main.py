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
import time

from backend.database.sqlite_db import init_db, list_documents
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
def _pre_warm_vector_cache() -> None:
    """
    Pre-populate the in-memory chunk cache for all 'ready' documents.

    ChromaDB's first .get() call per document takes 300-400ms (disk I/O + deserialize).
    By loading all chunks at startup we eliminate this cold-start hit on the first user query.
    """
    try:
        from backend.database import vector_db
        docs = list_documents()
        ready_docs = [d for d in docs if d.status == "ready"]
        if not ready_docs:
            logger.info("Vector cache pre-warm: no ready documents found.")
            return
        t0 = time.perf_counter()
        total_chunks = 0
        for doc in ready_docs:
            chunks = vector_db.get_all_chunks_for_doc(doc.doc_id)
            total_chunks += len(chunks)
        elapsed = round(time.perf_counter() - t0, 3)
        logger.info(
            "Vector cache pre-warmed: %d docs, %d chunks loaded in %.3fs.",
            len(ready_docs), total_chunks, elapsed
        )
    except Exception as exc:
        logger.warning("Vector cache pre-warm failed (non-fatal): %s", exc)


def _warmup_background():
    """
    Warm Ollama LLM in background (takes 8-15s for gemma3:4b).

    Embedder and ChromaDB are warmed synchronously in lifespan() because they are fast
    (≤5s combined). Ollama runs here so the server starts accepting requests immediately
    while the model loads — streaming answers may be delayed only for the very first
    request if it arrives before this thread completes.
    """
    logger.info("Background: warming Ollama model (keep_alive=-1) ...")
    t0 = time.perf_counter()
    warm_up_llm()
    logger.info("Background: Ollama warm-up done in %.1fs.", time.perf_counter() - t0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources before the server starts accepting requests."""
    logger.info("AutoHLD starting up …")
    t_start = time.perf_counter()

    # Step 1: SQLite schema (near-instant)
    init_db()
    logger.info("SQLite database ready (%.0fms).", (time.perf_counter() - t_start) * 1000)

    # Step 2: Embedding model — warm synchronously (~3-5s first load, instant if cached)
    # This ensures the first user query NEVER pays the model-load penalty.
    t_emb = time.perf_counter()
    warm_up_embedder()
    logger.info("Embedding model ready (%.1fs).", time.perf_counter() - t_emb)

    # Step 3: ChromaDB chunk cache — pre-load all ready documents into memory
    # Eliminates the 300-400ms first-access disk I/O delay per document.
    t_vec = time.perf_counter()
    _pre_warm_vector_cache()
    logger.info("ChromaDB cache ready (%.1fs).", time.perf_counter() - t_vec)

    # Step 4: Ollama LLM — warm in background thread (8-15s for gemma3:4b)
    # Uses keep_alive=-1 so model stays in RAM for the server's entire lifetime.
    threading.Thread(target=_warmup_background, daemon=True, name="autohld-llm-warmup").start()

    logger.info("AutoHLD startup complete in %.1fs (Ollama warming in background).",
                time.perf_counter() - t_start)
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
