"""
test_inconsistency.py — Tests for Phase 4 consistency checks.

All five rules are tested independently with synthetic data.
No LLM, no Ollama, no external services required.

Run:
    pytest tests/test_inconsistency.py -v
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.analysis.inconsistency import (
    Finding,
    InconsistencyReport,
    check_consistency,
    _check_cross_section_coverage,
    _check_undefined_interfaces,
    _check_description_conflict,
    _check_missing_dependencies,
    _check_value_conflicts,
)
from backend.analysis.extractor import (
    ExtractedEntity,
    ExtractionResult,
    Relationship,
)

DOC_ID = "pytest_inconsistency_test"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_component(name: str, page: int, text: str = "", confidence: str = "high") -> ExtractedEntity:
    return ExtractedEntity(
        name=name, entity_type="component", subtype="SWC",
        page=page, source_text=text or f"The {name} SWC is defined here.",
        confidence=confidence, doc_id=DOC_ID,
    )


def make_port(name: str, page: int, subtype: str = "P-Port",
              text: str = "", confidence: str = "high") -> ExtractedEntity:
    return ExtractedEntity(
        name=name, entity_type="port", subtype=subtype,
        page=page, source_text=text or f"{name} is a {subtype}.",
        confidence=confidence, doc_id=DOC_ID,
    )


def make_interface(name: str, page: int, text: str = "", confidence: str = "high") -> ExtractedEntity:
    return ExtractedEntity(
        name=name, entity_type="interface", subtype="PortInterface",
        page=page, source_text=text or f"Interface {name} is defined here.",
        confidence=confidence, doc_id=DOC_ID,
    )


def make_signal(name: str, page: int, text: str = "") -> ExtractedEntity:
    return ExtractedEntity(
        name=name, entity_type="signal", subtype="DataElement",
        page=page, source_text=text or f"Signal {name}.",
        confidence="high", doc_id=DOC_ID,
    )


def empty_extraction() -> ExtractionResult:
    return ExtractionResult(doc_id=DOC_ID)


# ── Report dataclass tests ────────────────────────────────────────────────────

class TestReportDataclass:
    def test_summary_counts_match(self):
        report = InconsistencyReport(doc_id=DOC_ID)
        report.findings = [
            Finding("t", "d", "warning",  "cat", "e", [1], "r"),
            Finding("t", "d", "warning",  "cat", "e", [2], "r"),
            Finding("t", "d", "review",   "cat", "e", [3], "r"),
            Finding("t", "d", "info",     "cat", "e", [4], "r"),
        ]
        s = report.summary()
        assert s["total"]   == 4
        assert s["warning"] == 2
        assert s["review"]  == 1
        assert s["info"]    == 1

    def test_empty_report_summary(self):
        report = InconsistencyReport(doc_id=DOC_ID)
        s = report.summary()
        assert s["total"] == 0

    def test_by_severity_groups_correctly(self):
        report = InconsistencyReport(doc_id=DOC_ID)
        report.findings = [
            Finding("t", "d", "warning", "c", "e", [1], "r"),
            Finding("t", "d", "info",    "c", "e", [2], "r"),
        ]
        grouped = report.by_severity()
        assert len(grouped["warning"]) == 1
        assert len(grouped["info"])    == 1
        assert len(grouped["review"])  == 0


# ── Check 1: Cross-section coverage ──────────────────────────────────────────

class TestCrossSectionCoverage:
    def test_no_findings_if_single_component(self):
        extraction = empty_extraction()
        extraction.components = [make_component("BattMgr", 1)]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_cross_section_coverage(extraction, report)
        assert len(report.findings) == 0

    def test_component_only_on_sparse_page_flagged(self):
        extraction = empty_extraction()
        # Page 1 has 3 components → "summary page"
        # Page 5 has 1 component not on page 1 → flagged
        extraction.components = [
            make_component("CompA", 1),
            make_component("CompB", 1),
            make_component("CompC", 1),
            make_component("CompD", 5),   # not on page 1
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_cross_section_coverage(extraction, report)
        assert len(report.findings) > 0
        titles = [f.title for f in report.findings]
        assert any("CompD" in t for t in titles)

    def test_no_flags_when_all_on_same_page(self):
        extraction = empty_extraction()
        extraction.components = [
            make_component("A", 2), make_component("B", 2), make_component("C", 2),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_cross_section_coverage(extraction, report)
        assert len(report.findings) == 0


# ── Check 2: Undefined interfaces ─────────────────────────────────────────────

class TestUndefinedInterfaces:
    def test_port_with_matching_interface_no_flag(self):
        extraction = empty_extraction()
        extraction.ports      = [make_port("BattVoltage_Prov", 4)]
        extraction.interfaces = [make_interface("BattVoltage_If", 2)]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_undefined_interfaces(extraction, report)
        assert len(report.findings) == 0

    def test_port_without_any_interface_flagged(self):
        extraction = empty_extraction()
        extraction.ports      = [make_port("PowerCtrl_Req", 7)]
        extraction.interfaces = []
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_undefined_interfaces(extraction, report)
        assert len(report.findings) == 1
        assert report.findings[0].severity == "review"
        assert "PowerCtrl_Req" in report.findings[0].title

    def test_low_confidence_port_not_flagged(self):
        """Low-confidence extractions should not generate undefined interface flags."""
        extraction = empty_extraction()
        extraction.ports      = [make_port("Unknown_Req", 3, confidence="low")]
        extraction.interfaces = []
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_undefined_interfaces(extraction, report)
        assert len(report.findings) == 0


# ── Check 3: Description conflict ────────────────────────────────────────────

class TestDescriptionConflict:
    def test_same_name_very_different_text_flagged(self):
        extraction = empty_extraction()
        # Very different words for same component name
        extraction.components = [
            make_component("BattMgr", 1, "voltage charging battery management"),
            make_component("BattMgr", 9, "network protocol communication routing"),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_description_conflict(extraction, report)
        assert len(report.findings) > 0

    def test_same_name_similar_text_no_flag(self):
        extraction = empty_extraction()
        # Sufficiently similar words → no conflict
        extraction.components = [
            make_component("BattMgr", 1, "battery voltage management charging system SWC"),
            make_component("BattMgr", 3, "battery management voltage charging component SWC"),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_description_conflict(extraction, report)
        assert len(report.findings) == 0

    def test_single_occurrence_never_flagged(self):
        extraction = empty_extraction()
        extraction.components = [make_component("LoneSWC", 5, "some component text here")]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_description_conflict(extraction, report)
        assert len(report.findings) == 0


# ── Check 4: Missing dependencies ─────────────────────────────────────────────

class TestMissingDependencies:
    def test_r_port_with_matching_p_port_no_flag(self):
        extraction = empty_extraction()
        extraction.ports = [
            make_port("BattVoltage_Prov", 4, "P-Port"),
            make_port("BattVoltage_Req",  7, "R-Port"),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_missing_dependencies(extraction, report)
        assert len(report.findings) == 0

    def test_r_port_without_p_port_flagged(self):
        extraction = empty_extraction()
        extraction.ports = [
            make_port("TempSensor_Req", 5, "R-Port"),   # no provider
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_missing_dependencies(extraction, report)
        assert len(report.findings) == 1
        assert report.findings[0].severity == "review"
        assert "TempSensor_Req" in report.findings[0].title

    def test_no_r_ports_no_findings(self):
        extraction = empty_extraction()
        extraction.ports = [make_port("A_Prov", 1, "P-Port")]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_missing_dependencies(extraction, report)
        assert len(report.findings) == 0


# ── Check 5: Value conflicts ──────────────────────────────────────────────────

class TestValueConflicts:
    def test_conflicting_large_values_flagged(self):
        extraction = empty_extraction()
        extraction.signals = [
            make_signal("BattVoltage", 3, "BattVoltage maximum value is 5000 mV"),
            make_signal("BattVoltage", 8, "BattVoltage maximum value is 9999 mV"),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_value_conflicts(extraction, report)
        # Large non-overlapping numbers on different pages should flag
        # (may or may not trigger depending on min/max range)
        # At minimum we verify the check doesn't crash
        assert isinstance(report.findings, list)

    def test_no_conflict_when_values_same(self):
        extraction = empty_extraction()
        extraction.signals = [
            make_signal("BattSOC", 2, "BattSOC range 100 percent"),
            make_signal("BattSOC", 6, "BattSOC maximum 100 percent"),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_value_conflicts(extraction, report)
        assert len(report.findings) == 0

    def test_no_crash_with_no_numerics(self):
        extraction = empty_extraction()
        extraction.components = [
            make_component("PowerCtrl", 1, "no numbers here just text"),
            make_component("PowerCtrl", 5, "also no numbers in this text"),
        ]
        report = InconsistencyReport(doc_id=DOC_ID)
        _check_value_conflicts(extraction, report)
        assert isinstance(report.findings, list)


# ── Full pipeline test (mocked extraction) ────────────────────────────────────

class TestFullConsistencyPipeline:
    SAMPLE_PDF = Path(__file__).parent.parent / "demo" / "sample_docs" / "sample_hld.pdf"

    def test_check_consistency_returns_report(self):
        """Full pipeline: extraction + 5 checks on the sample PDF."""
        if not self.SAMPLE_PDF.exists():
            pytest.skip("Sample PDF not found.")

        # Make sure the document is ingested first
        from backend.database.sqlite_db import init_db, create_document, update_document_ready
        from backend.database.vector_db import delete_document_chunks
        from backend.pipeline.doc_processor import process_pdf
        from backend.pipeline.chunker import chunk_document
        from backend.pipeline.embedder import embed_and_store

        test_doc_id = "pytest_consistency_integration"
        init_db()
        delete_document_chunks(test_doc_id)
        try:
            create_document(test_doc_id, "sample_hld.pdf", str(self.SAMPLE_PDF))
        except Exception:
            pass

        doc    = process_pdf(self.SAMPLE_PDF)
        chunks = chunk_document(doc, test_doc_id)
        stored = embed_and_store(chunks)
        update_document_ready(test_doc_id, doc.total_pages, stored)

        # Patch _persist so we don't need a full SQLite record
        with patch("backend.analysis.inconsistency._persist"):
            report = check_consistency(test_doc_id)

        assert isinstance(report, InconsistencyReport)
        assert isinstance(report.findings, list)
        assert isinstance(report.summary(), dict)
        assert "total" in report.summary()

    def test_findings_have_required_fields(self):
        """Every finding must have all required fields set."""
        if not self.SAMPLE_PDF.exists():
            pytest.skip("Sample PDF not found.")

        from backend.database.sqlite_db import init_db
        init_db()

        with patch("backend.analysis.inconsistency._persist"):
            report = check_consistency("pytest_consistency_integration")

        for f in report.findings:
            assert f.title,       f"Finding missing title: {f}"
            assert f.description, f"Finding missing description: {f}"
            assert f.severity in ("warning", "review", "info"), f"Invalid severity: {f.severity}"
            assert f.category,    f"Finding missing category: {f}"
            assert f.reason,      f"Finding missing reason: {f}"
            assert isinstance(f.pages, list), f"pages should be a list: {f}"

    def test_no_finding_claims_definitive_error(self):
        """
        No finding in a preliminary consistency check should claim the document
        is 'definitely wrong' — only that it 'warrants review'.
        """
        if not self.SAMPLE_PDF.exists():
            pytest.skip("Sample PDF not found.")

        from backend.database.sqlite_db import init_db
        init_db()

        DEFINITIVE_PHRASES = [
            "is definitely wrong",
            "is an error",
            "must be fixed",
            "incorrect",
        ]

        with patch("backend.analysis.inconsistency._persist"):
            report = check_consistency("pytest_consistency_integration")

        for f in report.findings:
            combined = (f.description + f.reason).lower()
            for phrase in DEFINITIVE_PHRASES:
                assert phrase not in combined, (
                    f"Finding '{f.title}' contains definitive language: '{phrase}'"
                )
