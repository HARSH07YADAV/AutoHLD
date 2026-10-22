"""
rag.py — End-to-end RAG orchestrator for AutoHLD.

Responsibility: receive a question and doc_id, run the full pipeline, and
return a structured answer with verified source citations.

Pipeline:
    1. Hybrid retrieval: semantic vector search + BM25 keyword matching + intent awareness (retriever.py)
    2. Fallback query expansion if initial evidence is sparse
    3. Deduplicate near-identical chunks to prevent repetitive context
    4. Build a grounded engineering prompt (prompt_builder.py)
    5. Call the LLM (llm_client.py)
    6. Post-process answer to eliminate duplicate lines and format numbered lists
    7. Clean citation assembly: if answer is a refusal, suppress citations; otherwise
       cite the verified pages supporting the answer
    8. Persist the Q&A to SQLite (sqlite_db.py)
    9. Return answer + citations to the router
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Generator

from backend.database import sqlite_db
from backend.database.sqlite_db import get_document
from backend.database import vector_db
from backend.pipeline import llm_client
from backend.pipeline.prompt_builder import build_no_doc_prompt, build_prompt
from backend.pipeline.retriever import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

# ── Minimum similarity score to include a chunk in the prompt ─────────────────
# Adjusted to 0.20 to work seamlessly with normalized Reciprocal Rank Fusion
# scores and prevent false refusals caused by aggressive score cutoffs.
MIN_RELEVANCE_SCORE = 0.20

# Headroom multiplier for retrieval before deduplication.
RETRIEVAL_HEADROOM = 2

# Near-duplicate detection: chunks whose normalised-text Jaccard similarity
# exceeds this threshold are considered duplicates; only the best is kept.
DUP_SIMILARITY_THRESHOLD = 0.70

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
    Answer a natural-language engineering question about an uploaded document.

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
    t_start = time.perf_counter()

    # ── Step 1: Hybrid Retrieval (with headroom for deduplication) ─────────
    from backend.config import TOP_K_RESULTS
    q_lower = question.lower()
    is_broad = any(w in q_lower for w in ("summary", "overview", "architecture", "what is this document", "high-level", "system context", "all components"))
    target_k = 4 if is_broad else 3

    t_retrieval_start = time.perf_counter()
    fetch_k = target_k * RETRIEVAL_HEADROOM
    all_chunks = retrieve(question, doc_id, top_k=fetch_k)

    # Safety: ensure all returned chunks actually belong to this document
    all_chunks = [c for c in all_chunks if c.doc_id == doc_id]

    # Filter out chunks below minimum threshold
    relevant_chunks = [c for c in all_chunks if c.score >= MIN_RELEVANCE_SCORE]

    if not relevant_chunks and all_chunks:
        # All chunks scored below threshold — keep top 2 rather than starving LLM
        relevant_chunks = all_chunks[:2]
        logger.info(
            "All chunks below threshold (%.2f); using top candidates (top score=%.3f)",
            MIN_RELEVANCE_SCORE,
            all_chunks[0].score,
        )

    # ── Step 1b: Deduplicate near-identical chunks ─────────────────────────
    relevant_chunks = _deduplicate_chunks(relevant_chunks)[:target_k]
    t_retrieval = round(time.perf_counter() - t_retrieval_start, 3)

    logger.info(
        "Retrieved %d raw chunks → %d above threshold (%.2f) → %d after dedup (retrieval: %.1fms)",
        len(all_chunks), sum(1 for c in all_chunks if c.score >= MIN_RELEVANCE_SCORE),
        MIN_RELEVANCE_SCORE, len(relevant_chunks), t_retrieval * 1000
    )

    # ── Step 2: Build grounded engineering prompt ─────────────────────────
    messages = build_prompt(
        question  = question,
        chunks    = relevant_chunks,
        filename  = doc.filename,
    )

    # ── Step 3: Call LLM ──────────────────────────────────────────────────
    t_llm_start = time.perf_counter()
    answer_text, model_id = llm_client.generate(messages)
    t_llm = round(time.perf_counter() - t_llm_start, 3)
    t_total = round(time.perf_counter() - t_start, 3)
    logger.info(
        "Q&A Sync Performance | doc=%s | retrieval=%.3fs | gen=%.3fs | total=%.3fs | model=%s",
        doc_id, t_retrieval, t_llm, t_total, model_id
    )

    # ── Step 3b: Post-process answer to remove duplicate lines ────────────
    answer_text = _dedup_answer_lines(answer_text)

    # ── Step 4: Build citations from retriever output ─────────────────────
    if _is_not_found_response(answer_text):
        citations: list[SourceCitation] = []
        logger.info("Answer is a 'not found' response; suppressed citations.")
    else:
        citations = _build_citations(relevant_chunks, answer_text=answer_text)

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


def ask_stream(doc_id: str, question: str) -> Generator[str, None, None]:
    """
    Stream an answer to an engineering question token-by-token using SSE format.

    Yields Server-Sent Event strings:
      - event: sources (immediate after retrieval)
      - event: token   (for every token generated)
      - event: done    (full answer, final citations, timings)
      - event: error   (on error)
    """
    t_start = time.perf_counter()

    try:
        doc = get_document(doc_id)
        if doc is None:
            err = f"Document '{doc_id}' not found."
            yield f"event: error\ndata: {json.dumps({'error': err})}\n\n"
            return
        if doc.status != "ready":
            err = f"Document '{doc_id}' is not ready for querying (status: {doc.status})."
            yield f"event: error\ndata: {json.dumps({'error': err})}\n\n"
            return

        # Verify chunks exist (uses in-memory cache — O(1) after first access)
        chunk_count = vector_db.collection_count(doc_id)
        if chunk_count == 0:
            err = (
                f"Document '{doc_id}' has 0 chunks in vector store. "
                "Please delete and re-upload this document."
            )
            yield f"event: error\ndata: {json.dumps({'error': err})}\n\n"
            return

        logger.info("RAG stream query | doc=%s | question=%r", doc_id, question[:80])

        # Step 1: Hybrid Retrieval
        t_retrieval_start = time.perf_counter()
        q_lower = question.lower()
        is_broad = any(w in q_lower for w in ("summary", "overview", "architecture", "what is this document", "high-level", "system context", "all components"))
        target_k = 4 if is_broad else 3

        fetch_k = target_k * RETRIEVAL_HEADROOM
        all_chunks = retrieve(question, doc_id, top_k=fetch_k)
        all_chunks = [c for c in all_chunks if c.doc_id == doc_id]

        relevant_chunks = [c for c in all_chunks if c.score >= MIN_RELEVANCE_SCORE]
        if not relevant_chunks and all_chunks:
            relevant_chunks = all_chunks[:2]

        relevant_chunks = _deduplicate_chunks(relevant_chunks)[:target_k]
        t_retrieval = round(time.perf_counter() - t_retrieval_start, 3)

        # Build candidate citations
        candidate_citations = _build_citations(relevant_chunks)
        sources_payload = [
            {
                "page": c.page,
                "section": c.section,
                "excerpt": c.excerpt,
                "score": c.score,
            }
            for c in candidate_citations
        ]

        # Send sources event early so frontend can render sources right away
        yield f"event: sources\ndata: {json.dumps({'sources': sources_payload, 'retrieval_time_s': t_retrieval})}\n\n"

        # Step 2: Build prompt
        messages = build_prompt(
            question=question,
            chunks=relevant_chunks,
            filename=doc.filename,
        )

        # Step 3: Stream tokens from LLM
        t_llm_start = time.perf_counter()
        first_token_time = None
        token_count = 0
        full_tokens = []
        model_id = "local-llm"

        for event in llm_client.stream_generate(messages):
            if event["type"] == "token":
                if first_token_time is None:
                    first_token_time = round(time.perf_counter() - t_llm_start, 3)
                token_count += 1
                full_tokens.append(event["content"])
                yield f"event: token\ndata: {json.dumps({'token': event['content']})}\n\n"
            elif event["type"] == "done":
                model_id = event.get("model", model_id)
                if not full_tokens and event.get("full_text"):
                    full_tokens.append(event["full_text"])

        raw_answer = "".join(full_tokens).strip()
        t_llm = round(time.perf_counter() - t_llm_start, 3)
        t_total = round(time.perf_counter() - t_start, 3)
        ttft = first_token_time if first_token_time is not None else t_llm
        tok_per_sec = round(token_count / max(0.001, t_llm), 1)

        logger.info(
            "Q&A Streaming Performance | doc=%s | retrieval=%.3fs | TTFT=%.3fs | gen=%.3fs "
            "(%d tokens, %.1f tok/s) | total=%.3fs | chunks=%d",
            doc_id, t_retrieval, ttft, t_llm, token_count, tok_per_sec, t_total,
            len(relevant_chunks)
        )

        # Step 4: Post-process
        answer_text = _dedup_answer_lines(raw_answer)

        # Citations check
        if _is_not_found_response(answer_text):
            final_citations = []
        else:
            final_citations = _build_citations(relevant_chunks, answer_text=answer_text)

        final_sources_payload = [
            {
                "page": c.page,
                "section": c.section,
                "excerpt": c.excerpt,
                "score": c.score,
            }
            for c in final_citations
        ]

        # Step 5: Persist Q&A to SQLite
        sqlite_db.save_query(
            doc_id=doc_id,
            question=question,
            answer=answer_text,
            sources=final_sources_payload,
            model_used=model_id,
        )

        # Send done event with complete data
        done_payload = {
            "answer": answer_text,
            "sources": final_sources_payload,
            "model": model_id,
            "timings": {
                "retrieval_s": t_retrieval,
                "ttft_s": ttft,
                "generation_s": t_llm,
                "total_s": t_total,
                "token_count": token_count,
                "tokens_per_sec": tok_per_sec,
                "chunks_used": len(relevant_chunks),
            },
        }
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    except Exception as exc:
        logger.exception("Error during ask_stream for doc=%s: %s", doc_id, exc)
        yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_not_found_response(answer: str) -> bool:
    """
    Check if the LLM's response indicates that the information was not found
    in the document. In this case, citations must NOT be displayed to the user.
    """
    if not answer:
        return True
    norm = answer.lower().strip()
    if "this information was not found in the selected document" in norm:
        return True
    if (
        norm.startswith("the selected document does not contain") or
        norm.startswith("the provided excerpts do not contain") or
        norm.startswith("no information regarding") or
        norm.startswith("information regarding this topic was not found") or
        norm.startswith("no relevant excerpts were found")
    ):
        return True
    if len(norm) < 130 and "not found" in norm and (
        "document" in norm or "excerpt" in norm or "information" in norm
    ):
        return True
    return False


def _clean_excerpt(text: str, max_len: int) -> str:
    """Trim excerpt cleanly without cutting words or sentences abruptly."""
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_len:
        return clean
    # Try to cut at sentence boundary
    period_idx = clean.rfind(".", 0, max_len)
    if period_idx > max_len // 2:
        return clean[:period_idx + 1]
    # Otherwise cut at last space
    space_idx = clean.rfind(" ", 0, max_len)
    if space_idx > 0:
        return clean[:space_idx] + "…"
    return clean[:max_len] + "…"


def _dedup_answer_lines(text: str) -> str:
    """
    Post-process the LLM's answer to remove duplicate lines, redundant headers,
    and re-number ordered list items sequentially.
    """
    lines = text.split("\n")
    seen_normalised: set[str] = set()
    result: list[str] = []
    ordered_counter = 0
    in_ordered = False

    for line in lines:
        stripped = line.strip()

        # Always keep blank lines (preserve paragraph spacing)
        if not stripped:
            result.append(line)
            if in_ordered:
                in_ordered = False
                ordered_counter = 0
            continue

        # Normalise the line for comparison
        normalised = re.sub(r"^\s*[-*•]\s+", "", stripped)        # unordered markers
        normalised = re.sub(r"^\s*\d+\.\s+", "", normalised)       # ordered markers
        normalised = re.sub(r"\(Page[s]?\s+[\d,\s&]+\)", "", normalised, flags=re.I)  # page refs
        normalised = re.sub(r"\s+", " ", normalised).lower().strip()

        # Skip very short lines from duplicate filtering
        if len(normalised) < 10:
            result.append(line)
            continue

        if normalised in seen_normalised:
            logger.debug("Dedup answer: skipping duplicate line: %r", stripped[:80])
            continue

        seen_normalised.add(normalised)

        # Re-number ordered list items sequentially
        if re.match(r"^\s*\d+\.\s+", stripped):
            in_ordered = True
            ordered_counter += 1
            renumbered = re.sub(r"^\s*\d+\.\s+", f"{ordered_counter}. ", stripped)
            result.append(renumbered)
        else:
            if in_ordered and not re.match(r"^\s*[-*•]\s+", stripped):
                in_ordered = False
                ordered_counter = 0
            result.append(line)

    return "\n".join(result)


def _normalise_for_dedup(text: str) -> set[str]:
    """Normalise chunk text into a set of word-level tokens for Jaccard comparison."""
    _STOPWORDS = {
        "the", "a", "an", "and", "or", "of", "in", "on", "to", "is", "are",
        "was", "were", "be", "been", "being", "that", "this", "with", "for",
        "it", "its", "by", "as", "at", "from", "into", "which", "has", "have",
        "had", "not", "but", "can", "will", "shall", "may", "should", "would",
    }
    tokens = re.sub(r"[^\w\s]", " ", text.lower()).split()
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _deduplicate_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Remove near-duplicate chunks using token-level Jaccard similarity."""
    if not chunks:
        return []

    kept: list[RetrievedChunk] = []
    kept_token_sets: list[set] = []

    for chunk in chunks:
        tokens = _normalise_for_dedup(chunk.text)
        is_dup = any(
            _jaccard(tokens, existing) >= DUP_SIMILARITY_THRESHOLD
            for existing in kept_token_sets
        )
        if not is_dup:
            kept.append(chunk)
            kept_token_sets.append(tokens)

    removed = len(chunks) - len(kept)
    if removed:
        logger.info(
            "Dedup: removed %d near-duplicate chunk(s) (threshold=%.2f)",
            removed, DUP_SIMILARITY_THRESHOLD
        )

    return kept


