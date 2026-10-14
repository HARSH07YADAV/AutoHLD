"""
analysis.py (router) — Endpoints for entity extraction, relationships, consistency checks,
                        document EDA statistics, and retrieval quality evaluation.

POST /api/extract/{doc_id}              — Run entity extraction on a document.
GET  /api/entities/{doc_id}             — Return previously extracted entities.
GET  /api/relationships/{doc_id}        — Return inferred component relationships.
POST /api/inconsistencies/{doc_id}      — Run consistency checks and return findings.
GET  /api/inconsistency-report/{doc_id} — Return persisted consistency findings.
GET  /api/eda/{doc_id}                  — Return EDA statistics for a document.
GET  /api/evaluate/{doc_id}             — Run retrieval evaluation vs TF-IDF baseline.
POST /api/evaluate/{doc_id}/answer      — Evaluate answer quality for a Q&A pair.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from backend.analysis.extractor import extract_entities
from backend.analysis.inconsistency import check_consistency
from backend.analysis.pdf_generator import generate_pdf_report
from backend.analysis.report_builder import generate_markdown_report, generate_report_data
from backend.database.sqlite_db import (
    get_document,
    get_entities,
    get_inconsistencies,
    get_query_history,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/extract/{doc_id}")
async def run_extraction(doc_id: str) -> JSONResponse:
    """
    Extract AUTOSAR entities from an uploaded document.

    Runs: regex patterns → confidence scoring → relationship inference → SQLite persist.
    Safe to call multiple times (re-extraction overwrites previous results).
    """
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    if doc.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not ready (status: {doc.status}).",
        )

    try:
        result = extract_entities(doc_id)
    except Exception as exc:
        logger.exception("Extraction failed for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Extraction error: {exc}")

    return JSONResponse(content={
        "doc_id":   doc_id,
        "summary":  result.summary(),
        "entities": {
            "components": [_entity_to_dict(e) for e in result.components],
            "ports":      [_entity_to_dict(e) for e in result.ports],
            "interfaces": [_entity_to_dict(e) for e in result.interfaces],
            "signals":    [_entity_to_dict(e) for e in result.signals],
            "runnables":  [_entity_to_dict(e) for e in result.runnables],
        },
        "relationships": [_rel_to_dict(r) for r in result.relationships],
    })


@router.get("/entities/{doc_id}")
async def get_extracted_entities(doc_id: str) -> JSONResponse:
    """Return previously extracted entities from SQLite (no re-extraction)."""
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    raw = get_entities(doc_id)
    if not raw:
        return JSONResponse(content={"doc_id": doc_id, "entities": [], "extracted": False})

    # Group by entity_type
    grouped: dict[str, list] = {}
    for e in raw:
        t = e["entity_type"]
        grouped.setdefault(t, []).append({
            "name":        e["name"],
            "entity_type": t,
            "subtype":     e["details"].get("subtype", ""),
            "page":        e["page_ref"],
            "source_text": e["details"].get("source_text", ""),
            "confidence":  e["details"].get("confidence", "medium"),
        })

    return JSONResponse(content={
        "doc_id":    doc_id,
        "entities":  grouped,
        "extracted": True,
        "summary":   {t: len(v) for t, v in grouped.items()},
    })


@router.get("/relationships/{doc_id}")
async def get_relationships(doc_id: str) -> JSONResponse:
    """
    Re-run extraction and return relationship graph data.

    Returns component nodes and directed edges for the UI relationship view.
    """
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready.")

    try:
        result = extract_entities(doc_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Build a clean graph structure for the UI
    nodes = []
    for c in result.components:
        nodes.append({"id": c.name, "type": "component", "page": c.page, "confidence": c.confidence})
    for i in result.interfaces:
        nodes.append({"id": i.name, "type": "interface", "page": i.page, "confidence": i.confidence})

    edges = []
    for r in result.relationships:
        edges.append({
            "source":     r.source,
            "target":     r.target,
            "relation":   r.relation,
            "page":       r.page,
            "confidence": r.confidence,
        })

    return JSONResponse(content={
        "doc_id": doc_id,
        "nodes":  nodes,
        "edges":  edges,
        "ports":  [_entity_to_dict(p) for p in result.ports],
    })


# ── Inconsistency endpoints ──────────────────────────────────────────────────

@router.post("/inconsistencies/{doc_id}")
async def run_consistency_check(doc_id: str) -> JSONResponse:
    """
    Run all consistency checks on a document and return findings.

    This is a preliminary, AI-assisted consistency review — NOT a full
    AUTOSAR validator. Every finding includes the rule that triggered it
    and must be reviewed by an engineer before any action is taken.
    """
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    if doc.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not ready (status: {doc.status}).",
        )

    try:
        report = check_consistency(doc_id)
    except Exception as exc:
        logger.exception("Consistency check failed for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Check failed: {exc}")

    return JSONResponse(content={
        "doc_id":   doc_id,
        "summary":  report.summary(),
        "findings": [
            {
                "title":       f.title,
                "description": f.description,
                "severity":    f.severity,
                "category":    f.category,
                "evidence":    f.evidence,
                "pages":       f.pages,
                "reason":      f.reason,
            }
            for f in report.findings
        ],
        "disclaimer": (
            "These findings are AI-assisted preliminary observations. "
            "They do not constitute a formal AUTOSAR validation. "
            "Engineer review is required before any conclusions are drawn."
        ),
    })


@router.get("/inconsistency-report/{doc_id}")
async def get_inconsistency_report(doc_id: str) -> JSONResponse:
    """Return persisted consistency findings without re-running the checks."""
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    findings = get_inconsistencies(doc_id)
    return JSONResponse(content={
        "doc_id":   doc_id,
        "findings": findings,
        "checked":  len(findings) > 0,
    })


# ── Dashboard & Report endpoints ─────────────────────────────────────────────

@router.get("/dashboard/{doc_id}")
async def get_dashboard_data(doc_id: str) -> JSONResponse:
    """Return aggregated dashboard engineering metrics for a specific document."""
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    entities = get_entities(doc_id)
    inconsistencies = get_inconsistencies(doc_id)
    queries = get_query_history(doc_id)

    components = [e for e in entities if e["entity_type"] == "component"]
    interfaces = [e for e in entities if e["entity_type"] == "interface"]
    ports = [e for e in entities if e["entity_type"] == "port"]
    signals = [e for e in entities if e["entity_type"] == "signal"]

    sev_counts = {"warning": 0, "review": 0, "info": 0}
    for item in inconsistencies:
        s = item.get("severity", "info")
        sev_counts[s] = sev_counts.get(s, 0) + 1

    return JSONResponse(content={
        "doc_id": doc_id,
        "filename": doc.filename,
        "status": doc.status,
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
        "upload_time": doc.upload_time.isoformat() if doc.upload_time else None,
        "entity_counts": {
            "components": len(components),
            "interfaces": len(interfaces),
            "ports": len(ports),
            "signals": len(signals),
            "total": len(entities),
        },
        "query_count": len(queries),
        "recent_queries": [
            {
                "id": q["id"],
                "question": q["question"],
                "model_used": q["model_used"],
                "created_at": q["created_at"],
                "sources_count": len(q.get("sources", [])),
            }
            for q in queries[:5]
        ],
        "inconsistency_summary": {
            "total": len(inconsistencies),
            "warning": sev_counts.get("warning", 0),
            "review": sev_counts.get("review", 0),
            "info": sev_counts.get("info", 0),
        },
        "extracted": len(entities) > 0,
        "inconsistencies_checked": len(inconsistencies) > 0,
    })


@router.get("/reports/{doc_id}")
async def get_engineering_report(
    doc_id: str,
    include_qa: bool = True,
) -> JSONResponse:
    """
    Return compiled engineering report JSON + Markdown preview.

    Query params
    ------------
    include_qa : bool (default True) — include Q&A session log and findings.
    """
    try:
        data = generate_report_data(doc_id, include_qa=include_qa)
        md   = generate_markdown_report(doc_id, include_qa=include_qa)
        return JSONResponse(content={
            "report_data": data,
            "markdown":    md,
        })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to build report for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Report generation error: {exc}")


@router.get("/reports/{doc_id}/download")
async def download_engineering_report_pdf(
    doc_id: str,
    include_qa: bool = True,
) -> Response:
    """
    Download the engineering report as a properly-paginated PDF.

    All 13 sections, entities, Q&A log, traceability index and sign-off
    are rendered into a multi-page PDF with headers, footers, and page numbers.
    """
    try:
        data     = generate_report_data(doc_id, include_qa=include_qa)
        pdf_bytes = generate_pdf_report(data)
        clean_name = data["filename"].replace(".pdf", "").replace(" ", "_")
        filename   = f"{clean_name}_AutoHLD_Engineering_Report.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to generate PDF for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"PDF generation error: {exc}")


@router.get("/reports/{doc_id}/download/markdown")
async def download_engineering_report_markdown(
    doc_id: str,
    include_qa: bool = True,
) -> Response:
    """Download the engineering report as a Markdown (.md) text attachment."""
    try:
        data = generate_report_data(doc_id, include_qa=include_qa)
        md   = generate_markdown_report(doc_id, include_qa=include_qa)
        clean_name = data["filename"].replace(".pdf", "").replace(" ", "_")
        filename   = f"{clean_name}_AutoHLD_Engineering_Report.md"
        return Response(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to download Markdown for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Download error: {exc}")


# ── EDA endpoint ──────────────────────────────────────────────────────────────

@router.get("/eda/{doc_id}")
async def get_eda_report(doc_id: str) -> JSONResponse:
    """
    Return Exploratory Data Analysis statistics for a document.

    Computes chunk size distribution, vocabulary stats, AUTOSAR keyword
    frequency, table/section coverage, and embedding model information.
    Requires the document to be fully ingested (status='ready').
    """
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    if doc.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not ready for analysis (status: {doc.status}).",
        )

    try:
        from backend.evaluation.eda import analyze_document
        report = analyze_document(doc_id)
        return JSONResponse(content={
            "doc_id": doc_id,
            "eda":    report.to_dict(),
            "text_summary": report.to_text(),
        })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("EDA failed for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"EDA error: {exc}")


# ── Retrieval evaluation endpoint ─────────────────────────────────────────────

@router.get("/evaluate/{doc_id}")
async def get_retrieval_evaluation(
    doc_id: str,
    k: int = 5,
    compare_baseline: bool = True,
) -> JSONResponse:
    """
    Run retrieval quality evaluation on the built-in sample QA set.

    Computes Precision@K, Recall@K, Hit Rate, and MRR for the semantic
    RAG retriever. Optionally compares against a TF-IDF keyword baseline
    to quantify the benefit of semantic embeddings over keyword matching.

    Query params
    ------------
    k                : Top-K chunks to retrieve (default 5).
    compare_baseline : Include TF-IDF baseline comparison (default True).
    """
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    if doc.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready.")

    try:
        from backend.evaluation.metrics import evaluate_retrieval, QAPair, compare_to_baseline

        # ── Built-in QA set for AUTOSAR BMS documents ──────────────────────
        # These work for any AUTOSAR HLD document that follows standard
        # naming conventions. For best results use the sample BMS document.
        qa_pairs = [
            QAPair(
                question         = "What software components are described in this document?",
                expected_pages   = [1, 2, 3],
                expected_keywords= ["SWC", "component", "software"],
                category         = "entity_lookup",
            ),
            QAPair(
                question         = "What ports does the BatteryManagement component have?",
                expected_pages   = [3, 4, 5],
                expected_keywords= ["port", "P-Port", "R-Port"],
                category         = "entity_lookup",
            ),
            QAPair(
                question         = "Which interfaces are used in the system?",
                expected_pages   = [2, 3, 4, 5],
                expected_keywords= ["interface", "PortInterface"],
                category         = "entity_lookup",
            ),
            QAPair(
                question         = "What signals are produced by the thermal management component?",
                expected_pages   = [4, 5, 6],
                expected_keywords= ["signal", "ThermalManagement"],
                category         = "relationship",
            ),
            QAPair(
                question         = "What is the battery voltage signal value?",
                expected_pages   = [2, 3],
                expected_keywords= ["voltage", "battery", "signal"],
                category         = "numeric",
            ),
        ]

        rag_report = evaluate_retrieval(doc_id, qa_pairs, k=k)
        result = {
            "doc_id":       doc_id,
            "k":            k,
            "rag_metrics":  rag_report.summary(),
            "table":        rag_report.to_table(),
            "per_question": [
                {
                    "question":        r.question,
                    "expected_pages":  r.expected_pages,
                    "retrieved_pages": r.retrieved_pages,
                    "retrieved_scores":r.retrieved_scores,
                    "precision_at_k":  round(r.precision_at_k, 4),
                    "recall_at_k":     round(r.recall_at_k, 4),
                    "reciprocal_rank": round(r.reciprocal_rank, 4),
                    "hit":             r.hit,
                }
                for r in rag_report.per_question
            ],
        }

        if compare_baseline:
            comparison = compare_to_baseline(doc_id, qa_pairs, k=k)
            result["baseline_comparison"] = comparison

        return JSONResponse(content=result)

    except Exception as exc:
        logger.exception("Evaluation failed for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Evaluation error: {exc}")


@router.post("/evaluate/{doc_id}/answer")
async def evaluate_answer_quality(
    doc_id: str,
    payload: dict,
) -> JSONResponse:
    """
    Evaluate the quality of a single answer returned by the RAG pipeline.

    Measures faithfulness (does the answer stay within retrieved context?),
    relevance (does it address the question?), and keyword hit rate.

    Body
    ----
    question          : str   — the original question
    answer            : str   — the LLM answer to evaluate
    expected_keywords : list  — optional list of terms expected in a good answer
    """
    question          = payload.get("question", "")
    answer            = payload.get("answer", "")
    expected_keywords = payload.get("expected_keywords", [])

    if not question or not answer:
        raise HTTPException(status_code=422, detail="'question' and 'answer' are required.")

    try:
        from backend.evaluation.metrics import evaluate_answer_quality as _eval
        from backend.pipeline.retriever import retrieve

        chunks = retrieve(question, doc_id, top_k=5)
        result = _eval(question, answer, chunks, expected_keywords or None)

        return JSONResponse(content={
            "doc_id":            doc_id,
            "question":          result.question,
            "faithfulness":      result.faithfulness_score,
            "relevance":         result.relevance_score,
            "keyword_hit_rate":  result.keyword_hit_rate,
            "issues":            result.issues,
            "overall_quality":   round(
                (result.faithfulness_score + result.relevance_score) / 2, 4
            ),
        })

    except Exception as exc:
        logger.exception("Answer quality eval failed for doc=%s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail=f"Evaluation error: {exc}")


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _entity_to_dict(e) -> dict:
    return {
        "name":        e.name,
        "entity_type": e.entity_type,
        "subtype":     e.subtype,
        "page":        e.page,
        "source_text": e.source_text,
        "confidence":  e.confidence,
    }


def _rel_to_dict(r) -> dict:
    return {
        "source":      r.source,
        "source_type": r.source_type,
        "target":      r.target,
        "target_type": r.target_type,
        "relation":    r.relation,
        "page":        r.page,
        "confidence":  r.confidence,
    }
