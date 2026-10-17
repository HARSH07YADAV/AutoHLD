"""
rag.py — End-to-end RAG orchestrator for AutoHLD.

Responsibility: receive a question and doc_id, run the full pipeline, and
return a structured answer with source citations.

Pipeline:
    1. Retrieve top-k chunks via vector search (retriever.py)
    2. Build a grounded prompt (prompt_builder.py)
    3. Call the LLM (llm_client.py)
    4. Assemble source citations from retriever output (NOT from LLM text)
    5. Persist the Q&A to SQLite (sqlite_db.py)
    6. Return answer + citations to the router

Citation guarantee:
    Citations are derived entirely from the retriever's metadata (page_num,
    section, text excerpt, score). The LLM never generates page numbers —
    it only receives labelled excerpts and is instructed to reference them.
    This makes citations structurally reliable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.database import sqlite_db
from backend.database.sqlite_db import get_document
from backend.database import vector_db
from backend.pipeline import llm_client
from backend.pipeline.prompt_builder import build_no_doc_prompt, build_prompt
from backend.pipeline.retriever import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

# ── Minimum similarity score to include a chunk in the prompt ─────────────────
# Chunks below this threshold are likely noise — unrelated document sections.
MIN_RELEVANCE_SCORE = 0.30

# Max characters of chunk text shown in a citation excerpt
CITATION_EXCERPT_LEN = 300


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class SourceCitation:
    """A single source reference shown below an answer in the UI."""
    page:    int
    section: str
    excerpt: str    # first N chars of the chunk text
    score:   float  # similarity score (informational only)


@dataclass
class RAGAnswer:
    """The complete result returned by ask()."""
    answer:  str
    sources: list[SourceCitation]
    model:   str
    doc_id:  str


# ── Public API ────────────────────────────────────────────────────────────────

def ask(doc_id: str, question: str) -> RAGAnswer:
    """
    Answer a question about an uploaded document using RAG.

    Parameters
    ----------
    doc_id   : Document identifier (must be status='ready' in SQLite).
    question : The engineer's natural language question.

    Returns
    -------
    RAGAnswer
        answer  — the LLM's grounded response text
        sources — list of SourceCitation (page, section, excerpt, score)
        model   — which LLM model answered (for transparency)
        doc_id  — echoed back for the router

    Raises
    ------
    ValueError  — if doc_id doesn't exist or is not yet ready
    ConnectionError — if the LLM backend is unreachable
    """
    # ── Validate document is ready and has chunks ──────────────────────────
    doc = get_document(doc_id)
    if doc is None:
        raise ValueError(f"Document '{doc_id}' not found.")
    if doc.status != "ready":
        raise ValueError(
            f"Document '{doc_id}' is not ready for querying (status: {doc.status})."
        )

    # Verify the document has chunks in ChromaDB (guard against doc_id mismatch)
    chunk_count = vector_db.collection_count(doc_id)
    if chunk_count == 0:
        raise ValueError(
            f"Document '{doc_id}' shows {doc.chunk_count} chunks in the database but "
            "none were found in the vector store. "
            "Please delete and re-upload this document to fix the inconsistency."
        )

    logger.info("RAG query | doc=%s | question=%r", doc_id, question[:80])

    # ── Step 1: Retrieve relevant chunks ──────────────────────────────────
    all_chunks = retrieve(question, doc_id)

    # Filter out low-relevance chunks to avoid polluting the prompt
    relevant_chunks = [c for c in all_chunks if c.score >= MIN_RELEVANCE_SCORE]

    if not relevant_chunks and all_chunks:
        # All chunks scored below threshold — use best one rather than nothing
        relevant_chunks = all_chunks[:1]
        logger.info(
            "All chunks below threshold (%.2f); using top-1 (score=%.3f)",
            MIN_RELEVANCE_SCORE,
            all_chunks[0].score,
        )

    logger.info(
        "Retrieved %d chunks, %d above threshold (%.2f)",
        len(all_chunks), len(relevant_chunks), MIN_RELEVANCE_SCORE,
    )

    # ── Step 2: Build prompt ───────────────────────────────────────────────
    messages = build_prompt(
        question  = question,
        chunks    = relevant_chunks,
        filename  = doc.filename,
    )

    # ── Step 3: Call LLM ──────────────────────────────────────────────────
    answer_text, model_id = llm_client.generate(messages)
    logger.info("LLM answered: model=%s, answer_len=%d", model_id, len(answer_text))

    # ── Step 4: Build citations from retriever output ─────────────────────
    # Citations come from the chunks we passed to the LLM — not from the
    # LLM response. This guarantees citations point to real document pages.
    citations = _build_citations(relevant_chunks)

    # ── Step 5: Persist Q&A ───────────────────────────────────────────────
    sqlite_db.save_query(
        doc_id     = doc_id,
        question   = question,
        answer     = answer_text,
        sources    = [
            {
                "page":    c.page,
                "section": c.section,
                "excerpt": c.excerpt,
                "score":   c.score,
            }
            for c in citations
        ],
        model_used = model_id,
    )

    return RAGAnswer(
        answer  = answer_text,
        sources = citations,
        model   = model_id,
        doc_id  = doc_id,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_citations(chunks: list[RetrievedChunk]) -> list[SourceCitation]:
    """
    Convert retrieved chunks into SourceCitation objects for the UI.

    Deduplicates by page number (same page may appear in multiple chunks).
    Keeps the highest-scoring occurrence of each page.
    Orders by page number for a natural reading order in the UI.
    """
    if not chunks:
        return []

    # Deduplicate: keep highest score per page
    best_by_page: dict[int, RetrievedChunk] = {}
    for chunk in chunks:
        page = chunk.page_num
        if page not in best_by_page or chunk.score > best_by_page[page].score:
            best_by_page[page] = chunk

    # Sort by page number
    sorted_chunks = sorted(best_by_page.values(), key=lambda c: c.page_num)

    return [
        SourceCitation(
            page    = c.page_num,
            section = c.section,
            excerpt = c.text[:CITATION_EXCERPT_LEN].strip(),
            score   = c.score,
        )
        for c in sorted_chunks
    ]
