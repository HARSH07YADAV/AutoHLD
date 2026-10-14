"""
report_builder.py — Structured engineering analysis report generator for AutoHLD.

IMPORTANT DISCLAIMER
--------------------
Reports produced by this module are AI-ASSISTED ENGINEERING ANALYSIS documents.
They are NOT formal AUTOSAR compliance validations or architecture approvals.
Every finding, entity, and dependency link cited here was produced by automated
pattern-matching and/or large-language-model inference over the uploaded document.
Human engineering review and sign-off is required before acting on any finding.

Report Sections
---------------
  1.  Cover & Identification
  2.  Engineering Notice (disclaimer, methodology, limitations)
  3.  Document Information & Ingestion Summary
  4.  Processing & Extraction Summary
  5.  Software Components (SWCs) Identified
  6.  Interfaces Identified
  7.  Ports (P-Port / R-Port) Catalogue
  8.  Signals Identified
  9.  Component Dependencies & Connectivity
  10. Architecture Findings (AI observations from Q&A history)
  11. Inconsistency Findings (rule-based checker results)
  12. Q&A Session Log (questions asked, answers given, sources cited)
  13. Source Evidence Index (page-to-artifact traceability)
  14. Review Status & Sign-off

Each section clearly marks whether its content is:
  [EXTRACTED]  — direct text lifted from the document (source evidence)
  [INFERRED]   — AI/rule-based pattern analysis (requires engineer verification)
  [RULE-BASED] — deterministic rule fired on extracted data (most reliable)
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from backend.database.sqlite_db import (
    get_document,
    get_entities,
    get_inconsistencies,
    get_query_history,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_TOOL_VERSION = "AutoHLD v0.1  |  Regex + Heuristic Extractor  |  ChromaDB + Ollama RAG"

_DISCLAIMER_SHORT = (
    "This is an AI-assisted engineering analysis report — NOT a formal AUTOSAR "
    "compliance validation or architecture approval document. All findings and "
    "extracted entities require human engineering review before any design decision "
    "is made."
)

_DISCLAIMER_FULL = (
    "ENGINEERING ANALYSIS NOTICE\n"
    "============================\n\n"
    "This report was generated automatically by AutoHLD, an AI-assisted AUTOSAR "
    "High-Level Design analysis tool, using the following automated methods:\n\n"
    "  • DOCUMENT EXTRACTION:  Text, tables, and structural elements are extracted "
    "from the uploaded PDF using the pdfplumber library.  Page numbers are preserved "
    "throughout.  Extraction quality depends on the PDF encoding and layout.\n\n"
    "  • ENTITY RECOGNITION:   Software Components, Interfaces, Ports, and Signals "
    "are identified using regular-expression pattern matching and AUTOSAR naming-"
    "convention heuristics.  Results are tagged with a confidence level (high / "
    "medium / low / uncertain) that reflects how strongly the evidence supports the "
    "classification.  Entities tagged 'uncertain' or 'low' require manual inspection.\n\n"
    "  • VECTOR RETRIEVAL:     Questions are answered using Retrieval-Augmented "
    "Generation (RAG): the query is embedded, the nearest document chunks are "
    "retrieved from ChromaDB, and the retrieved text is forwarded to an Ollama LLM "
    "(qwen2.5:1.5b by default).  The LLM is instructed to answer only from the "
    "supplied context and to state when information is not found.\n\n"
    "  • CONSISTENCY RULES:    Five deterministic, document-level rules check for "
    "structural problems such as undefined interfaces, orphaned ports, and conflicting "
    "descriptions.  Rule results are labelled REVIEW, WARNING, or INFO and must be "
    "reviewed by a qualified automotive systems engineer.\n\n"
    "WHAT THIS REPORT IS NOT:\n"
    "  ✗  Not a formal AUTOSAR compliance audit\n"
    "  ✗  Not an architecture approval or sign-off\n"
    "  ✗  Not a substitute for tool-supported AUTOSAR toolchain validation\n"
    "  ✗  Not a guarantee of completeness — the extractor may miss entities\n\n"
    "WHAT THIS REPORT IS:\n"
    "  ✓  An AI-assisted preliminary analysis to accelerate initial review\n"
    "  ✓  A structured index of architectural entities found in the document\n"
    "  ✓  A rule-based consistency pre-check to highlight potential issues\n"
    "  ✓  A grounded Q&A audit trail for traceability\n\n"
    "Human engineering review and explicit sign-off is required before acting on "
    "any finding in this report."
)


# ── Core data aggregation ─────────────────────────────────────────────────────

def generate_report_data(doc_id: str, include_qa: bool = True) -> dict[str, Any]:
    """
    Aggregate all available data for doc_id into a single structured payload
    suitable for JSON serialisation or Markdown rendering.

    Parameters
    ----------
    doc_id    : Document identifier.
    include_qa: If True, include Q&A session log in the report.
    """
    doc = get_document(doc_id)
    if doc is None:
        raise ValueError(f"Document '{doc_id}' not found.")

    entities       = get_entities(doc_id)
    inconsistencies = get_inconsistencies(doc_id)
    queries        = get_query_history(doc_id) if include_qa else []

    # ── Entity groups ──────────────────────────────────────────────────────
    components = [e for e in entities if e["entity_type"] == "component"]
    interfaces = [e for e in entities if e["entity_type"] == "interface"]
    ports      = [e for e in entities if e["entity_type"] == "port"]
    signals    = [e for e in entities if e["entity_type"] == "signal"]
    runnables  = [e for e in entities if e["entity_type"] == "runnable"]

    # ── Confidence breakdown ───────────────────────────────────────────────
    def _conf_counts(items: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in items:
            c = e.get("details", {}).get("confidence", "medium")
            counts[c] = counts.get(c, 0) + 1
        return counts

    # ── Inferred dependency graph ──────────────────────────────────────────
    # A dependency exists where a P-Port and R-Port share a base interface name.
    p_ports = [p for p in ports if "prov" in p["name"].lower() or "send" in p["name"].lower()
               or (p.get("details", {}).get("subtype") or "").lower().startswith("p")]
    r_ports = [p for p in ports if "req" in p["name"].lower() or "recv" in p["name"].lower()
               or (p.get("details", {}).get("subtype") or "").lower().startswith("r")]

    def _base_name(name: str) -> str:
        """Strip common suffixes to find a likely interface base."""
        return re.sub(r'_(Prov|Req|Send|Recv|In|Out|Port)$', '', name, flags=re.IGNORECASE)

    dependency_links: list[dict] = []
    for r in r_ports:
        r_base = _base_name(r["name"])
        for p in p_ports:
            p_base = _base_name(p["name"])
            if r_base and p_base and (r_base.lower() == p_base.lower()):
                dependency_links.append({
                    "provider_port":   p["name"],
                    "require_port":    r["name"],
                    "inferred_iface":  f"{p_base}_If",
                    "provider_page":   p.get("page_ref"),
                    "require_page":    r.get("page_ref"),
                    "analysis_type":   "INFERRED",
                    "confidence":      "medium",
                })

    # ── Architecture findings from Q&A ────────────────────────────────────
    # Summarise notable Q&A exchanges as "architecture findings"
    arch_findings: list[dict] = []
    for q in queries:
        answer = q.get("answer", "")
        sources = q.get("sources", [])
        if answer and "not found" not in answer.lower():
            arch_findings.append({
                "question":      q["question"],
                "answer_excerpt": answer[:600] + ("…" if len(answer) > 600 else ""),
                "sources":       sources,
                "model":         q.get("model_used", "—"),
                "created_at":    q.get("created_at", "—"),
                "analysis_type": "AI-GENERATED",
            })

    # ── Severity breakdown for inconsistencies ────────────────────────────
    sev_counts: dict[str, int] = {"warning": 0, "review": 0, "info": 0}
    for inc in inconsistencies:
        sev = inc.get("severity", "info")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    # ── Page traceability index ───────────────────────────────────────────
    page_index: dict[int, dict[str, list]] = {}
    for p_num in range(1, (doc.page_count or 0) + 1):
        page_index[p_num] = {"entities": [], "inconsistencies": []}

    for e in entities:
        pref = e.get("page_ref") or 0
        if pref in page_index:
            page_index[pref]["entities"].append({
                "name": e["name"],
                "type": e["entity_type"],
                "confidence": e.get("details", {}).get("confidence", "medium"),
            })

    for inc in inconsistencies:
        for pg in inc.get("pages", []):
            if pg in page_index:
                page_index[pg]["inconsistencies"].append(inc.get("description", ""))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── Review status ─────────────────────────────────────────────────────
    review_status = _compute_review_status(entities, inconsistencies)

    return {
        # Identification
        "doc_id":        doc_id,
        "filename":      doc.filename,
        "generated_at":  generated_at,
        "tool_version":  _TOOL_VERSION,

        # Document metadata
        "document_metadata": {
            "status":      doc.status,
            "page_count":  doc.page_count,
            "chunk_count": doc.chunk_count,
            "upload_time": doc.upload_time.isoformat() if doc.upload_time else "—",
        },

        # Processing summary
        "processing_summary": {
            "extraction_performed":    len(entities) > 0,
            "consistency_checked":     len(inconsistencies) > 0,
            "qa_sessions":             len(queries),
            "total_entities_found":    len(entities),
            "entities_by_type": {
                "components": len(components),
                "interfaces": len(interfaces),
                "ports":      len(ports),
                "signals":    len(signals),
                "runnables":  len(runnables),
            },
            "confidence_distribution": {
                "components": _conf_counts(components),
                "interfaces": _conf_counts(interfaces),
                "ports":      _conf_counts(ports),
            },
        },

        # Architectural entities
        "components":  components,
        "interfaces":  interfaces,
        "ports":       ports,
        "signals":     signals,
        "runnables":   runnables,

        # Dependencies
        "dependency_links":     dependency_links,
        "dependency_count":     len(dependency_links),

        # Architecture findings (from Q&A)
        "architecture_findings": arch_findings,

        # Consistency check results
        "inconsistencies":          inconsistencies,
        "inconsistency_summary":    sev_counts,
        "inconsistency_count":      len(inconsistencies),

        # Q&A log
        "include_qa":  include_qa,
        "query_log":   queries,
        "query_count": len(queries),

        # Source traceability
        "page_traceability": page_index,

        # Review status
        "review_status": review_status,

        # Disclaimers
        "disclaimer_short": _DISCLAIMER_SHORT,
        "disclaimer_full":  _DISCLAIMER_FULL,
    }


def _compute_review_status(entities: list, inconsistencies: list) -> dict:
    """Determine an overall review readiness status from available data."""
    has_entities = len(entities) > 0
    has_inconsistencies = len(inconsistencies) > 0
    warnings = sum(1 for i in inconsistencies if i.get("severity") == "warning")
    reviews  = sum(1 for i in inconsistencies if i.get("severity") == "review")

    if warnings > 0:
        overall = "REQUIRES REVIEW — Potential architectural warnings detected"
        color   = "warning"
    elif reviews > 0:
        overall = "REVIEW RECOMMENDED — Items flagged for engineer disposition"
        color   = "review"
    elif has_inconsistencies:
        overall = "INFORMATIONAL FINDINGS — Low-severity observations only"
        color   = "info"
    elif has_entities:
        overall = "EXTRACTION COMPLETE — No consistency issues detected"
        color   = "success"
    else:
        overall = "PENDING — Extraction and consistency check not yet performed"
        color   = "pending"

    return {
        "overall":        overall,
        "color":          color,
        "warnings":       warnings,
        "review_items":   reviews,
        "has_entities":   has_entities,
        "has_consistency": has_inconsistencies,
    }


# ── Markdown Report Generator ─────────────────────────────────────────────────

def generate_markdown_report(doc_id: str, include_qa: bool = True) -> str:
    """
    Render the full engineering analysis report as clean Markdown.

    The Markdown clearly labels every content block as either:
      [EXTRACTED]   — verbatim source text from the document
      [INFERRED]    — AI/pattern analysis result
      [RULE-BASED]  — deterministic rule fired on structured data
      [AI RESPONSE] — LLM-generated answer to an engineering question
    """
    data    = generate_report_data(doc_id, include_qa=include_qa)
    dm      = data["document_metadata"]
    ps      = data["processing_summary"]
    inc_sum = data["inconsistency_summary"]
    rs      = data["review_status"]

    lines: list[str] = []

    # ──────────────────────────────────────────────────────────────────────
    # COVER
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "# AutoHLD — AUTOSAR Architecture Engineering Analysis Report",
        "",
        "---",
        "",
        f"> **⚠ ENGINEERING NOTICE:** {data['disclaimer_short']}",
        "",
        "---",
        "",
        "## Cover & Document Identification",
        "",
        f"| Field | Value |",
        f"| :--- | :--- |",
        f"| Document File | `{data['filename']}` |",
        f"| Document ID | `{data['doc_id']}` |",
        f"| Report Generated | {data['generated_at']} |",
        f"| Analysis Tool | {data['tool_version']} |",
        f"| Ingestion Status | **{dm['status'].upper()}** |",
        f"| Document Pages Analyzed | {dm['page_count']} |",
        f"| Semantic Chunks Indexed | {dm['chunk_count']} |",
        f"| Ingestion Timestamp | {dm['upload_time']} |",
        "",
        f"**Overall Review Status:** `{rs['overall']}`",
        "",
        "---",
        "",
    ]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 1 — ENGINEERING NOTICE & METHODOLOGY
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 1 — Engineering Notice & Methodology",
        "",
        "```",
        data["disclaimer_full"],
        "```",
        "",
        "---",
        "",
    ]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 2 — DOCUMENT INFORMATION
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 2 — Document Information",
        "",
        f"The following metadata describes the AUTOSAR HLD document as ingested by AutoHLD.",
        "",
        f"| Property | Value |",
        f"| :--- | :--- |",
        f"| Filename | `{data['filename']}` |",
        f"| Total Pages Processed | {dm['page_count']} |",
        f"| Vector Chunk Count | {dm['chunk_count']} |",
        f"| Vector Embedding Model | all-MiniLM-L6-v2 (384-dimensional, Cosine similarity) |",
        f"| LLM Reasoning Engine | Ollama — qwen2.5:1.5b (local inference, no cloud) |",
        f"| Vector Store | ChromaDB (local persistent collection) |",
        f"| Entity Extraction Method | Regex pattern matching + AUTOSAR naming-convention heuristics |",
        f"| Consistency Rule Engine | 5 deterministic document-level rules |",
        "",
        "---",
        "",
    ]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 3 — PROCESSING SUMMARY
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 3 — Processing & Extraction Summary",
        "",
        "| Analysis Stage | Status | Count |",
        "| :--- | :--- | :--- |",
        f"| PDF Ingestion | {'✓ Complete' if dm['status'] == 'ready' else '⚠ ' + dm['status']} | {dm['page_count']} pages |",
        f"| Vector Indexing | {'✓ Complete' if dm['chunk_count'] > 0 else '—'} | {dm['chunk_count']} chunks |",
        f"| Entity Extraction | {'✓ Performed' if ps['extraction_performed'] else '⚠ Not yet run'} | {ps['total_entities_found']} entities total |",
        f"| Consistency Check | {'✓ Performed' if ps['consistency_checked'] else '⚠ Not yet run'} | {data['inconsistency_count']} findings |",
        f"| Q&A Sessions | {'✓ ' + str(ps['qa_sessions']) + ' queries' if ps['qa_sessions'] else '— None recorded'} | {ps['qa_sessions']} |",
        "",
        "### Entity Extraction Breakdown",
        "",
        "| Entity Type | Count | High Confidence | Medium | Low / Uncertain |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for etype in ("components", "interfaces", "ports", "signals"):
        n = ps["entities_by_type"].get(etype, 0)
        cd = ps["confidence_distribution"].get(etype, {})
        h = cd.get("high", 0)
        m = cd.get("medium", 0)
        l = cd.get("low", 0) + cd.get("uncertain", 0)
        label = etype.title()
        lines.append(f"| {label} | {n} | {h} | {m} | {l} |")

    lines += [
        "",
        "_Note: Confidence levels reflect pattern-match strength, not semantic correctness._",
        "_All entities with confidence < high should be manually verified._",
        "",
        "---",
        "",
    ]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 4 — SOFTWARE COMPONENTS (SWCs)
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 4 — Software Components (SWCs) Identified",
        "",
        "> **Analysis Type: [INFERRED]** — Components are identified by AUTOSAR naming",
        "> conventions and explicit SWC keywords. Verify against the authoritative arxml.",
        "",
    ]

    if not data["components"]:
        lines += [
            "_No software components identified. Run entity extraction via the Components & Interfaces tab._",
            "",
        ]
    else:
        lines += [
            f"**{len(data['components'])} software component(s) identified.**",
            "",
            "| # | Component Name | Subtype | Source Page | Confidence | Evidence Excerpt |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for i, c in enumerate(data["components"], 1):
            det = c.get("details", {})
            excerpt = _truncate(det.get("source_text", "—"), 90)
            lines.append(
                f"| {i} | `{c['name']}` | {det.get('subtype', 'SWC')} "
                f"| p.{c.get('page_ref', '—')} | **{det.get('confidence', 'medium')}** "
                f"| {_md_escape(excerpt)} |"
            )
        lines.append("")

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 5 — INTERFACES
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 5 — Interfaces Identified",
        "",
        "> **Analysis Type: [INFERRED]** — Interfaces are identified by naming suffixes",
        "> (`_If`, `_Interface`) and explicit AUTOSAR keywords. Cross-reference with arxml.",
        "",
    ]

    if not data["interfaces"]:
        lines += ["_No interfaces identified._", ""]
    else:
        lines += [
            f"**{len(data['interfaces'])} interface(s) identified.**",
            "",
            "| # | Interface Name | Type | Source Page | Confidence | Evidence Excerpt |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for i, iface in enumerate(data["interfaces"], 1):
            det = iface.get("details", {})
            excerpt = _truncate(det.get("source_text", "—"), 90)
            lines.append(
                f"| {i} | `{iface['name']}` | {det.get('subtype', 'SenderReceiver')} "
                f"| p.{iface.get('page_ref', '—')} | **{det.get('confidence', 'medium')}** "
                f"| {_md_escape(excerpt)} |"
            )
        lines.append("")

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 6 — PORTS (P / R)
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 6 — Ports (P-Port / R-Port) Catalogue",
        "",
        "> **Analysis Type: [INFERRED]** — Ports identified via explicit direction keywords",
        "> (P-Port / R-Port) and naming suffix heuristics (`_Prov`, `_Req`).",
        "",
    ]

    p_ports_list = [p for p in data["ports"] if "prov" in p["name"].lower() or "send" in p["name"].lower()]
    r_ports_list = [p for p in data["ports"] if "req" in p["name"].lower() or "recv" in p["name"].lower()]
    other_ports  = [p for p in data["ports"] if p not in p_ports_list and p not in r_ports_list]

    if not data["ports"]:
        lines += ["_No ports identified._", ""]
    else:
        if p_ports_list:
            lines += [
                f"### P-Ports (Provide Ports) — {len(p_ports_list)} identified",
                "",
                "| Port Name | Associated Interface | Source Page | Confidence |",
                "| :--- | :--- | :--- | :--- |",
            ]
            for p in p_ports_list:
                det  = p.get("details", {})
                iface = det.get("associated_interface") or "—"
                lines.append(
                    f"| `{p['name']}` | `{iface}` | p.{p.get('page_ref', '—')} | {det.get('confidence', 'medium')} |"
                )
            lines.append("")

        if r_ports_list:
            lines += [
                f"### R-Ports (Require Ports) — {len(r_ports_list)} identified",
                "",
                "| Port Name | Associated Interface | Source Page | Confidence |",
                "| :--- | :--- | :--- | :--- |",
            ]
            for p in r_ports_list:
                det  = p.get("details", {})
                iface = det.get("associated_interface") or "—"
                lines.append(
                    f"| `{p['name']}` | `{iface}` | p.{p.get('page_ref', '—')} | {det.get('confidence', 'medium')} |"
                )
            lines.append("")

        if other_ports:
            lines += [
                f"### Other Ports — {len(other_ports)} identified",
                "",
                "| Port Name | Subtype | Source Page | Confidence |",
                "| :--- | :--- | :--- | :--- |",
            ]
            for p in other_ports:
                det = p.get("details", {})
                lines.append(
                    f"| `{p['name']}` | {det.get('subtype', 'Port')} | p.{p.get('page_ref', '—')} | {det.get('confidence', 'medium')} |"
                )
            lines.append("")

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 7 — SIGNALS
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 7 — Signals Identified",
        "",
        "> **Analysis Type: [INFERRED]** — Signals identified by `_Sig`, `_Val` suffixes",
        "> and explicit signal keyword patterns in the document text.",
        "",
    ]

    if not data["signals"]:
        lines += ["_No signals identified._", ""]
    else:
        lines += [
            f"**{len(data['signals'])} signal(s) identified.**",
            "",
            "| # | Signal Name | Type | Source Page | Confidence |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for i, sig in enumerate(data["signals"], 1):
            det = sig.get("details", {})
            lines.append(
                f"| {i} | `{sig['name']}` | {det.get('subtype', 'Signal')} "
                f"| p.{sig.get('page_ref', '—')} | {det.get('confidence', 'medium')} |"
            )
        lines.append("")

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 8 — DEPENDENCIES
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 8 — Component Dependencies & Connectivity",
        "",
        "> **Analysis Type: [INFERRED]** — Dependencies are inferred by matching",
        "> P-Port and R-Port base names (e.g., `BattSOC_Prov` ↔ `BattSOC_Req`).",
        "> Actual connectivity requires arxml / RTE configuration verification.",
        "",
    ]

    if not data["dependency_links"]:
        lines += [
            "_No port-level dependencies inferred. This may indicate:_",
            "_- Ports follow non-standard naming conventions_",
            "_- Extraction has not been run_",
            "_- The document describes a single SWC boundary_",
            "",
        ]
    else:
        lines += [
            f"**{len(data['dependency_links'])} inferred port-level dependency link(s).**",
            "",
            "| Provider Port | Require Port | Inferred Interface | P-Port Page | R-Port Page | Confidence |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for d in data["dependency_links"]:
            lines.append(
                f"| `{d['provider_port']}` | `{d['require_port']}` | `{d['inferred_iface']}` "
                f"| p.{d['provider_page'] or '—'} | p.{d['require_page'] or '—'} | {d['confidence']} |"
            )
        lines.append("")
        lines.append(
            "_These links are inferred from port naming conventions only. "
            "They may not reflect actual RTE connections in the implemented system._"
        )
        lines.append("")

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 9 — ARCHITECTURE FINDINGS (Q&A-derived)
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 9 — Architecture Findings from Grounded Q&A",
        "",
        "> **Analysis Type: [AI-GENERATED]** — These findings were produced by the LLM",
        "> in response to engineering questions. The LLM was grounded on retrieved",
        "> document chunks and instructed not to fabricate information.",
        "> **AI responses require engineer verification against the source document.**",
        "",
    ]

    if not data["architecture_findings"]:
        lines += [
            "_No Q&A architecture findings recorded._",
            "_Use the 'Ask the HLD' tab to ask questions about the document architecture._",
            "",
        ]
    else:
        for i, finding in enumerate(data["architecture_findings"], 1):
            lines += [
                f"### Finding {i}: {_truncate(finding['question'], 100)}",
                "",
                f"**Question:** {finding['question']}",
                "",
                f"**AI Response** _(from {finding['model']})_:",
                "",
                f"> {finding['answer_excerpt'].replace(chr(10), chr(10) + '> ')}",
                "",
            ]
            sources = finding.get("sources", [])
            if sources:
                lines.append("**Source Evidence Retrieved:**")
                lines.append("")
                lines.append("| Source Page | Evidence Excerpt [EXTRACTED] |")
                lines.append("| :--- | :--- |")
                for s in sources[:5]:
                    pg = s.get("page_num") or s.get("page") or "—"
                    txt = _truncate(s.get("text") or s.get("excerpt") or "—", 120)
                    lines.append(f"| p.{pg} | {_md_escape(txt)} |")
                lines.append("")
            lines.append("")

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 10 — INCONSISTENCY FINDINGS
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 10 — Architecture Inconsistency Findings",
        "",
        "> **Analysis Type: [RULE-BASED]** — The following findings were produced by",
        "> five deterministic consistency rules applied to the extracted entity data.",
        "> Rules fire on structural conditions only — they do NOT perform semantic",
        "> reasoning. Each finding must be reviewed by a qualified engineer.",
        "",
        f"### Summary",
        "",
        f"| Severity | Count | Meaning |",
        f"| :--- | :--- | :--- |",
        f"| **WARNING** | {inc_sum.get('warning', 0)} | Strong structural evidence of a potential issue — prioritise review |",
        f"| **REVIEW** | {inc_sum.get('review', 0)} | Structural observation requiring engineer disposition |",
        f"| **INFO** | {inc_sum.get('info', 0)} | Low-priority observation for completeness |",
        f"| **Total** | {data['inconsistency_count']} | All findings require review before sign-off |",
        "",
    ]

    if not data["inconsistencies"]:
        lines += [
            "✓ _No document-level inconsistencies detected by the automated rules._",
            "_This does not mean the document is error-free — manual review is always required._",
            "",
        ]
    else:
        for i, inc in enumerate(data["inconsistencies"], 1):
            sev   = inc.get("severity", "info").upper()
            cat   = inc.get("category", "general")
            desc  = inc.get("description", "")
            evid  = inc.get("evidence", "—") or "—"
            reason = inc.get("reason", "—") or "—"
            pages = ", ".join(f"p.{p}" for p in inc.get("pages", [])) or "—"

            lines += [
                f"### Finding {i} — {sev}: {_truncate(desc, 80)}",
                "",
                f"| Attribute | Detail |",
                f"| :--- | :--- |",
                f"| Severity | **{sev}** |",
                f"| Rule Category | `{cat}` |",
                f"| Source Pages | {pages} |",
                f"| Disposition | `[ ] Reviewed    [ ] False Positive    [ ] Action Required` |",
                "",
                f"**Description:** {desc}",
                "",
                f"**Evidence [EXTRACTED from document]:**",
                "",
                f"> {evid}",
                "",
                f"**Why This Was Flagged [RULE-BASED]:** {reason}",
                "",
            ]

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 11 — Q&A SESSION LOG
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 11 — Q&A Session Log & Source References",
        "",
        "> **Analysis Type: [AI-GENERATED + EXTRACTED]** — Each answer was produced",
        "> by the LLM from retrieved document chunks. Source pages are [EXTRACTED].",
        "> Answers are [AI-GENERATED] and require verification.",
        "",
    ]

    if not data["query_log"]:
        lines += [
            "_No Q&A queries recorded for this document session._",
            "",
        ]
    else:
        for i, q in enumerate(data["query_log"], 1):
            lines += [
                f"### Query {i}",
                "",
                f"**Question:** {q['question']}",
                "",
                f"**Engine:** `{q.get('model_used', '—')}` | **Timestamp:** {q.get('created_at', '—')}",
                "",
                f"**Answer [AI-GENERATED]:**",
                "",
            ]
            answer = q.get("answer", "—")
            for para in answer.split("\n"):
                lines.append(f"> {para}")
            lines.append("")

            sources = q.get("sources", [])
            if sources:
                lines += [
                    "**Source Evidence [EXTRACTED from document]:**",
                    "",
                    "| Page | Section | Excerpt |",
                    "| :--- | :--- | :--- |",
                ]
                for s in sources:
                    pg   = s.get("page_num") or s.get("page") or "—"
                    sec  = s.get("section") or "—"
                    txt  = _truncate(s.get("text") or s.get("excerpt") or "—", 140)
                    lines.append(f"| p.{pg} | {_md_escape(sec)} | {_md_escape(txt)} |")
                lines.append("")
            else:
                lines += ["_No source citations recorded for this query._", ""]

    lines += ["---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 12 — PAGE-TO-ARTIFACT TRACEABILITY INDEX
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 12 — Source Evidence & Page Traceability Index",
        "",
        "> **Analysis Type: [EXTRACTED]** — The following index maps each document page",
        "> to the architectural entities detected on that page and any consistency",
        "> findings that reference it. This section is the primary audit trail.",
        "",
        "| Page | Entities Detected [EXTRACTED] | Confidence Summary | Consistency Observations [RULE-BASED] |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for p_num, p_info in data["page_traceability"].items():
        ents = p_info.get("entities", [])
        incs = p_info.get("inconsistencies", [])

        if not ents and not incs:
            continue

        ent_str = ", ".join(
            f"`{e['name']}`" for e in ents[:6]
        ) + (f" _+{len(ents)-6} more_" if len(ents) > 6 else "") if ents else "—"

        conf_high = sum(1 for e in ents if e.get("confidence") == "high")
        conf_low  = sum(1 for e in ents if e.get("confidence") in ("low", "uncertain"))
        conf_str  = f"{len(ents)} entities ({conf_high} high / {conf_low} low-conf)" if ents else "—"

        inc_str = "; ".join(_truncate(inc, 60) for inc in incs[:2]) if incs else "—"

        lines.append(f"| **p.{p_num}** | {ent_str} | {conf_str} | {inc_str} |")

    lines += ["", "---", ""]

    # ──────────────────────────────────────────────────────────────────────
    # SECTION 13 — REVIEW STATUS & SIGN-OFF
    # ──────────────────────────────────────────────────────────────────────
    lines += [
        "## Section 13 — Review Status & Engineering Sign-off",
        "",
        "### Automated Analysis Status",
        "",
        f"| Stage | Completed | Result |",
        f"| :--- | :--- | :--- |",
        f"| Document Ingestion | {'✓' if dm['status'] == 'ready' else '✗'} | {dm['status'].upper()} |",
        f"| Entity Extraction | {'✓' if ps['extraction_performed'] else '○ Pending'} | {ps['total_entities_found']} entities found |",
        f"| Consistency Check | {'✓' if ps['consistency_checked'] else '○ Pending'} | {data['inconsistency_count']} findings |",
        f"| Q&A Review | {'✓' if ps['qa_sessions'] > 0 else '○ No queries'} | {ps['qa_sessions']} queries recorded |",
        f"| **Overall Status** | | **{rs['overall']}** |",
        "",
        "### Human Engineering Sign-off",
        "",
        "_Complete this section after reviewing all findings above._",
        "",
        "| Role | Engineer Name | Date | Disposition |",
        "| :--- | :--- | :--- | :--- |",
        "| Lead Systems Architect | ___________________________ | ____________ | `[ ] Approved  [ ] Revision Required  [ ] Rejected` |",
        "| Software Safety Engineer | ___________________________ | ____________ | `[ ] Approved  [ ] Revision Required  [ ] Rejected` |",
        "| AUTOSAR Integration Engineer | ___________________________ | ____________ | `[ ] Approved  [ ] Revision Required  [ ] Rejected` |",
        "| Review Coordinator | ___________________________ | ____________ | `[ ] Released  [ ] Withheld` |",
        "",
        "**Review Notes:**",
        "",
        "_______________________________________________________________________",
        "",
        "_______________________________________________________________________",
        "",
        "---",
        "",
        f"_Report generated: {data['generated_at']}_  ",
        f"_Tool: {data['tool_version']}_  ",
        "",
        f"> **{data['disclaimer_short']}**",
    ]

    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters."""
    if not text:
        return "—"
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def _md_escape(text: str) -> str:
    """Escape characters that break Markdown table cells."""
    if not text:
        return "—"
    return text.replace("|", "&#124;").replace("\n", " ").replace("\r", "")
