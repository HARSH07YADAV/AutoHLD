"""
metrics.py — Retrieval and answer-quality evaluation metrics for AutoHLD.

Implements:
  - Precision@K  : fraction of retrieved chunks that are relevant
  - Recall@K     : fraction of relevant chunks that were retrieved
  - MRR          : Mean Reciprocal Rank (how high does the first relevant chunk rank?)
  - Hit Rate@K   : was at least one relevant chunk in the top-K?
  - Faithfulness : does the LLM answer only use information from retrieved chunks?
  - Context Relevance : are the retrieved chunks relevant to the question?
  - Answer Relevance  : does the answer actually address the question?

Design:
  Relevance is determined by page overlap between retrieved chunks and
  the expected ground-truth pages (from a manually curated QA set).
  This avoids needing a second LLM to judge quality — the page-number
  match is deterministic and auditable.

Usage:
  from backend.evaluation.metrics import evaluate_retrieval, evaluate_answer_quality
  results = evaluate_retrieval(doc_id, qa_pairs)
  quality = evaluate_answer_quality(answer, retrieved_chunks, question)
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class QAPair:
    """
    A single ground-truth question-answer pair for evaluation.

    Parameters
    ----------
    question         : Natural language question about the document.
    expected_pages   : Which document pages contain the answer (ground truth).
    expected_keywords: Key terms that should appear in a correct answer.
    category         : Type of question (entity_lookup / relationship / numeric / boolean).
    """
    question:          str
    expected_pages:    list[int]
    expected_keywords: list[str] = field(default_factory=list)
    category:          str       = "entity_lookup"


@dataclass
class RetrievalResult:
    """Per-question retrieval evaluation result."""
    question:          str
    expected_pages:    list[int]
    retrieved_pages:   list[int]
    retrieved_scores:  list[float]
    precision_at_k:    float
    recall_at_k:       float
    reciprocal_rank:   float
    hit:               bool        # at least one relevant page in top-K
    k:                 int


@dataclass
class EvaluationReport:
    """Aggregate evaluation metrics across all QA pairs."""
    doc_id:            str
    k:                 int
    num_questions:     int
    mean_precision:    float
    mean_recall:       float
    mrr:               float        # Mean Reciprocal Rank
    hit_rate:          float        # fraction of questions with at least 1 hit
    per_question:      list[RetrievalResult] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "k":               self.k,
            "num_questions":   self.num_questions,
            "precision_at_k":  round(self.mean_precision, 4),
            "recall_at_k":     round(self.mean_recall, 4),
            "mrr":             round(self.mrr, 4),
            "hit_rate":        round(self.hit_rate, 4),
        }

    def to_table(self) -> str:
        """Return a human-readable table for the panel demo."""
        lines = [
            f"  Retrieval Evaluation — Top-{self.k} Results",
            f"  {'─' * 50}",
            f"  Questions evaluated : {self.num_questions}",
            f"  Precision@{self.k}        : {self.mean_precision:.1%}",
            f"  Recall@{self.k}           : {self.mean_recall:.1%}",
            f"  Hit Rate@{self.k}         : {self.hit_rate:.1%}",
            f"  MRR                : {self.mrr:.4f}",
            "",
            f"  {'Question':<45} {'P@K':>6} {'Recall':>7} {'Hit':>5}",
            f"  {'─' * 67}",
        ]
        for r in self.per_question:
            q_short = r.question[:42] + "..." if len(r.question) > 42 else r.question
            hit_str = "✓" if r.hit else "✗"
            lines.append(
                f"  {q_short:<45} {r.precision_at_k:>5.1%} {r.recall_at_k:>6.1%} {hit_str:>5}"
            )
        return "\n".join(lines)


@dataclass
class AnswerQualityResult:
    """Answer quality evaluation for a single Q&A."""
    question:           str
    answer:             str
    faithfulness_score: float   # 0-1: does answer stay within retrieved context?
    relevance_score:    float   # 0-1: does answer address the question?
    keyword_hit_rate:   float   # fraction of expected_keywords found in answer
    issues:             list[str] = field(default_factory=list)


# ── Retrieval Evaluation ──────────────────────────────────────────────────────

def evaluate_retrieval(
    doc_id: str,
    qa_pairs: list[QAPair],
    k: int = 5,
) -> EvaluationReport:
    """
    Evaluate retrieval quality against a set of ground-truth QA pairs.

    For each question, runs the retriever and compares retrieved page numbers
    to the expected pages. Computes Precision@K, Recall@K, Hit Rate, and MRR.

    Parameters
    ----------
    doc_id   : The document to evaluate against.
    qa_pairs : Ground-truth question/expected-page pairs.
    k        : Number of chunks to retrieve per question (top-K).

    Returns
    -------
    EvaluationReport with per-question and aggregate metrics.
    """
    from backend.pipeline.retriever import retrieve

    per_question_results: list[RetrievalResult] = []

    for qa in qa_pairs:
        try:
            chunks = retrieve(qa.question, doc_id, top_k=k)
            retrieved_pages  = [c.page_num for c in chunks]
            retrieved_scores = [round(c.score, 4) for c in chunks]
        except Exception as exc:
            logger.warning("Retrieval failed for question %r: %s", qa.question[:60], exc)
            retrieved_pages  = []
            retrieved_scores = []

        expected_set  = set(qa.expected_pages)
        retrieved_set = set(retrieved_pages)

        # Precision@K: how many of the retrieved pages are relevant?
        if retrieved_pages:
            precision = len(expected_set & retrieved_set) / len(retrieved_pages)
        else:
            precision = 0.0

        # Recall@K: how many of the expected pages were retrieved?
        if expected_set:
            recall = len(expected_set & retrieved_set) / len(expected_set)
        else:
            recall = 1.0  # vacuously true if nothing was expected

        # Hit Rate: was any expected page in the top-K?
        hit = bool(expected_set & retrieved_set)

        # Reciprocal Rank: rank of the first relevant hit (1-indexed)
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

        logger.debug(
            "Q=%r | expected=%s | retrieved=%s | P@%d=%.2f | RR=%.2f",
            qa.question[:40], qa.expected_pages, retrieved_pages[:k], k, precision, rr,
        )

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


# ── Answer Quality Evaluation ─────────────────────────────────────────────────

def evaluate_answer_quality(
    question:          str,
    answer:            str,
    retrieved_chunks:  list[Any],   # list of RetrievedChunk or dicts with 'text'
    expected_keywords: list[str] | None = None,
) -> AnswerQualityResult:
    """
    Evaluate the quality of a single LLM answer without a second LLM call.

    Metrics
    -------
    faithfulness_score :
        Fraction of answer sentences that can be grounded in the retrieved context.
        A sentence is considered grounded if ≥1 key phrase from it appears in
        the retrieved text. This is a lexical approximation of faithfulness.

    relevance_score :
        Question-answer lexical overlap — how many question content words
        appear in the answer? Penalises "not found" responses.

    keyword_hit_rate :
        Fraction of expected_keywords found in the answer (case-insensitive).
        Requires a manually supplied keyword list; 0.0 if not provided.

    Parameters
    ----------
    question          : The original question asked.
    answer            : The LLM's response text.
    retrieved_chunks  : Chunks passed to the LLM (used for faithfulness check).
    expected_keywords : Optional list of terms that should appear in a good answer.

    Returns
    -------
    AnswerQualityResult with per-metric scores and any detected issues.
    """
    issues: list[str] = []

    # ── Build context corpus ───────────────────────────────────────────────
    context_text = " ".join(
        c.text if hasattr(c, "text") else c.get("text", "")
        for c in retrieved_chunks
    ).lower()

    # ── Faithfulness ──────────────────────────────────────────────────────
    # Split answer into sentences; score each sentence
    sentences = [s.strip() for s in re.split(r"[.!?]", answer) if len(s.strip()) > 10]
    if sentences:
        grounded = 0
        for sent in sentences:
            words = [w for w in sent.lower().split() if len(w) > 4]
            # A sentence is grounded if ≥2 of its content words appear in context
            if not words:
                grounded += 1  # short sentences pass by default
                continue
            matches = sum(1 for w in words if w in context_text)
            if matches >= min(2, len(words)):
                grounded += 1
        faithfulness = grounded / len(sentences)
    else:
        faithfulness = 1.0  # empty/trivial answer

    if faithfulness < 0.5:
        issues.append(f"Low faithfulness ({faithfulness:.1%}): answer may contain hallucinated content.")

    # ── Relevance ─────────────────────────────────────────────────────────
    # Extract content words from question (skip stop words)
    _stop = {"what", "which", "where", "when", "how", "is", "are", "the",
              "a", "an", "of", "in", "to", "for", "do", "does", "does",
              "this", "that", "have", "has", "by", "from", "at", "with"}
    q_words = [w.lower() for w in re.findall(r"\b\w{4,}\b", question) if w.lower() not in _stop]
    if q_words:
        answer_lower = answer.lower()
        hits = sum(1 for w in q_words if w in answer_lower)
        relevance = hits / len(q_words)
    else:
        relevance = 1.0

    if relevance < 0.3:
        issues.append(f"Low relevance ({relevance:.1%}): answer may not address the question.")

    # Detect "not found" responses
    not_found_phrases = [
        "not found in the uploaded document",
        "information was not found",
        "cannot find",
        "not present in the document",
    ]
    is_not_found = any(p in answer.lower() for p in not_found_phrases)
    if is_not_found:
        relevance = max(relevance * 0.5, 0.0)  # penalise "not found" answers
        issues.append("Answer indicates information was not found in the document.")

    # ── Keyword Hit Rate ───────────────────────────────────────────────────
    if expected_keywords:
        answer_lower = answer.lower()
        found = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
        keyword_hit_rate = found / len(expected_keywords)
        if keyword_hit_rate < 0.5:
            missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
            issues.append(f"Missing expected keywords: {missing}")
    else:
        keyword_hit_rate = 0.0  # not evaluated — no keywords provided

    return AnswerQualityResult(
        question           = question,
        answer             = answer,
        faithfulness_score = round(faithfulness, 4),
        relevance_score    = round(relevance, 4),
        keyword_hit_rate   = round(keyword_hit_rate, 4),
        issues             = issues,
    )


# ── Retrieval vs Baseline Comparison ─────────────────────────────────────────

def compare_to_baseline(
    doc_id:   str,
    qa_pairs: list[QAPair],
    k:        int = 5,
) -> dict:
    """
    Compare RAG retrieval to a TF-IDF keyword baseline on the same QA pairs.

    Returns a comparison dict showing RAG wins, losses, and ties per metric.
    The baseline uses BM25-style keyword matching (implemented in baseline.py).

    Parameters
    ----------
    doc_id   : Document to evaluate.
    qa_pairs : Ground-truth QA pairs.
    k        : Top-K for both systems.

    Returns
    -------
    dict with 'rag', 'baseline', and 'comparison' sub-dicts.
    """
    from backend.evaluation.baseline import evaluate_baseline_retrieval

    rag_report      = evaluate_retrieval(doc_id, qa_pairs, k=k)
    baseline_report = evaluate_baseline_retrieval(doc_id, qa_pairs, k=k)

    rag_p  = rag_report.mean_precision
    bas_p  = baseline_report.mean_precision
    rag_hr = rag_report.hit_rate
    bas_hr = baseline_report.hit_rate

    return {
        "rag": {
            "precision_at_k": round(rag_p, 4),
            "recall_at_k":    round(rag_report.mean_recall, 4),
            "hit_rate":       round(rag_hr, 4),
            "mrr":            round(rag_report.mrr, 4),
        },
        "baseline_tfidf": {
            "precision_at_k": round(bas_p, 4),
            "recall_at_k":    round(baseline_report.mean_recall, 4),
            "hit_rate":       round(bas_hr, 4),
            "mrr":            round(baseline_report.mrr, 4),
        },
        "comparison": {
            "precision_improvement": round(rag_p  - bas_p, 4),
            "hit_rate_improvement":  round(rag_hr - bas_hr, 4),
            "rag_wins_precision":    rag_p  > bas_p,
            "rag_wins_hit_rate":     rag_hr > bas_hr,
        },
    }
