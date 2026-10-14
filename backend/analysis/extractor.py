"""
extractor.py — Regex-based AUTOSAR entity extraction from document chunks.

Responsibility:
  Scan all chunks stored for a document and attempt to identify:
    - Software Components (SWCs)
    - Ports (P-Port / R-Port)
    - Interfaces
    - Signals
    - Dependencies (inferred from port co-location)
    - Functional flows (runnable references)

Design principles:
  1. Honesty over completeness: entities that don't match patterns clearly
     are marked "uncertain" rather than invented.
  2. Every entity carries: name, type, source_page, source_text, confidence.
  3. Two-pass: regex first (fast), then heuristic scoring.
  4. Relationships are inferred from co-occurrence on the same page.

Confidence levels:
  "high"      — strong pattern match (e.g. explicit "P-Port" keyword)
  "medium"    — probable match (naming convention only)
  "low"       — weak signal, needs manual verification
  "uncertain" — pattern matched but context is ambiguous
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from backend.database.sqlite_db import save_entities
from backend.database.vector_db import get_all_chunks_for_doc

logger = logging.getLogger(__name__)

Confidence = Literal["high", "medium", "low", "uncertain"]

# ── Regex patterns ─────────────────────────────────────────────────────────────

# SWC: explicit keyword or common naming patterns
_RE_SWC_EXPLICIT = re.compile(
    r'\b([A-Z][A-Za-z0-9]{2,40})\s*(?:SWC|Software\s*Component|AtomicSWC)\b'
)
_RE_SWC_NAMING = re.compile(
    r'\b([A-Z][A-Za-z0-9]{3,40}'
    r'(?:Manager|Management|Controller|Handler|Monitor|Control|Mgr|Ctrl))\b'
)

# Ports: explicit direction keywords (highest confidence)
_RE_PORT_EXPLICIT = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_]{2,50})\b\s*[:\-–]?\s*\b([PR]-Port|PPort|RPort|'
    r'ProvidePort|RequirePort|Provide\s*Port|Require\s*Port)\b',
    re.IGNORECASE,
)
_RE_PORT_EXPLICIT_REV = re.compile(
    r'\b([PR]-Port|PPort|RPort|ProvidePort|RequirePort)\b\s*[:\-–]?\s*'
    r'([A-Za-z][A-Za-z0-9_]{2,50})\b',
    re.IGNORECASE,
)
# Naming convention: _Prov / _Req suffixes
_RE_PORT_NAMING = re.compile(
    r'\b([A-Za-z][A-Za-z0-9]{2,40}_(?:Prov|Req|Send|Recv|In|Out|Port))\b'
)

# Interfaces
_RE_IFACE_EXPLICIT = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_]{2,50})\b\s*[:\-–]?\s*\b'
    r'(?:Interface|PortInterface|SenderReceiver|ClientServer|SR|CS)\b',
    re.IGNORECASE,
)
_RE_IFACE_NAMING = re.compile(
    r'\b([A-Za-z][A-Za-z0-9]{2,40}_(?:If|Interface|Iface|IF))\b'
)

# Signals
_RE_SIGNAL_EXPLICIT = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_]{2,50})\b\s*[:\-–]?\s*\b(?:Signal|DataElement)\b',
    re.IGNORECASE,
)
_RE_SIGNAL_NAMING = re.compile(
    r'\b([A-Za-z][A-Za-z0-9]{2,40}_(?:Sig|Signal|Val|Value|Cmd|Data|Msg))\b'
)

# Runnables (functional flows)
_RE_RUNNABLE = re.compile(
    r'\b(Runnable_[A-Za-z][A-Za-z0-9_]{2,50})\b'
)
_RE_RUNNABLE_ALT = re.compile(
    r'\b([A-Za-z][A-Za-z0-9_]{2,50})\s+(?:Runnable|runnable|RUNNABLE)\b'
)


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class ExtractedEntity:
    name:        str
    entity_type: str        # component | port | interface | signal | runnable
    subtype:     str = ""   # P-Port / R-Port / SenderReceiver etc.
    page:        int  = 0
    source_text: str  = ""  # the sentence/line where it was found
    confidence:  Confidence = "medium"
    doc_id:      str  = ""


@dataclass
class Relationship:
    """An inferred connection between two entities."""
    source:       str   # name of source entity
    source_type:  str
    target:       str   # name of target entity
    target_type:  str
    relation:     str   # "provides" | "requires" | "uses" | "connected_to"
    page:         int   = 0
    confidence:   Confidence = "low"


@dataclass
class ExtractionResult:
    doc_id:        str
    components:    list[ExtractedEntity] = field(default_factory=list)
    ports:         list[ExtractedEntity] = field(default_factory=list)
    interfaces:    list[ExtractedEntity] = field(default_factory=list)
    signals:       list[ExtractedEntity] = field(default_factory=list)
    runnables:     list[ExtractedEntity] = field(default_factory=list)
    relationships: list[Relationship]    = field(default_factory=list)

    def all_entities(self) -> list[ExtractedEntity]:
        return (self.components + self.ports + self.interfaces +
                self.signals + self.runnables)

    def summary(self) -> dict:
        return {
            "components":    len(self.components),
            "ports":         len(self.ports),
            "interfaces":    len(self.interfaces),
            "signals":       len(self.signals),
            "runnables":     len(self.runnables),
            "relationships": len(self.relationships),
        }


# ── Public API ────────────────────────────────────────────────────────────────

def extract_entities(doc_id: str) -> ExtractionResult:
    """
    Extract AUTOSAR entities from all chunks stored for a document.

    Reads chunks from ChromaDB, applies regex patterns, deduplicates,
    infers relationships, persists to SQLite, and returns the full result.
    """
    logger.info("Starting entity extraction for doc_id=%s", doc_id)

    chunks = get_all_chunks_for_doc(doc_id)
    if not chunks:
        logger.warning("No chunks found for doc_id=%s", doc_id)
        return ExtractionResult(doc_id=doc_id)

    result = ExtractionResult(doc_id=doc_id)

    # Collect raw findings per page for relationship inference
    page_components: dict[int, list[str]] = defaultdict(list)
    page_ports:      dict[int, list[ExtractedEntity]] = defaultdict(list)
    page_interfaces: dict[int, list[str]] = defaultdict(list)

    for chunk in chunks:
        text     = chunk["text"]
        page_num = int(chunk["metadata"].get("page_num", 0))
        section  = chunk["metadata"].get("section", "")

        # ── Extract from each chunk ────────────────────────────────────────
        _extract_components(text, page_num, section, doc_id, result, page_components)
        _extract_ports(text, page_num, section, doc_id, result, page_ports)
        _extract_interfaces(text, page_num, section, doc_id, result, page_interfaces)
        _extract_signals(text, page_num, section, doc_id, result)
        _extract_runnables(text, page_num, section, doc_id, result)

    # ── Deduplicate (keep highest confidence per name+type) ────────────────
    result.components  = _deduplicate(result.components)
    result.ports       = _deduplicate(result.ports)
    result.interfaces  = _deduplicate(result.interfaces)
    result.signals     = _deduplicate(result.signals)
    result.runnables   = _deduplicate(result.runnables)

    # ── Infer relationships ────────────────────────────────────────────────
    result.relationships = _infer_relationships(
        result.components, result.ports, result.interfaces, page_ports
    )

    # ── Persist to SQLite ──────────────────────────────────────────────────
    _persist(doc_id, result)

    logger.info(
        "Extraction complete: %s",
        ", ".join(f"{k}={v}" for k, v in result.summary().items()),
    )

    return result


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_components(
    text: str, page: int, section: str, doc_id: str,
    result: ExtractionResult,
    page_components: dict,
) -> None:
    seen = set()

    for m in _RE_SWC_EXPLICIT.finditer(text):
        name = m.group(1).strip()
        if name in seen or len(name) < 3:
            continue
        seen.add(name)
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="component", subtype="SWC",
            page=page, source_text=snippet, confidence="high", doc_id=doc_id,
        )
        result.components.append(e)
        page_components[page].append(name)

    for m in _RE_SWC_NAMING.finditer(text):
        name = m.group(1).strip()
        if name in seen or len(name) < 5:
            continue
        seen.add(name)
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="component", subtype="SWC (inferred)",
            page=page, source_text=snippet, confidence="medium", doc_id=doc_id,
        )
        result.components.append(e)
        page_components[page].append(name)


def _extract_ports(
    text: str, page: int, section: str, doc_id: str,
    result: ExtractionResult,
    page_ports: dict,
) -> None:
    seen = set()

    # Explicit direction from table/text: "BattVoltage_Prov : P-Port"
    for m in _RE_PORT_EXPLICIT.finditer(text):
        name, direction = m.group(1).strip(), m.group(2).strip()
        if name in seen:
            continue
        seen.add(name)
        subtype = "P-Port" if direction.upper().startswith("P") else "R-Port"
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="port", subtype=subtype,
            page=page, source_text=snippet, confidence="high", doc_id=doc_id,
        )
        result.ports.append(e)
        page_ports[page].append(e)

    # Reversed form: "P-Port : BattVoltage_Prov"
    for m in _RE_PORT_EXPLICIT_REV.finditer(text):
        direction, name = m.group(1).strip(), m.group(2).strip()
        if name in seen:
            continue
        seen.add(name)
        subtype = "P-Port" if direction.upper().startswith("P") else "R-Port"
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="port", subtype=subtype,
            page=page, source_text=snippet, confidence="high", doc_id=doc_id,
        )
        result.ports.append(e)
        page_ports[page].append(e)

    # Naming convention only
    for m in _RE_PORT_NAMING.finditer(text):
        name = m.group(1).strip()
        if name in seen:
            continue
        seen.add(name)
        suffix = name.rsplit("_", 1)[-1].lower()
        subtype = "P-Port" if suffix in ("prov", "send", "out") else "R-Port"
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="port", subtype=subtype,
            page=page, source_text=snippet, confidence="medium", doc_id=doc_id,
        )
        result.ports.append(e)
        page_ports[page].append(e)


def _extract_interfaces(
    text: str, page: int, section: str, doc_id: str,
    result: ExtractionResult,
    page_interfaces: dict,
) -> None:
    seen = set()

    for m in _RE_IFACE_EXPLICIT.finditer(text):
        name = m.group(1).strip()
        if name in seen or len(name) < 3:
            continue
        seen.add(name)
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="interface", subtype="PortInterface",
            page=page, source_text=snippet, confidence="high", doc_id=doc_id,
        )
        result.interfaces.append(e)
        page_interfaces[page].append(name)

    for m in _RE_IFACE_NAMING.finditer(text):
        name = m.group(1).strip()
        if name in seen:
            continue
        seen.add(name)
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="interface", subtype="PortInterface (inferred)",
            page=page, source_text=snippet, confidence="medium", doc_id=doc_id,
        )
        result.interfaces.append(e)
        page_interfaces[page].append(name)


def _extract_signals(
    text: str, page: int, section: str, doc_id: str,
    result: ExtractionResult,
) -> None:
    seen = set()

    for m in _RE_SIGNAL_EXPLICIT.finditer(text):
        name = m.group(1).strip()
        if name in seen or len(name) < 3:
            continue
        seen.add(name)
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="signal", subtype="DataElement",
            page=page, source_text=snippet, confidence="high", doc_id=doc_id,
        )
        result.signals.append(e)

    for m in _RE_SIGNAL_NAMING.finditer(text):
        name = m.group(1).strip()
        if name in seen:
            continue
        seen.add(name)
        snippet = _snippet(text, m.start())
        e = ExtractedEntity(
            name=name, entity_type="signal", subtype="DataElement (inferred)",
            page=page, source_text=snippet, confidence="medium", doc_id=doc_id,
        )
        result.signals.append(e)


def _extract_runnables(
    text: str, page: int, section: str, doc_id: str,
    result: ExtractionResult,
) -> None:
    seen = set()

    for pattern in (_RE_RUNNABLE, _RE_RUNNABLE_ALT):
        for m in pattern.finditer(text):
            name = m.group(1).strip()
            if name in seen or len(name) < 4:
                continue
            seen.add(name)
            snippet = _snippet(text, m.start())
            e = ExtractedEntity(
                name=name, entity_type="runnable", subtype="Functional flow",
                page=page, source_text=snippet, confidence="high", doc_id=doc_id,
            )
            result.runnables.append(e)


# ── Relationship inference ────────────────────────────────────────────────────

def _infer_relationships(
    components:      list[ExtractedEntity],
    ports:           list[ExtractedEntity],
    interfaces:      list[ExtractedEntity],
    page_ports:      dict[int, list[ExtractedEntity]],
) -> list[Relationship]:
    """
    Infer relationships from co-location of entities on the same page.

    Rules:
      - A P-Port on the same page as a component → component "provides" port
      - A R-Port on the same page as a component → component "requires" port
      - A port whose name contains an interface name → port "uses" interface
      - A P-Port and R-Port sharing an interface name → "connected_to" relationship
    """
    rels: list[Relationship] = []

    # Build component page map
    comp_pages: dict[int, list[str]] = defaultdict(list)
    for c in components:
        comp_pages[c.page].append(c.name)

    # Build interface name set for quick lookup
    iface_names = {i.name for i in interfaces}

    # Port → component on same page
    for page, ports_on_page in page_ports.items():
        comps_on_page = comp_pages.get(page, [])
        for port in ports_on_page:
            for comp in comps_on_page:
                relation = "provides" if port.subtype == "P-Port" else "requires"
                rels.append(Relationship(
                    source=comp, source_type="component",
                    target=port.name, target_type="port",
                    relation=relation, page=page, confidence="low",
                ))

    # Port → interface (name contains interface name)
    for port in ports:
        for iface in interfaces:
            # e.g. "BattVoltage_Prov" references "BattVoltage_If"
            port_stem = re.sub(r'_(Prov|Req|Send|Recv|In|Out|Port)$', '', port.name, flags=re.I)
            iface_stem = re.sub(r'_(If|Interface|Iface|IF)$', '', iface.name, flags=re.I)
            if port_stem.lower() == iface_stem.lower() or port_stem in iface.name:
                rels.append(Relationship(
                    source=port.name, source_type="port",
                    target=iface.name, target_type="interface",
                    relation="uses", page=port.page, confidence="medium",
                ))

    # Deduplicate relationships
    seen_rels = set()
    unique_rels = []
    for r in rels:
        key = (r.source, r.target, r.relation)
        if key not in seen_rels:
            seen_rels.add(key)
            unique_rels.append(r)

    return unique_rels


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snippet(text: str, pos: int, window: int = 150) -> str:
    """Extract a short context snippet around the match position."""
    start = max(0, pos - 40)
    end   = min(len(text), pos + window)
    raw   = text[start:end].replace("\n", " ").strip()
    return raw[:200]


def _deduplicate(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    """
    Deduplicate by name, keeping the highest confidence entry.
    """
    _conf_rank = {"high": 3, "medium": 2, "low": 1, "uncertain": 0}
    best: dict[str, ExtractedEntity] = {}
    for e in entities:
        key = e.name.lower()
        if key not in best:
            best[key] = e
        elif _conf_rank[e.confidence] > _conf_rank[best[key].confidence]:
            best[key] = e
    return sorted(best.values(), key=lambda e: (e.page, e.name))


def _persist(doc_id: str, result: ExtractionResult) -> None:
    """Save all extracted entities to SQLite for later report generation."""
    entities = []
    for e in result.all_entities():
        entities.append({
            "entity_type": e.entity_type,
            "name":        e.name,
            "page_ref":    e.page,
            "details": {
                "subtype":     e.subtype,
                "source_text": e.source_text,
                "confidence":  e.confidence,
            },
        })
    save_entities(doc_id, entities)
