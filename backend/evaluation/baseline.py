"""
baseline.py — TF-IDF keyword baseline retrieval for AutoHLD evaluation.

Purpose:
  Provides a BM25-style keyword matching baseline to compare against the
  semantic RAG retrieval. This answers the panel question:
  "Why use embeddings? How much better is RAG than keyword search?"

Design:
  - Loads all chunks for a document from ChromaDB.
  - Computes TF-IDF scores for each chunk against the query.
  - Returns top-K chunks ranked by keyword overlap score.
  - No neural network involved — pure term statistics.

Usage:
  from backend.evaluation.baseline import evaluate_baseline_retrieval
  report = evaluate_baseline_retrieval(doc_id, qa_pairs, k=5)
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── TF-IDF Retriever ──────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Tokenize text to lowercase alpha-numeric words (≥3 chars)."""
    return [w.lower() for w in re.findall(r"\b[a-zA-Z0-9]{3,}\b", text)]


def _tf(tokens: list[str]) -> dict[str, float]:
    """Term frequency: count / total."""
    total = len(tokens)
    if total == 0:
        return {}
    counts = Counter(tokens)
    return {term: count / total for term, count in counts.items()}


def _idf(term: str, all_docs: list[list[str]]) -> float:
    """
    Inverse document frequency: log((N + 1) / (df + 1)) + 1.
    Smoothed to avoid division-by-zero.
    """
    n  = len(all_docs)
    df = sum(1 for doc in all_docs if term in doc)
    return math.log((n + 1) / (df + 1)) + 1.0


def _tfidf_score(query_tokens: list[str], chunk_tokens: list[str], idf_map: dict) -> float:
    """Dot-product TF-IDF score for a single chunk against a query."""
    tf = _tf(chunk_tokens)
    score = 0.0
    for term in set(query_tokens):
        if term in tf:
            score += idf_map.get(term, 1.0) * tf[term]
    return score


@dataclass
class BaselineChunk:
    """A retrieved chunk from the TF-IDF baseline."""
    page_num: int
    text:     str
    score:    float


def tfidf_retrieve(query: str, doc_id: str, top_k: int = 5) -> list[BaselineChunk]:
    """
    Retrieve top-K chunks using TF-IDF keyword matching.

    Parameters
    ----------
    query  : User question (raw text).
    doc_id : Document to search within.
    top_k  : Number of chunks to return.

    Returns
    -------
    list[BaselineChunk] sorted by TF-IDF score descending.
    """
    from backend.database.vector_db import get_all_chunks_for_doc

    raw_chunks = get_all_chunks_for_doc(doc_id)
    if not raw_chunks:
        logger.warning("No chunks found for doc_id=%s in TF-IDF baseline", doc_id)
        return []

    query_tokens     = _tokenize(query)
    chunk_token_lists = [_tokenize(c["text"]) for c in raw_chunks]

    # Build IDF map over all chunks
    idf_map: dict[str, float] = {}
    for term in set(query_tokens):
        idf_map[term] = _idf(term, chunk_token_lists)

    # Score all chunks
    scored: list[tuple[float, int]] = []
    for idx, chunk_tokens in enumerate(chunk_token_lists):
        score = _tfidf_score(query_tokens, chunk_tokens, idf_map)
        scored.append((score, idx))

    # Sort descending, take top-K
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    results: list[BaselineChunk] = []
    for score, idx in top:
        chunk = raw_chunks[idx]
        page  = int(chunk["metadata"].get("page_num", 0))
        results.append(BaselineChunk(
            page_num = page,
            text     = chunk["text"],
            score    = round(score, 6),
        ))

    logger.debug(
        "TF-IDF baseline: query=%r, top scores=%s",
        query[:40],
        [round(s, 3) for s, _ in top[:3]],
    )
    return results


def evaluate_baseline_retrieval(
    doc_id:   str,
    qa_pairs,          # list[QAPair] — imported from metrics to avoid circular import
    k:        int = 5,
) -> "EvaluationReport":  # noqa: F821
    """
    Run the TF-IDF baseline on all QA pairs and return an EvaluationReport.

    This is used by metrics.compare_to_baseline() to quantify the advantage
    of semantic embedding retrieval over keyword matching.

    Parameters
    ----------
    doc_id   : Document to evaluate.
    qa_pairs : list of QAPair from metrics.py.
    k        : Top-K chunks to retrieve.

    Returns
    -------
    EvaluationReport (same structure as the RAG evaluation).
    """
    from backend.evaluation.metrics import EvaluationReport, RetrievalResult

    per_question_results: list[RetrievalResult] = []

    for qa in qa_pairs:
        chunks = tfidf_retrieve(qa.question, doc_id, top_k=k)
        retrieved_pages  = [c.page_num for c in chunks]
        retrieved_scores = [c.score for c in chunks]

        expected_set  = set(qa.expected_pages)
        retrieved_set = set(retrieved_pages)

        precision = (len(expected_set & retrieved_set) / len(retrieved_pages)) if retrieved_pages else 0.0
        recall    = (len(expected_set & retrieved_set) / len(expected_set))    if expected_set  else 1.0
        hit       = bool(expected_set & retrieved_set)

        rr = 0.0
        for rank, page in enumerate(retrieved_pages, start=1):
            if page in expected_set:
                rr = 1.0 / rank
                break

        per_question_results.append(RetrievalResult(
            question         = qa.question,
            expected_pages   = qa.expected_pages,
            retrieved_pages  = retrieved_pages,
            retrieved_scores = retrieved_scores,
            precision_at_k   = precision,
            recall_at_k      = recall,
            reciprocal_rank  = rr,
            hit              = hit,
            k                = k,
        ))

    n = len(per_question_results)
    if n == 0:
        return EvaluationReport(
            doc_id=doc_id, k=k, num_questions=0,
            mean_precision=0.0, mean_recall=0.0, mrr=0.0, hit_rate=0.0,
        )

    return EvaluationReport(
        doc_id         = doc_id,
        k              = k,
        num_questions  = n,
        mean_precision = sum(r.precision_at_k  for r in per_question_results) / n,
        mean_recall    = sum(r.recall_at_k     for r in per_question_results) / n,
        mrr            = sum(r.reciprocal_rank for r in per_question_results) / n,
        hit_rate       = sum(1 for r in per_question_results if r.hit) / n,
        per_question   = per_question_results,
    )
