"""
query.py (router) — HTTP endpoints for RAG-based Q&A.

POST /api/ask              — Ask a question about an uploaded document.
GET  /api/history/{doc_id} — Return past Q&A for a document.
GET  /api/llm/status       — Check if the LLM backend is reachable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from backend.database.sqlite_db import get_document, get_query_history
from backend.models.schemas import AskRequest, AskResponse, SourceCitation
from backend.pipeline import llm_client
from backend.pipeline.rag import ask, ask_stream

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["query"])


@router.post("/ask/stream")
async def ask_question_stream(body: AskRequest):
    """
    Stream an answer to a natural language question token-by-token (SSE).
    Yields sources, token deltas, and completion metrics with zero buffering.
    """
    doc = get_document(body.doc_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{body.doc_id}' not found. Upload a document first.",
        )
    if doc.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Document is still being processed. Please wait and try again.",
        )
    if doc.status == "error":
        raise HTTPException(
            status_code=422,
            detail=f"Document processing failed: {doc.error_msg}",
        )

    return StreamingResponse(
        ask_stream(doc_id=body.doc_id, question=body.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ask", response_model=AskResponse)
async def ask_question(body: AskRequest) -> AskResponse:
    """
    Answer a natural language question about an uploaded AUTOSAR HLD document.

    Runs the full RAG pipeline:
      1. Embeds the question
      2. Retrieves the top-k most relevant chunks from ChromaDB
      3. Builds a grounded prompt with page-labelled context
      4. Calls the LLM (Ollama or OpenAI)
      5. Returns the answer with source citations (page numbers)

    The answer is grounded in the document — the LLM is instructed not to
    invent information. If the answer is not found in the document, the
    response will explicitly state that.
    """
    # Validate document exists and is ready
    doc = get_document(body.doc_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{body.doc_id}' not found. Upload a document first.",
        )
    if doc.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Document is still being processed. Please wait and try again.",
        )
    if doc.status == "error":
        raise HTTPException(
            status_code=422,
            detail=f"Document processing failed: {doc.error_msg}",
        )

    try:
        result = ask(doc_id=body.doc_id, question=body.question)
    except ConnectionError as exc:
        # LLM backend not reachable
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )
    except ValueError as exc:
        # Document not found, not ready, or vector store inconsistency
        err = str(exc)
        if "vector store" in err:
            raise HTTPException(status_code=422, detail=err)
        raise HTTPException(status_code=400, detail=err)
    except Exception as exc:
        logger.exception("Unexpected RAG error for doc=%s: %s", body.doc_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"An internal error occurred while generating the answer: {exc}",
        )

    return AskResponse(
        answer  = result.answer,
        sources = [
            SourceCitation(
                page    = s.page,
                section = s.section,
                excerpt = s.excerpt,
                score   = s.score,
            )
            for s in result.sources
        ],
        model   = result.model,
    )


@router.get("/history/{doc_id}")
async def get_history(doc_id: str) -> JSONResponse:
    """
    Return all past Q&A entries for a document, newest first.

    Used by the UI to populate the query history panel.
    """
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    history = get_query_history(doc_id)
    return JSONResponse(content={"doc_id": doc_id, "history": history})


@router.get("/llm/status")
async def llm_status() -> JSONResponse:
    """
    Check whether the configured LLM backend is reachable.

    Used by the UI to show a connection indicator without revealing
    internal configuration details.
    """
    from backend.config import LLM_PROVIDER, OLLAMA_MODEL, OPENAI_MODEL

    if LLM_PROVIDER == "ollama":
        available = llm_client.is_ollama_available()
        return JSONResponse(content={
            "provider":  "ollama",
            "model":     OLLAMA_MODEL,
            "available": available,
            "message":   "Ollama is running." if available
                         else "Ollama is not reachable. Run: ollama serve",
        })
    else:
        from backend.config import OPENAI_API_KEY
        has_key = bool(OPENAI_API_KEY)
        return JSONResponse(content={
            "provider":  "openai",
            "model":     OPENAI_MODEL,
            "available": has_key,
            "message":   "OpenAI API key configured." if has_key
                         else "OPENAI_API_KEY is not set in .env",
        })
