"""
retriever.py — Vector search: embed a query and return the top-k most
relevant chunks from ChromaDB for a specific document.

Responsibility:
  - Accept a natural language question and a doc_id.
  - Embed the question using the same model used at ingestion time.
  - Query ChromaDB for the top-k semantically closest chunks.
  - Return results as RetrievedChunk objects, sorted by relevance score.

The page_num in every returned chunk is the citation source — it must
never be transformed or discarded here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.config import TOP_K_RESULTS
from backend.database.vector_db import query_chunks
from backend.pipeline.embedder import embed_query

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single chunk returned by vector search, ready for prompt assembly."""
    text:        str
    page_num:    int
    section:     str
    chunk_index: int
    score:       float       # cosine similarity 0.0–1.0 (higher = more relevant)
    doc_id:      str
    filename:    str


def retrieve(
    question: str,
    doc_id:   str,
    top_k:    int = TOP_K_RESULTS,
) -> list[RetrievedChunk]:
    """
    Embed the question and return the top-k most relevant chunks.

    Parameters
    ----------
    question : str
        The user's natural language question.
    doc_id : str
        Only chunks from this document are searched.
    top_k : int
        Number of chunks to return. Defaults to TOP_K_RESULTS from config.

    Returns
    -------
    list[RetrievedChunk]
        Ordered by descending similarity score (most relevant first).
        Empty list if the document has no chunks or the query fails.
    """
    if not question.strip():
        return []

    logger.debug("Retrieving top-%d chunks for doc_id=%s", top_k, doc_id)

    # Embed the question with the same model used at ingestion
    query_vector = embed_query(question)

    # Query ChromaDB — filtered to this document only
    raw_results = query_chunks(
        query_embedding = query_vector,
        doc_id          = doc_id,
        n_results       = top_k,
    )

    if not raw_results:
        logger.info("No chunks retrieved for doc_id=%s — document may be empty.", doc_id)
        return []

    chunks = [
        RetrievedChunk(
            text        = r["text"],
            page_num    = int(r["metadata"].get("page_num", 0)),
            section     = r["metadata"].get("section", ""),
            chunk_index = int(r["metadata"].get("chunk_index", 0)),
            score       = float(r["score"]),
            doc_id      = r["metadata"].get("doc_id", doc_id),
            filename    = r["metadata"].get("filename", ""),
        )
        for r in raw_results
    ]

    logger.debug(
        "Retrieved %d chunks; top score=%.3f, bottom score=%.3f",
        len(chunks),
        chunks[0].score if chunks else 0,
        chunks[-1].score if chunks else 0,
    )

    return chunks