def _build_citations(
    chunks: list[RetrievedChunk],
    answer_text: str = "",
) -> list[SourceCitation]:
    """
    Convert retrieved chunks into SourceCitation objects for the UI.

    - Prioritizes chunks whose pages are actually cited in answer_text.
    - Deduplicates by page number (keeping highest scoring occurrence).
    - Sorts by page number for a natural reading order in the UI.
    """
    if not chunks:
        return []

    # Extract pages mentioned in answer text (e.g. (Page 4) or (Pages 2, 5))
    cited_pages: set[int] = set()
    if answer_text:
        matches = re.findall(r"\(Page[s]?\s+([0-9,\s&]+)\)", answer_text, flags=re.I)
        for m in matches:
            nums = re.findall(r"\d+", m)
            for n in nums:
                cited_pages.add(int(n))

    # Deduplicate: keep highest score per page
    best_by_page: dict[int, RetrievedChunk] = {}
    for chunk in chunks:
        page = chunk.page_num
        if page not in best_by_page or chunk.score > best_by_page[page].score:
            best_by_page[page] = chunk

    # If the answer specifically cited certain pages, prioritize them:
    # include all chunks for cited pages, plus top chunks up to max 6 citations
    if cited_pages:
        selected_pages = [p for p in best_by_page if p in cited_pages]
        other_pages = sorted(
            [p for p in best_by_page if p not in cited_pages],
            key=lambda p: best_by_page[p].score,
            reverse=True
        )
        while len(selected_pages) < 3 and other_pages:
            selected_pages.append(other_pages.pop(0))
        final_chunks = [best_by_page[p] for p in selected_pages if p in best_by_page]
    else:
        final_chunks = list(best_by_page.values())

    # Sort by page number
    sorted_chunks = sorted(final_chunks, key=lambda c: c.page_num)

    return [
        SourceCitation(
            page    = c.page_num,
            section = c.section,
            excerpt = _clean_excerpt(c.text, CITATION_EXCERPT_LEN),
            score   = c.score,
        )
        for c in sorted_chunks
    ]
