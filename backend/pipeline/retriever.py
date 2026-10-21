"""
retriever.py — Hybrid semantic vector and lexical keyword search with
intent-awareness and fallback expansion for AutoHLD.

Responsibilities:
  - Accept a natural language question and a doc_id.
  - Analyze question intent and expand domain acronyms / synonyms (query_expander.py).
  - Execute dense vector search via ChromaDB embeddings.
  - Execute lexical BM25/keyword search across all document chunks.
  - Combine scores using Reciprocal Rank Fusion (RRF) with section-heading and entity bonuses.
  - Apply fallback retrieval with expanded terminology if initial evidence is sparse.
  - Ensure document overview queries receive high-level architectural & summary chunks.
  - Return results as RetrievedChunk objects, sorted by relevance score.

Page numbers in returned chunks are the source of citations and are strictly preserved.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

from backend.config import TOP_K_RESULTS
from backend.database.vector_db import get_all_chunks_for_doc, query_chunks
from backend.pipeline.embedder import embed_query
from backend.pipeline.query_expander import QueryIntent, analyze_query

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single chunk returned by hybrid search, ready for prompt assembly."""
    text:        str
    page_num:    int
    section:     str
    chunk_index: int
    score:       float       # blended similarity score 0.0–1.0 (higher = more relevant)
    doc_id:      str
    filename:    str


# ── Lexical search & scoring helpers ──────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words/acronyms for lexical matching."""
    return re.findall(r"\b[a-zA-Z0-9_\-]+\b", text.lower())


def _score_chunk_lexical(
    chunk_text: str,
    chunk_section: str,
    keywords: list[str],
    expanded_terms: list[str],
    entities: list[str],
) -> float:
    """
    Compute a lexical relevance score for a chunk against query terms.
    Includes term frequency, section heading bonus, and exact entity bonuses.
    """
    if not chunk_text:
        return 0.0

    text_lower = chunk_text.lower()
    section_lower = chunk_section.lower()
    tokens = _tokenize(text_lower)
    token_count = max(1, len(tokens))

    score = 0.0

    # 1. Primary keywords match (BM25-style term frequency)
    for kw in keywords:
        tf = tokens.count(kw)
        if tf > 0:
            # Saturated term frequency
            score += (tf / (tf + 1.2)) * 1.5

        # Section heading bonus
        if kw in section_lower:
            score += 1.0

    # 2. Expanded terms match (moderate weight)
    for term in expanded_terms:
        if term in text_lower:
            score += 0.8
        if term in section_lower:
            score += 0.5

    # 3. Exact entity match (high priority for SWCs, ports, interfaces)
    for ent in entities:
        ent_lower = ent.lower()
        if ent_lower in text_lower:
            score += 2.0
        if ent_lower in section_lower:
            score += 1.5

    return score


