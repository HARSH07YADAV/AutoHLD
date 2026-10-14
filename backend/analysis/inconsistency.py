"""
inconsistency.py — Rule-based preliminary consistency checks for AUTOSAR HLD documents.

IMPORTANT DISCLAIMER:
  This is NOT a complete AUTOSAR validator or formal model checker.
  It is a document-level consistency assistant that applies simple, explicit
  rules to extracted text. It flags items that WARRANT ENGINEER REVIEW —
  not items that are definitively wrong.

  Every finding includes:
    - title         : short description
    - description   : what was found
    - severity      : 'review' | 'warning' | 'info'
    - category      : which check produced the finding
    - evidence      : the actual text fragment that triggered the flag
    - pages         : source page numbers
    - reason        : why this was flagged (explicit rule statement)

  Severity guide:
    'review'  — Engineer should look at this. May or may not be an issue.
    'warning' — Strong textual evidence of an inconsistency. Verify carefully.
    'info'    — Observation that may need attention (e.g. missing section).

Five checks implemented:
  1. cross_section_coverage  — entity in one section, absent from another
  2. undefined_interfaces    — port references interface not found in document
  3. description_conflict    — same entity described with conflicting terms
  4. missing_dependencies    — required port with no visible provider
  5. value_conflict          — same property with different numeric values
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from backend.analysis.extractor import ExtractionResult, extract_entities
from backend.database.sqlite_db import save_inconsistencies
from backend.models.schemas import InconsistencyItem

logger = logging.getLogger(__name__)

Severity = Literal["review", "warning", "info"]


# ── Finding dataclass ─────────────────────────────────────────────────────────

@dataclass
class Finding:
    """A single flagged consistency issue."""
    title:       str
    description: str
    severity:    Severity
    category:    str
    evidence:    str
    pages:       list[int]
    reason:      str


@dataclass
class InconsistencyReport:
    doc_id:   str
    findings: list[Finding] = field(default_factory=list)

    def by_severity(self) -> dict[str, list[Finding]]:
        result: dict[str, list[Finding]] = {"warning": [], "review": [], "info": []}
        for f in self.findings:
            result.setdefault(f.severity, []).append(f)
        return result

    def summary(self) -> dict:
        by_sev = self.by_severity()
        return {
            "total":    len(self.findings),
            "warning":  len(by_sev.get("warning", [])),
            "review":   len(by_sev.get("review", [])),
            "info":     len(by_sev.get("info", [])),
        }


# ── Public API ────────────────────────────────────────────────────────────────

def check_consistency(doc_id: str) -> InconsistencyReport:
    """
    Run all consistency checks on an extracted document and return a report.

    Runs entity extraction if not already done, then applies five rules.
    Results are persisted to SQLite for later retrieval.
    """
    logger.info("Starting consistency checks for doc_id=%s", doc_id)

    # Run / re-use entity extraction
    extraction = extract_entities(doc_id)
    report = InconsistencyReport(doc_id=doc_id)

    # Apply each check
    _check_cross_section_coverage(extraction, report)
    _check_undefined_interfaces(extraction, report)
    _check_description_conflict(extraction, report)
    _check_missing_dependencies(extraction, report)
    _check_value_conflicts(extraction, report)

    logger.info(
        "Consistency check complete: %d findings (%s)",
        len(report.findings),
        ", ".join(f"{k}={v}" for k, v in report.summary().items()),
    )

    _persist(doc_id, report)
    return report


# ── Check 1: Cross-section coverage ──────────────────────────────────────────

def _check_cross_section_coverage(
    extraction: ExtractionResult,
    report: InconsistencyReport,
) -> None:
    """
    Rule: A software component mentioned on one page should also appear in
    sections that typically summarise components (e.g. a table of components,
    an overview section).

    Limitation: We infer "summary sections" from page distribution — pages
    with the highest density of component mentions are treated as summary pages.
    This is heuristic; false positives are possible.
    """
    if len(extraction.components) < 2:
        return   # Not enough data to make cross-section comparisons

    # Build: page → set of component names on that page
    page_to_comps: dict[int, set[str]] = defaultdict(set)
    for c in extraction.components:
        page_to_comps[c.page].add(c.name)

    # Find the "densest" page — most likely a summary table
    if not page_to_comps:
        return
    summary_page = max(page_to_comps, key=lambda p: len(page_to_comps[p]))
    summary_comps = page_to_comps[summary_page]

    # Find components on other pages that are not on the summary page
    for page, comps in page_to_comps.items():
        if page == summary_page:
            continue
        missing_from_summary = comps - summary_comps
        for name in missing_from_summary:
            entity = next((c for c in extraction.components if c.name == name), None)
            if not entity:
                continue
            report.findings.append(Finding(
                title       = f"'{name}' not listed on dense component page",
                description = (
                    f"Component '{name}' is mentioned on page {page} but does not "
                    f"appear on page {summary_page}, which contains the highest "
                    f"concentration of component definitions in the document."
                ),
                severity    = "info",
                category    = "cross_section_coverage",
                evidence    = entity.source_text[:200],
                pages       = sorted({page, summary_page}),
                reason      = (
                    "Rule: If page A has more component definitions than any other page, "
                    "components on other pages should also appear there. "
                    "This may indicate a missing entry in a component summary table."
                ),
            ))


# ── Check 2: Undefined interfaces ─────────────────────────────────────────────

def _check_undefined_interfaces(
    extraction: ExtractionResult,
    report: InconsistencyReport,
) -> None:
    """
    Rule: If a port name follows the pattern '<stem>_Prov' or '<stem>_Req'
    and implies an interface '<stem>_If', that interface should appear
    somewhere in the document.

    If it does not, the interface may be defined in a separate document
    or may be missing from this HLD.
    """
    # Build set of known interface names (lowercase for comparison)
    known_interfaces = {i.name.lower() for i in extraction.interfaces}
    known_iface_stems = set()
    for iname in known_interfaces:
        stem = re.sub(r'_(if|interface|iface)$', '', iname, flags=re.I)
        known_iface_stems.add(stem.lower())

    for port in extraction.ports:
        # Derive expected interface stem from port name
        port_stem = re.sub(
            r'_(prov|req|send|recv|in|out|port)$', '', port.name, flags=re.I
        ).lower()

        if not port_stem:
            continue

        # Check if any known interface matches this stem
        matched = (
            port_stem in known_iface_stems
            or any(port_stem in i for i in known_iface_stems)
            or any(i in port_stem for i in known_iface_stems)
        )

        if not matched and port.confidence in ("high", "medium"):
            implied_iface = f"{port.name.rsplit('_', 1)[0]}_If"
            report.findings.append(Finding(
                title       = f"Interface for port '{port.name}' not found",
                description = (
                    f"Port '{port.name}' ({port.subtype}) on page {port.page} implies "
                    f"an interface (expected: '{implied_iface}' or similar), "
                    f"but no matching interface definition was found in this document."
                ),
                severity    = "review",
                category    = "undefined_interface",
                evidence    = port.source_text[:200],
                pages       = [port.page],
                reason      = (
                    "Rule: An AUTOSAR port must be typed by a PortInterface. "
                    "If the implied interface name is not present in this HLD, "
                    "it may be defined in a separate document or may be missing. "
                    "No automatic conclusion is drawn — engineer review required."
                ),
            ))


# ── Check 3: Description conflicts ───────────────────────────────────────────

def _check_description_conflict(
    extraction: ExtractionResult,
    report: InconsistencyReport,
) -> None:
    """
    Rule: If the same entity (by name) appears with substantially different
    surrounding text on different pages, the descriptions may conflict.

    'Substantially different' = no shared significant words between two
    source_text snippets. This is a weak signal — flag as 'info' only.
    """
    # Group all entity source texts by name (case-insensitive)
    name_to_occurrences: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for e in extraction.all_entities():
        if e.source_text and len(e.source_text) > 20:
            name_to_occurrences[e.name.lower()].append((e.page, e.source_text))

    _STOP_WORDS = {
        "the", "a", "an", "of", "in", "is", "are", "and", "or",
        "for", "to", "with", "as", "by", "on", "at", "from",
        "this", "that", "be", "has", "have", "its", "it",
    }

    for name, occurrences in name_to_occurrences.items():
        if len(occurrences) < 2:
            continue

        # Compare first and last occurrence
        page_a, text_a = occurrences[0]
        page_b, text_b = occurrences[-1]
        if page_a == page_b:
            continue

        def sig_words(t: str) -> set:
            return {
                w.lower() for w in re.findall(r'[A-Za-z]{4,}', t)
                if w.lower() not in _STOP_WORDS
            }

        words_a = sig_words(text_a)
        words_b = sig_words(text_b)

        if not words_a or not words_b:
            continue

        overlap = words_a & words_b
        union   = words_a | words_b
        jaccard = len(overlap) / len(union) if union else 1.0

        # Very low overlap (< 20%) between two descriptions of the same name
        if jaccard < 0.20:
            # Find canonical entity
            entity = next(
                (e for e in extraction.all_entities() if e.name.lower() == name),
                None,
            )
            display_name = entity.name if entity else name
            report.findings.append(Finding(
                title       = f"'{display_name}' described differently on two pages",
                description = (
                    f"'{display_name}' appears on page {page_a} and page {page_b} "
                    f"with very different surrounding text (word overlap: "
                    f"{jaccard:.0%}). This may indicate inconsistent descriptions, "
                    f"or the same name being used for two different entities."
                ),
                severity    = "info",
                category    = "description_conflict",
                evidence    = (
                    f"Page {page_a}: \"{text_a[:100].strip()}\"\n"
                    f"Page {page_b}: \"{text_b[:100].strip()}\""
                ),
                pages       = sorted({page_a, page_b}),
                reason      = (
                    "Rule: Two occurrences of the same entity name with less than "
                    "20% word overlap in their surrounding text may indicate "
                    "conflicting descriptions or name reuse. Low confidence — "
                    "review both passages before drawing conclusions."
                ),
            ))


# ── Check 4: Missing dependencies ─────────────────────────────────────────────

def _check_missing_dependencies(
    extraction: ExtractionResult,
    report: InconsistencyReport,
) -> None:
    """
    Rule: For every R-Port (require port), there should be a corresponding
    P-Port (provide port) with a matching stem name somewhere in the document.

    If a required port has no visible provider, the dependency may be:
      (a) provided by a BSW module not described in this HLD, or
      (b) missing from the document.
    """
    # Collect P-Port stems and R-Port stems
    p_port_stems: dict[str, str] = {}   # stem → full port name
    r_port_entities = []

    for port in extraction.ports:
        stem = re.sub(
            r'_(prov|send|out|provider)$', '', port.name, flags=re.I
        ).lower()
        if port.subtype == "P-Port":
            p_port_stems[stem] = port.name
        elif port.subtype == "R-Port":
            r_port_entities.append((port, stem))

    if not r_port_entities:
        return

    for port, r_stem in r_port_entities:
        # Check if any P-Port stem matches this R-Port stem
        matched = (
            r_stem in p_port_stems
            or any(r_stem in ps for ps in p_port_stems)
            or any(ps in r_stem for ps in p_port_stems)
        )

        if not matched and port.confidence in ("high", "medium"):
            report.findings.append(Finding(
                title       = f"No provider found for required port '{port.name}'",
                description = (
                    f"R-Port '{port.name}' on page {port.page} has no corresponding "
                    f"P-Port with a matching name in this document. "
                    f"The provider may be in a BSW module, RTE, or a separate HLD "
                    f"not included in this upload."
                ),
                severity    = "review",
                category    = "missing_dependency",
                evidence    = port.source_text[:200],
                pages       = [port.page],
                reason      = (
                    "Rule: Every AUTOSAR R-Port must be connected to a P-Port that "
                    "provides the same PortInterface. If the providing component is "
                    "not described in this document, the dependency source is unclear. "
                    "This is flagged for review, not declared an error."
                ),
            ))


# ── Check 5: Value conflicts ──────────────────────────────────────────────────

def _check_value_conflicts(
    extraction: ExtractionResult,
    report: InconsistencyReport,
) -> None:
    """
    Rule: If the same entity name is associated with different numeric values
    on different pages (e.g. a signal with two different lengths, or a
    component with different version numbers), flag it.

    Only triggers when two numbers differ by more than ±1 to avoid
    false positives from ordinal references.
    """
    # Patterns for: 'EntityName ... <number>' or '<number> ... EntityName'
    _NUM = re.compile(r'\b(\d+(?:\.\d+)?)\b')

    # Collect: entity name → list of (page, [numbers found nearby])
    name_to_values: dict[str, list[tuple[int, list[float]]]] = defaultdict(list)

    for e in extraction.all_entities():
        if not e.source_text:
            continue
        numbers = [float(m) for m in _NUM.findall(e.source_text) if float(m) > 1]
        if numbers:
            name_to_values[e.name.lower()].append((e.page, numbers))

    for name, page_values in name_to_values.items():
        if len(page_values) < 2:
            continue

        # Find if any number pair across pages differs significantly
        for i, (pa, nums_a) in enumerate(page_values):
            for pb, nums_b in page_values[i + 1:]:
                if pa == pb:
                    continue

                # Compare min/max of each page's numbers
                min_a, max_a = min(nums_a), max(nums_a)
                min_b, max_b = min(nums_b), max(nums_b)

                # Check if ranges don't overlap (excluding page numbers like 1, 2, 3)
                no_overlap = max_a < min_b - 1 or max_b < min_a - 1
                has_big_num = max(max_a, max_b) > 10  # avoid triggering on page refs

                if no_overlap and has_big_num:
                    entity = next(
                        (e for e in extraction.all_entities() if e.name.lower() == name),
                        None,
                    )
                    display_name = entity.name if entity else name
                    report.findings.append(Finding(
                        title       = f"Numeric values differ for '{display_name}'",
                        description = (
                            f"'{display_name}' appears with different numeric values "
                            f"on page {pa} ({nums_a}) and page {pb} ({nums_b}). "
                            f"This may indicate conflicting specifications or version "
                            f"differences."
                        ),
                        severity    = "warning",
                        category    = "value_conflict",
                        evidence    = (
                            f"Page {pa}: values {nums_a}\n"
                            f"Page {pb}: values {nums_b}"
                        ),
                        pages       = sorted({pa, pb}),
                        reason      = (
                            "Rule: The same entity appearing with non-overlapping "
                            "numeric value sets on different pages may indicate "
                            "a conflicting specification. Verify both passages "
                            "against the authoritative source."
                        ),
                    ))
                    break  # One finding per entity name


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist(doc_id: str, report: InconsistencyReport) -> None:
    """Save findings to SQLite as InconsistencyItem objects."""
    items = [
        InconsistencyItem(
            severity    = f.severity,
            category    = f.category,
            description = f.description,
            pages       = f.pages,
        )
        for f in report.findings
    ]
    save_inconsistencies(doc_id, items)
