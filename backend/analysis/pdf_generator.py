"""
pdf_generator.py — Multi-page PDF report generator for AutoHLD.

Converts the structured report_data dict (produced by report_builder.generate_report_data)
into a properly-paginated PDF using ReportLab.

All 13 report sections are included with:
  - Cover page with metadata grid
  - Section headings with source-type labels
  - Styled tables for entities, inconsistencies, Q&A, etc.
  - Page numbers and running header/footer on every page
  - Page-break control so sections don't split awkwardly
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    FrameBreak,
    HRFlowable,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Frame,
)
from reportlab.platypus.flowables import Flowable

# ── Colour palette ─────────────────────────────────────────────────────────────
_C_NAVY    = colors.HexColor("#0f172a")
_C_BLUE    = colors.HexColor("#3b82f6")
_C_ACCENT  = colors.HexColor("#6366f1")
_C_GREEN   = colors.HexColor("#22c55e")
_C_YELLOW  = colors.HexColor("#f59e0b")
_C_RED     = colors.HexColor("#ef4444")
_C_MUTED   = colors.HexColor("#64748b")
_C_LIGHT   = colors.HexColor("#f8fafc")
_C_BORDER  = colors.HexColor("#e2e8f0")
_C_ROW_ALT = colors.HexColor("#f1f5f9")
_C_WHITE   = colors.white
_C_BLACK   = colors.HexColor("#1e293b")

W, H = A4  # 595.27 x 841.89 pt

MARGIN_LEFT   = 1.8 * cm
MARGIN_RIGHT  = 1.8 * cm
MARGIN_TOP    = 2.2 * cm
MARGIN_BOTTOM = 2.2 * cm

BODY_W = W - MARGIN_LEFT - MARGIN_RIGHT


# ── Style sheet ───────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()

    def s(name, **kw) -> ParagraphStyle:
        parent = kw.pop("parent", "Normal")
        style  = ParagraphStyle(name, parent=base[parent], **kw)
        return style

    return {
        "title": s("RTitle",
            fontSize=22, leading=28, textColor=_C_NAVY,
            fontName="Helvetica-Bold", spaceAfter=6, alignment=TA_CENTER),

        "subtitle": s("RSubtitle",
            fontSize=11, leading=15, textColor=_C_MUTED,
            fontName="Helvetica", spaceAfter=4, alignment=TA_CENTER),

        "h1": s("RH1",
            fontSize=14, leading=18, textColor=_C_NAVY,
            fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6,
            borderPad=4, backColor=_C_LIGHT),

        "h2": s("RH2",
            fontSize=11, leading=15, textColor=_C_ACCENT,
            fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4),

        "h3": s("RH3",
            fontSize=10, leading=13, textColor=_C_NAVY,
            fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2),

        "body": s("RBody",
            fontSize=9, leading=13, textColor=_C_BLACK,
            fontName="Helvetica", spaceAfter=4),

        "mono": s("RMono",
            fontSize=8, leading=11, textColor=_C_BLACK,
            fontName="Courier", spaceAfter=4),

        "caption": s("RCaption",
            fontSize=8, leading=11, textColor=_C_MUTED,
            fontName="Helvetica-Oblique", spaceAfter=4),

        "notice": s("RNotice",
            fontSize=8.5, leading=12, textColor=colors.HexColor("#92400e"),
            fontName="Helvetica", spaceAfter=6),

        "th": s("RTh",
            fontSize=8, leading=10, textColor=_C_WHITE,
            fontName="Helvetica-Bold"),

        "td": s("RTd",
            fontSize=8, leading=10, textColor=_C_BLACK,
            fontName="Helvetica"),

        "td_mono": s("RTdMono",
            fontSize=7.5, leading=10, textColor=_C_BLACK,
            fontName="Courier"),

        "td_muted": s("RTdMuted",
            fontSize=8, leading=10, textColor=_C_MUTED,
            fontName="Helvetica-Oblique"),
    }


# ── Table style builders ──────────────────────────────────────────────────────

def _tbl_style(col_count: int, alt_rows: bool = True) -> TableStyle:
    cmds = [
        ("BACKGROUND",  (0, 0), (-1, 0), _C_NAVY),
        ("TEXTCOLOR",   (0, 0), (-1, 0), _C_WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 8),
        ("TEXTCOLOR",   (0, 1), (-1, -1), _C_BLACK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_C_WHITE, _C_ROW_ALT] if alt_rows else [_C_WHITE]),
        ("GRID",        (0, 0), (-1, -1), 0.4, _C_BORDER),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("WORDWRAP",    (0, 0), (-1, -1), "CJK"),
    ]
    return TableStyle(cmds)


# ── Page template with header/footer ─────────────────────────────────────────

class _PageDecorator:
    def __init__(self, doc_title: str, generated_at: str):
        self.doc_title    = doc_title
        self.generated_at = generated_at

    def __call__(self, canvas, doc):
        canvas.saveState()

        # Header bar
        canvas.setFillColor(_C_NAVY)
        canvas.rect(MARGIN_LEFT, H - MARGIN_TOP + 4*mm,
                    BODY_W, 6*mm, fill=1, stroke=0)
        canvas.setFillColor(_C_WHITE)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(MARGIN_LEFT + 4, H - MARGIN_TOP + 4*mm + 4,
                          "AutoHLD — AUTOSAR Architecture Engineering Analysis")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(W - MARGIN_RIGHT - 2,
                               H - MARGIN_TOP + 4*mm + 4,
                               f"CONFIDENTIAL DRAFT")

        # Footer bar
        canvas.setFillColor(_C_LIGHT)
        canvas.rect(MARGIN_LEFT, MARGIN_BOTTOM - 8*mm,
                    BODY_W, 6*mm, fill=1, stroke=0)
        canvas.setStrokeColor(_C_BORDER)
        canvas.line(MARGIN_LEFT, MARGIN_BOTTOM - 2*mm,
                    W - MARGIN_RIGHT, MARGIN_BOTTOM - 2*mm)
        canvas.setFillColor(_C_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN_LEFT + 2, MARGIN_BOTTOM - 6*mm,
                          f"Generated: {self.generated_at}")
        canvas.drawCentredString(W / 2, MARGIN_BOTTOM - 6*mm,
                                 f"Page {doc.page}")
        canvas.drawRightString(W - MARGIN_RIGHT - 2, MARGIN_BOTTOM - 6*mm,
                               "AI-ASSISTED ANALYSIS — REQUIRES ENGINEER REVIEW")

        canvas.restoreState()


# ── Helper paragraph / table builders ────────────────────────────────────────

def _p(text: str, style) -> Paragraph:
    """Safe paragraph — escapes < > & for ReportLab XML parser."""
    safe = str(text or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def _trunc(text, n: int) -> str:
    t = str(text or "—").replace("\n", " ").strip()
    return t[:n] + "…" if len(t) > n else t


def _section_header(title: str, badge: str | None, st: dict) -> list:
    badge_str = f"  [{badge}]" if badge else ""
    return [
        HRFlowable(width=BODY_W, thickness=0.5, color=_C_BORDER),
        Spacer(1, 2*mm),
        _p(f"{title}{badge_str}", st["h1"]),
        Spacer(1, 2*mm),
    ]


def _kv_table(rows: list[tuple[str, str]], st: dict, col_w=None) -> Table:
    col_w = col_w or [5.5*cm, BODY_W - 5.5*cm]
    data  = [[_p(k, st["th"]), _p(v, st["td"])] for k, v in rows]
    t     = Table(data, colWidths=col_w, repeatRows=0)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, -1), _C_NAVY),
        ("TEXTCOLOR",    (0, 0), (0, -1), _C_WHITE),
        ("FONTNAME",     (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",     (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID",         (0, 0), (-1, -1), 0.4, _C_BORDER),
        ("ROWBACKGROUNDS",(1, 0), (1, -1), [_C_WHITE, _C_ROW_ALT]),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _conf_color(level: str) -> colors.Color:
    return {
        "high":      _C_GREEN,
        "medium":    _C_BLUE,
        "low":       _C_YELLOW,
        "uncertain": _C_RED,
    }.get(str(level).lower(), _C_MUTED)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_pdf_report(report_data: dict[str, Any]) -> bytes:
    """
    Convert a report_data dict (from generate_report_data) into a PDF binary.

    Returns the raw PDF bytes ready to stream as a file download.
    """
    buf  = io.BytesIO()
    st   = _build_styles()
    rd   = report_data
    dm   = rd.get("document_metadata", {})
    ps   = rd.get("processing_summary", {})
    rs   = rd.get("review_status", {})
    inc_sum = rd.get("inconsistency_summary", {})

    generated_at = rd.get("generated_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    doc_title    = rd.get("filename", "AutoHLD Report")

    decorator = _PageDecorator(doc_title, generated_at)

    body_frame = Frame(
        MARGIN_LEFT, MARGIN_BOTTOM,
        BODY_W, H - MARGIN_TOP - MARGIN_BOTTOM,
        id="body", leftPadding=0, rightPadding=0,
        topPadding=0, bottomPadding=0,
    )
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_LEFT, rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
        title=f"AutoHLD Report — {doc_title}",
        author="AutoHLD",
    )
    template = PageTemplate(id="main", frames=[body_frame], onPage=decorator)
    doc.addPageTemplates([template])

    story: list = []

    # ── COVER PAGE ─────────────────────────────────────────────────────────
    story += [
        Spacer(1, 2*cm),
        _p("AutoHLD", st["title"]),
        _p("AUTOSAR Architecture Engineering Analysis Report", st["subtitle"]),
        Spacer(1, 6*mm),
        HRFlowable(width=BODY_W, thickness=2, color=_C_ACCENT),
        Spacer(1, 4*mm),
    ]

    status_color = {
        "warning": _C_RED, "review": _C_YELLOW, "info": _C_BLUE,
        "success": _C_GREEN, "pending": _C_MUTED,
    }.get(rs.get("color", "pending"), _C_MUTED)

    # Notice banner
    notice_tbl = Table(
        [[_p(f"⚠  ENGINEERING NOTICE: {rd.get('disclaimer_short', '')}", st["notice"])]],
        colWidths=[BODY_W],
    )
    notice_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#fef9c3")),
        ("BOX",        (0,0), (-1,-1), 1, colors.HexColor("#f59e0b")),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
        ("LEFTPADDING", (0,0),(-1,-1), 10),
        ("RIGHTPADDING",(0,0),(-1,-1), 10),
    ]))
    story += [notice_tbl, Spacer(1, 6*mm)]

    # Cover metadata grid
    story.append(_kv_table([
        ("Document File",        doc_title),
        ("Document ID",          rd.get("doc_id", "—")),
        ("Report Generated",     generated_at),
        ("Analysis Tool",        rd.get("tool_version", "—")),
        ("Ingestion Status",     dm.get("status", "—").upper()),
        ("Pages Analysed",       str(dm.get("page_count", "—"))),
        ("Semantic Chunks",      str(dm.get("chunk_count", "—"))),
        ("Ingestion Timestamp",  str(dm.get("upload_time", "—"))),
        ("Overall Review Status", rs.get("overall", "—")),
    ], st))

    story += [Spacer(1, 8*mm), PageBreak()]

    # ── SECTION 1: METHODOLOGY ─────────────────────────────────────────────
    story += _section_header("Section 1 — Engineering Notice & Methodology", None, st)
    disc = rd.get("disclaimer_full", "")
    for para in disc.split("\n\n"):
        story.append(_p(para.strip(), st["body"]))
        story.append(Spacer(1, 2*mm))
    story.append(PageBreak())

    # ── SECTION 2: DOCUMENT INFORMATION ───────────────────────────────────
    story += _section_header("Section 2 — Document Information", None, st)
    story.append(_kv_table([
        ("Filename",             doc_title),
        ("Total Pages",          str(dm.get("page_count", "—"))),
        ("Vector Chunks",        str(dm.get("chunk_count", "—"))),
        ("Embedding Model",      "all-MiniLM-L6-v2 (384-dim, Cosine similarity)"),
        ("LLM Engine",           "Ollama — qwen2.5:1.5b (local inference)"),
        ("Vector Store",         "ChromaDB (local persistent collection)"),
        ("Extraction Method",    "Regex + AUTOSAR naming-convention heuristics"),
        ("Consistency Rules",    "5 deterministic document-level rules"),
    ], st))
    story.append(Spacer(1, 6*mm))

    # ── SECTION 3: PROCESSING SUMMARY ─────────────────────────────────────
    story += _section_header("Section 3 — Processing & Extraction Summary", None, st)

    stage_data = [
        [_p("Stage", st["th"]), _p("Status", st["th"]), _p("Metric", st["th"])],
        [_p("PDF Ingestion", st["td"]),
         _p("✓ Complete" if dm.get("status") == "ready" else f"⚠ {dm.get('status','?')}", st["td"]),
         _p(f"{dm.get('page_count','—')} pages", st["td"])],
        [_p("Vector Indexing", st["td"]),
         _p("✓ Complete" if (dm.get("chunk_count") or 0) > 0 else "—", st["td"]),
         _p(f"{dm.get('chunk_count','—')} chunks", st["td"])],
        [_p("Entity Extraction", st["td"]),
         _p("✓ Performed" if ps.get("extraction_performed") else "⚠ Pending", st["td"]),
         _p(f"{ps.get('total_entities_found', 0)} entities", st["td"])],
        [_p("Consistency Check", st["td"]),
         _p("✓ Performed" if ps.get("consistency_checked") else "⚠ Pending", st["td"]),
         _p(f"{rd.get('inconsistency_count', 0)} findings", st["td"])],
        [_p("Q&A Sessions", st["td"]),
         _p(f"✓ {ps.get('qa_sessions',0)} queries" if ps.get("qa_sessions") else "— None", st["td"]),
         _p(str(ps.get("qa_sessions", 0)), st["td"])],
    ]
    stage_tbl = Table(stage_data, colWidths=[6*cm, 5*cm, BODY_W - 11*cm], repeatRows=1)
    stage_tbl.setStyle(_tbl_style(3))
    story += [stage_tbl, Spacer(1, 5*mm)]

    # Entity breakdown
    story.append(_p("Entity Extraction Breakdown", st["h2"]))
    eb = ps.get("entities_by_type", {})
    cd = ps.get("confidence_distribution", {})
    ent_data = [
        [_p("Entity Type", st["th"]), _p("Count", st["th"]), _p("High Confidence", st["th"]),
         _p("Medium", st["th"]), _p("Low / Uncertain", st["th"])],
    ]
    for etype in ("components", "interfaces", "ports", "signals"):
        n    = eb.get(etype, 0)
        conf = cd.get(etype, {})
        h, m = conf.get("high", 0), conf.get("medium", 0)
        l    = conf.get("low", 0) + conf.get("uncertain", 0)
        ent_data.append([
            _p(etype.title(), st["td"]), _p(str(n), st["td"]),
            _p(str(h), st["td"]), _p(str(m), st["td"]), _p(str(l), st["td"]),
        ])
    ent_tbl = Table(ent_data,
                    colWidths=[4*cm, 2.5*cm, 3.5*cm, 3*cm, BODY_W-13*cm],
                    repeatRows=1)
    ent_tbl.setStyle(_tbl_style(5))
    story += [ent_tbl, Spacer(1, 4*mm),
              _p("Confidence levels reflect pattern-match strength only. All entities with confidence < high must be manually verified.", st["caption"]),
              PageBreak()]

    # ── SECTION 4: COMPONENTS ──────────────────────────────────────────────
    story += _section_header("Section 4 — Software Components (SWCs) Identified", "INFERRED", st)
    components = rd.get("components", [])
    if not components:
        story.append(_p("No software components identified. Run entity extraction.", st["caption"]))
    else:
        story.append(_p(f"{len(components)} software component(s) identified.", st["body"]))
        hdr = [_p("#", st["th"]), _p("Component Name", st["th"]), _p("Subtype", st["th"]),
               _p("Page", st["th"]), _p("Confidence", st["th"]), _p("Evidence Excerpt [EXTRACTED]", st["th"])]
        rows = [hdr]
        for i, c in enumerate(components, 1):
            det = c.get("details", {})
            rows.append([
                _p(str(i), st["td"]),
                _p(c.get("name", "—"), st["td_mono"]),
                _p(det.get("subtype", "SWC"), st["td"]),
                _p(f"p.{c.get('page_ref', '—')}", st["td"]),
                _p(det.get("confidence", "medium"), st["td"]),
                _p(_trunc(det.get("source_text", "—"), 80), st["td_muted"]),
            ])
        col_w = [0.8*cm, 3.5*cm, 2.5*cm, 1.2*cm, 2*cm, BODY_W-10*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(_tbl_style(6))
        story.append(t)
    story += [Spacer(1, 4*mm)]

    # ── SECTION 5: INTERFACES ──────────────────────────────────────────────
    story += _section_header("Section 5 — Interfaces Identified", "INFERRED", st)
    interfaces = rd.get("interfaces", [])
    if not interfaces:
        story.append(_p("No interfaces identified.", st["caption"]))
    else:
        story.append(_p(f"{len(interfaces)} interface(s) identified.", st["body"]))
        hdr = [_p("#", st["th"]), _p("Interface Name", st["th"]), _p("Type", st["th"]),
               _p("Page", st["th"]), _p("Confidence", st["th"]), _p("Evidence Excerpt [EXTRACTED]", st["th"])]
        rows = [hdr]
        for i, iface in enumerate(interfaces, 1):
            det = iface.get("details", {})
            rows.append([
                _p(str(i), st["td"]),
                _p(iface.get("name", "—"), st["td_mono"]),
                _p(det.get("subtype", "SenderReceiver"), st["td"]),
                _p(f"p.{iface.get('page_ref', '—')}", st["td"]),
                _p(det.get("confidence", "medium"), st["td"]),
                _p(_trunc(det.get("source_text", "—"), 80), st["td_muted"]),
            ])
        col_w = [0.8*cm, 3.5*cm, 2.5*cm, 1.2*cm, 2*cm, BODY_W-10*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(_tbl_style(6))
        story.append(t)
    story += [Spacer(1, 4*mm)]

    # ── SECTION 6: PORTS ──────────────────────────────────────────────────
    story += _section_header("Section 6 — Ports (P-Port / R-Port) Catalogue", "INFERRED", st)
    ports = rd.get("ports", [])
    if not ports:
        story.append(_p("No ports identified.", st["caption"]))
    else:
        story.append(_p(f"{len(ports)} port(s) identified.", st["body"]))
        hdr = [_p("#", st["th"]), _p("Port Name", st["th"]), _p("Direction", st["th"]),
               _p("Associated Interface", st["th"]), _p("Page", st["th"]), _p("Confidence", st["th"])]
        rows = [hdr]
        for i, port in enumerate(ports, 1):
            det = port.get("details", {})
            rows.append([
                _p(str(i), st["td"]),
                _p(port.get("name", "—"), st["td_mono"]),
                _p(det.get("subtype", "Port"), st["td"]),
                _p(det.get("associated_interface", "—"), st["td_mono"]),
                _p(f"p.{port.get('page_ref', '—')}", st["td"]),
                _p(det.get("confidence", "medium"), st["td"]),
            ])
        col_w = [0.8*cm, 3.5*cm, 2*cm, 4*cm, 1.2*cm, 2*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(_tbl_style(6))
        story.append(t)
    story += [Spacer(1, 4*mm)]

    # ── SECTION 7: SIGNALS ─────────────────────────────────────────────────
    story += _section_header("Section 7 — Signals Identified", "INFERRED", st)
    signals = rd.get("signals", [])
    if not signals:
        story.append(_p("No signals identified.", st["caption"]))
    else:
        story.append(_p(f"{len(signals)} signal(s) identified.", st["body"]))
        hdr = [_p("#", st["th"]), _p("Signal Name", st["th"]), _p("Type", st["th"]),
               _p("Page", st["th"]), _p("Confidence", st["th"])]
        rows = [hdr]
        for i, sig in enumerate(signals, 1):
            det = sig.get("details", {})
            rows.append([
                _p(str(i), st["td"]),
                _p(sig.get("name", "—"), st["td_mono"]),
                _p(det.get("subtype", "Signal"), st["td"]),
                _p(f"p.{sig.get('page_ref', '—')}", st["td"]),
                _p(det.get("confidence", "medium"), st["td"]),
            ])
        col_w = [0.8*cm, 5*cm, 3.5*cm, 1.5*cm, 2.5*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(_tbl_style(5))
        story.append(t)
    story += [Spacer(1, 4*mm), PageBreak()]

    # ── SECTION 8: DEPENDENCIES ────────────────────────────────────────────
    story += _section_header("Section 8 — Component Dependencies & Connectivity", "INFERRED", st)
    dep_links = rd.get("dependency_links", [])
    if not dep_links:
        story.append(_p("No port-level dependencies inferred from naming conventions.", st["caption"]))
    else:
        story.append(_p(f"{len(dep_links)} inferred port-level dependency link(s).", st["body"]))
        hdr = [_p("Provider Port", st["th"]), _p("Require Port", st["th"]),
               _p("Inferred Interface", st["th"]), _p("P-Port Page", st["th"]),
               _p("R-Port Page", st["th"]), _p("Confidence", st["th"])]
        rows = [hdr]
        for d in dep_links:
            rows.append([
                _p(d.get("provider_port", "—"), st["td_mono"]),
                _p(d.get("require_port", "—"), st["td_mono"]),
                _p(d.get("inferred_iface", "—"), st["td_mono"]),
                _p(f"p.{d.get('provider_page') or '—'}", st["td"]),
                _p(f"p.{d.get('require_page') or '—'}", st["td"]),
                _p(d.get("confidence", "medium"), st["td"]),
            ])
        col_w = [3.5*cm, 3.5*cm, 3.5*cm, 2*cm, 2*cm, 2*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(_tbl_style(6))
        story.append(t)
    story += [Spacer(1, 4*mm)]

    # ── SECTION 9: ARCHITECTURE FINDINGS ──────────────────────────────────
    story += _section_header("Section 9 — Architecture Findings from Grounded Q&A", "AI-GENERATED", st)
    findings = rd.get("architecture_findings", [])
    if not findings:
        story.append(_p("No Q&A architecture findings recorded.", st["caption"]))
    else:
        for i, f in enumerate(findings, 1):
            block = [
                _p(f"Finding {i}: {_trunc(f.get('question',''), 90)}", st["h3"]),
                _p(f"Q: {f.get('question','—')}", st["body"]),
                _p(f"Answer (model: {f.get('model','—')}):", st["h3"]),
                _p(_trunc(f.get("answer_excerpt", "—"), 500), st["body"]),
            ]
            srcs = f.get("sources", [])
            if srcs:
                src_hdr = [_p("Page", st["th"]), _p("Excerpt [EXTRACTED]", st["th"])]
                src_rows = [src_hdr]
                for s in srcs[:4]:
                    pg  = s.get("page_num") or s.get("page") or "—"
                    txt = _trunc(s.get("text") or s.get("excerpt") or "—", 140)
                    src_rows.append([_p(f"p.{pg}", st["td"]), _p(txt, st["td_muted"])])
                src_tbl = Table(src_rows, colWidths=[1.5*cm, BODY_W-1.5*cm], repeatRows=1)
                src_tbl.setStyle(_tbl_style(2))
                block.append(src_tbl)
            block.append(Spacer(1, 3*mm))
            story.append(KeepTogether(block))
    story += [Spacer(1, 4*mm)]

    # ── SECTION 10: INCONSISTENCIES ────────────────────────────────────────
    story += _section_header("Section 10 — Architecture Inconsistency Findings", "RULE-BASED", st)

    # Summary pills
    sum_data = [[
        _p(f"WARNING: {inc_sum.get('warning', 0)}", st["th"]),
        _p(f"REVIEW: {inc_sum.get('review', 0)}", st["th"]),
        _p(f"INFO: {inc_sum.get('info', 0)}", st["th"]),
        _p(f"Total: {rd.get('inconsistency_count', 0)}", st["th"]),
    ]]
    sum_tbl = Table(sum_data, colWidths=[3.5*cm]*4)
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), _C_RED),
        ("BACKGROUND", (1,0), (1,-1), _C_YELLOW),
        ("BACKGROUND", (2,0), (2,-1), _C_BLUE),
        ("BACKGROUND", (3,0), (3,-1), _C_MUTED),
        ("TEXTCOLOR",  (0,0), (-1,-1), _C_WHITE),
        ("FONTNAME",   (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("GRID",       (0,0), (-1,-1), 0.5, _C_WHITE),
    ]))
    story += [sum_tbl, Spacer(1, 4*mm)]

    inconsistencies = rd.get("inconsistencies", [])
    if not inconsistencies:
        story.append(_p("✓ No document-level inconsistencies detected by the automated rules. Manual review is still required.", st["body"]))
    else:
        for i, inc in enumerate(inconsistencies, 1):
            sev   = (inc.get("severity", "info")).upper()
            cat   = inc.get("category", "general")
            desc  = inc.get("description", "—")
            pages = ", ".join(f"p.{p}" for p in inc.get("pages", [])) or "—"
            sev_color = {"WARNING": _C_RED, "REVIEW": _C_YELLOW, "INFO": _C_BLUE}.get(sev, _C_MUTED)

            block = [
                _p(f"Finding {i} — {sev}: {_trunc(desc, 70)}", st["h3"]),
                _kv_table([
                    ("Severity",      sev),
                    ("Category",      cat),
                    ("Source Pages",  pages),
                    ("Description",   desc),
                ], st),
                Spacer(1, 2*mm),
            ]
            evidence = inc.get("evidence")
            if evidence:
                block += [
                    _p("[EXTRACTED] Evidence from Document:", st["h3"]),
                    _p(_trunc(evidence, 400), st["td_muted"]),
                ]
            reason = inc.get("reason")
            if reason:
                block += [
                    _p("[RULE-BASED] Why Flagged:", st["h3"]),
                    _p(reason, st["body"]),
                ]
            block.append(Spacer(1, 4*mm))
            story.append(KeepTogether(block))

    story.append(PageBreak())

    # ── SECTION 11: Q&A LOG ────────────────────────────────────────────────
    if rd.get("include_qa", True):
        story += _section_header("Section 11 — Q&A Session Log & Source References",
                                 "AI-GENERATED + EXTRACTED", st)
        queries = rd.get("query_log", [])
        if not queries:
            story.append(_p("No Q&A queries recorded for this document session.", st["caption"]))
        else:
            for i, q in enumerate(queries, 1):
                block = [
                    _p(f"Query {i}", st["h3"]),
                    _p(f"Q: {q.get('question', '—')}", st["body"]),
                    _p(f"Engine: {q.get('model_used','—')}  |  Timestamp: {q.get('created_at','—')}", st["caption"]),
                    _p("[AI-GENERATED] Answer:", st["h3"]),
                    _p(_trunc(q.get("answer", "—"), 800), st["body"]),
                ]
                srcs = q.get("sources", [])
                if srcs:
                    src_hdr = [_p("Page", st["th"]), _p("Section", st["th"]), _p("Excerpt [EXTRACTED]", st["th"])]
                    src_rows = [src_hdr]
                    for s in srcs[:6]:
                        pg  = s.get("page_num") or s.get("page") or "—"
                        sec = s.get("section") or "—"
                        txt = _trunc(s.get("text") or s.get("excerpt") or "—", 160)
                        src_rows.append([
                            _p(f"p.{pg}", st["td"]),
                            _p(_trunc(sec, 30), st["td"]),
                            _p(txt, st["td_muted"]),
                        ])
                    src_tbl = Table(src_rows, colWidths=[1.5*cm, 3*cm, BODY_W-4.5*cm], repeatRows=1)
                    src_tbl.setStyle(_tbl_style(3))
                    block.append(src_tbl)
                block.append(Spacer(1, 4*mm))
                story.append(KeepTogether(block[:4]))   # keep Q+A together
                story += block[4:]                       # sources can flow

    story.append(PageBreak())

    # ── SECTION 12: TRACEABILITY INDEX ────────────────────────────────────
    story += _section_header("Section 12 — Source Evidence & Page Traceability Index", "EXTRACTED", st)
    page_idx = rd.get("page_traceability", {})
    trace_entries = [
        (int(pg), info)
        for pg, info in page_idx.items()
        if info.get("entities") or info.get("inconsistencies")
    ]
    trace_entries.sort(key=lambda x: x[0])

    if not trace_entries:
        story.append(_p("No page-entity mappings available. Run entity extraction first.", st["caption"]))
    else:
        hdr = [_p("Page", st["th"]), _p("Entities Detected [EXTRACTED]", st["th"]),
               _p("Confidence", st["th"]), _p("Consistency Observations [RULE-BASED]", st["th"])]
        rows = [hdr]
        for pg, info in trace_entries:
            ents = info.get("entities", [])
            incs = info.get("inconsistencies", [])
            ent_str = ", ".join(e.get("name","") for e in ents[:5])
            if len(ents) > 5:
                ent_str += f" +{len(ents)-5} more"
            high = sum(1 for e in ents if e.get("confidence") == "high")
            low  = sum(1 for e in ents if e.get("confidence") in ("low","uncertain"))
            conf = f"{len(ents)} entities ({high} high / {low} low)" if ents else "—"
            inc_str = "; ".join(_trunc(i, 50) for i in incs[:2]) if incs else "—"
            rows.append([
                _p(f"p.{pg}", st["td"]),
                _p(ent_str or "—", st["td_mono"]),
                _p(conf, st["td"]),
                _p(inc_str, st["td_muted"]),
            ])
        col_w = [1.3*cm, 5.5*cm, 4.5*cm, BODY_W-11.3*cm]
        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(_tbl_style(4))
        story.append(t)
    story.append(PageBreak())

    # ── SECTION 13: REVIEW STATUS & SIGN-OFF ──────────────────────────────
    story += _section_header("Section 13 — Review Status & Engineering Sign-off", None, st)
    story.append(_p("Automated Analysis Status", st["h2"]))

    status_data = [
        [_p("Stage", st["th"]), _p("Completed", st["th"]), _p("Result", st["th"])],
        [_p("Document Ingestion", st["td"]),
         _p("✓" if dm.get("status") == "ready" else "✗", st["td"]),
         _p(dm.get("status","—").upper(), st["td"])],
        [_p("Entity Extraction", st["td"]),
         _p("✓" if ps.get("extraction_performed") else "○ Pending", st["td"]),
         _p(f"{ps.get('total_entities_found',0)} entities found", st["td"])],
        [_p("Consistency Check", st["td"]),
         _p("✓" if ps.get("consistency_checked") else "○ Pending", st["td"]),
         _p(f"{rd.get('inconsistency_count',0)} findings", st["td"])],
        [_p("Q&A Review", st["td"]),
         _p(f"✓" if ps.get("qa_sessions",0) > 0 else "○ None", st["td"]),
         _p(f"{ps.get('qa_sessions',0)} queries", st["td"])],
        [_p("Overall Status", st["td"]),
         _p("", st["td"]),
         _p(rs.get("overall","—"), st["td"])],
    ]
    status_tbl = Table(status_data, colWidths=[6*cm, 4*cm, BODY_W-10*cm], repeatRows=1)
    status_tbl.setStyle(_tbl_style(3))
    story += [status_tbl, Spacer(1, 8*mm)]

    story.append(_p("Human Engineering Sign-off", st["h2"]))
    story.append(_p("Complete this section after reviewing all findings above.", st["caption"]))

    signoff_roles = [
        "Lead Systems Architect",
        "Software Safety Engineer",
        "AUTOSAR Integration Engineer",
        "Review Coordinator",
    ]
    so_data = [
        [_p("Role", st["th"]), _p("Engineer Name", st["th"]),
         _p("Date", st["th"]), _p("Disposition", st["th"])],
    ]
    for role in signoff_roles:
        so_data.append([
            _p(role, st["td"]),
            _p("_______________________", st["td_muted"]),
            _p("____________", st["td_muted"]),
            _p("[ ] Approved   [ ] Revision   [ ] Rejected", st["td_muted"]),
        ])
    so_tbl = Table(so_data, colWidths=[4.5*cm, 4.5*cm, 2.5*cm, BODY_W-11.5*cm], repeatRows=1)
    so_tbl.setStyle(_tbl_style(4))
    story += [so_tbl, Spacer(1, 8*mm)]

    story.append(_p("Review Notes:", st["h3"]))
    for _ in range(5):
        story.append(HRFlowable(width=BODY_W, thickness=0.3, color=_C_BORDER, spaceAfter=8))

    story += [
        Spacer(1, 8*mm),
        HRFlowable(width=BODY_W, thickness=1, color=_C_ACCENT),
        Spacer(1, 3*mm),
        _p(f"Report generated: {generated_at}  |  Tool: {rd.get('tool_version', 'AutoHLD')}", st["caption"]),
        _p(rd.get("disclaimer_short", ""), st["caption"]),
    ]

    doc.build(story)
    return buf.getvalue()