def _reciprocal_rank_fusion(
    dense_ranks: dict[str, int],
    lexical_ranks: dict[str, int],
    dense_weight: float = 0.5,
    lexical_weight: float = 0.5,
    k: int = 60,
) -> dict[str, float]:
    """
    Combine rankings from dense vector search and lexical search using RRF.
    Score = sum(weight / (k + rank))
    """
    all_keys = set(dense_ranks.keys()) | set(lexical_ranks.keys())
    fused_scores: dict[str, float] = {}

    for key in all_keys:
        d_rank = dense_ranks.get(key, 999)
        l_rank = lexical_ranks.get(key, 999)

        d_score = dense_weight / (k + d_rank)
        l_score = lexical_weight / (k + l_rank)
        fused_scores[key] = d_score + l_score

    # Normalize fused scores to 0.0 - 1.0 range
    if fused_scores:
        max_score = max(fused_scores.values())
        if max_score > 0:
            for k_item in fused_scores:
                fused_scores[k_item] = round(fused_scores[k_item] / max_score, 4)

    return fused_scores


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    question: str,
    doc_id:   str,
    top_k:    int = TOP_K_RESULTS,
) -> list[RetrievedChunk]:
    """
    Retrieve the top-k most relevant chunks using hybrid search, intent
    classification, and fallback expansion within the selected document.

    Parameters
    ----------
    question : str
        The user's natural language question.
    doc_id : str
        Only chunks from this document are searched (strict isolation).
    top_k : int
        Number of chunks to return. Defaults to TOP_K_RESULTS.

    Returns
    -------
    list[RetrievedChunk]
        Ordered by descending score (most relevant first).
    """
    if not question.strip():
        return []

    logger.debug("Hybrid retrieve top-%d chunks for doc_id=%s | query=%r", top_k, doc_id, question[:80])

    # 1. Analyze query intent and expansions
    analysis = analyze_query(question)

    # 2. Get all stored chunks for this document for lexical indexing & fallback
    all_stored_chunks = get_all_chunks_for_doc(doc_id)
    if not all_stored_chunks:
        logger.info("No chunks stored for doc_id=%s.", doc_id)
        return []

    # Map chunk_id/index to chunk dict
    chunk_by_idx: dict[int, dict] = {}
    for c in all_stored_chunks:
        idx = int(c["metadata"].get("chunk_index", len(chunk_by_idx)))
        chunk_by_idx[idx] = c

    # 3. Dense Vector Search (Primary)
    query_vector = embed_query(question)
    dense_fetch_k = min(len(all_stored_chunks), max(top_k * 3, 15))
    raw_dense_results = query_chunks(
        query_embedding=query_vector,
        doc_id=doc_id,
        n_results=dense_fetch_k,
    )

    dense_ranks: dict[str, int] = {}
    dense_scores: dict[str, float] = {}
    for rank, r in enumerate(raw_dense_results, 1):
        idx_key = str(r["metadata"].get("chunk_index", rank))
        dense_ranks[idx_key] = rank
        dense_scores[idx_key] = float(r["score"])

    # 4. Lexical Search
    lexical_scores_raw: list[tuple[str, float]] = []
    for c in all_stored_chunks:
        meta = c["metadata"]
        idx_key = str(meta.get("chunk_index", 0))
        lex_score = _score_chunk_lexical(
            chunk_text=c["text"],
            chunk_section=meta.get("section", ""),
            keywords=analysis.keywords,
            expanded_terms=analysis.expanded_terms,
            entities=analysis.entities,
        )
        if lex_score > 0:
            lexical_scores_raw.append((idx_key, lex_score))

    # Sort by lexical score descending to assign ranks
    lexical_scores_raw.sort(key=lambda x: x[1], reverse=True)
    lexical_ranks: dict[str, int] = {
        item[0]: rank for rank, item in enumerate(lexical_scores_raw, 1)
    }

    # 5. Hybrid Reciprocal Rank Fusion (RRF)
    # Give higher lexical weight for exact entity or port/signal queries
    if analysis.entities or analysis.intent == QueryIntent.PORTS_INTERFACES:
        dense_w, lex_w = 0.4, 0.6
    else:
        dense_w, lex_w = 0.5, 0.5

    fused_scores = _reciprocal_rank_fusion(
        dense_ranks=dense_ranks,
        lexical_ranks=lexical_ranks,
        dense_weight=dense_w,
        lexical_weight=lex_w,
    )

    # 6. Intent-Aware Boost & Overview Injection
    # For Document Overview, prioritize Title, Executive Summary, Table of Contents, System Context
    overview_boost_indices: set[str] = set()
    if analysis.is_overview:
        for c in all_stored_chunks:
            meta = c["metadata"]
            p = int(meta.get("page_num", 0))
            sec = meta.get("section", "").lower()
            idx_key = str(meta.get("chunk_index", 0))

            if p in (1, 2, 3, 4) or any(w in sec for w in ["summary", "context", "overview", "introduction", "scope", "architecture"]):
                overview_boost_indices.add(idx_key)
                fused_scores[idx_key] = max(fused_scores.get(idx_key, 0.0), 0.95 - (p * 0.02))

    # 7. Targeted Fallback Retrieval Strategy:
    # Only retry if top relevance is weak (< 0.50) and fewer than 2 chunks matched well
    top_dense_score = max(dense_scores.values(), default=0.0)
    high_confidence_count = sum(1 for s in fused_scores.values() if s >= 0.35)
    if high_confidence_count < 2 and top_dense_score < 0.50 and len(analysis.suggested_search_queries) > 1:
        fallback_q = analysis.suggested_search_queries[1]
        logger.debug("Targeted fallback retrieval: doc=%s | fallback_q=%r", doc_id, fallback_q)
        fb_vector = embed_query(fallback_q)
        fb_results = query_chunks(
            query_embedding=fb_vector,
            doc_id=doc_id,
            n_results=min(len(all_stored_chunks), top_k),
        )
        for r in fb_results:
            idx_key = str(r["metadata"].get("chunk_index", 0))
            fb_score = float(r["score"])
            if fb_score > 0.20:
                current_s = fused_scores.get(idx_key, 0.0)
                fused_scores[idx_key] = max(current_s, round(fb_score * 0.85, 4))

    # 8. Build Sorted RetrievedChunk list
    sorted_idx_keys = sorted(
        fused_scores.keys(),
        key=lambda k: fused_scores[k],
        reverse=True
    )

    results: list[RetrievedChunk] = []
    seen_texts: set[str] = set()

    for idx_key in sorted_idx_keys:
        try:
            chunk_int_idx = int(idx_key)
        except ValueError:
            continue

        c = chunk_by_idx.get(chunk_int_idx)
        if not c:
            continue

        # Prevent exact duplicate text in results
        text_norm = c["text"].strip()
        if text_norm in seen_texts:
            continue
        seen_texts.add(text_norm)

        meta = c["metadata"]
        score = fused_scores.get(idx_key, 0.0)

        # Scale and ensure score is strictly between 0.0 and 1.0
        clamped_score = min(1.0, max(0.0, score))

        results.append(
            RetrievedChunk(
                text=c["text"],
                page_num=int(meta.get("page_num", 0)),
                section=meta.get("section", ""),
                chunk_index=chunk_int_idx,
                score=clamped_score,
                doc_id=meta.get("doc_id", doc_id),
                filename=meta.get("filename", ""),
            )
        )

        if len(results) >= top_k:
            break

    logger.debug(
        "Hybrid search produced %d chunks for doc=%s (top score: %.3f)",
        len(results), doc_id, results[0].score if results else 0.0
    )

    return results
