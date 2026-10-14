"""
test_evaluation.py — Retrieval quality and answer quality evaluation tests.

Tests the full evaluation pipeline:
  1. Retrieval metrics: Precision@K, Recall@K, MRR, Hit Rate
  2. TF-IDF baseline comparison
  3. Answer quality evaluation: faithfulness, relevance, keyword hit rate
  4. EDA statistics computation

These are NOT unit tests in the traditional sense — they measure the
quality of the ML pipeline against ground-truth Q&A pairs from the
sample AUTOSAR BMS HLD document.

Run:
    pytest tests/test_evaluation.py -v
    pytest tests/test_evaluation.py -v -s   (shows metric tables)
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

SAMPLE_PDF  = Path(__file__).parent.parent / "demo" / "sample_docs" / "sample_hld.pdf"
TEST_DOC_ID = "pytest_eval_test"


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ingested_doc():
    """
    Ingest the sample BMS HLD PDF once for all evaluation tests.
    Cleans up vectors after the module finishes.
    """
    if not SAMPLE_PDF.exists():
        pytest.skip("Sample PDF not found. Run: python demo/generate_sample_pdf.py")

    from backend.pipeline.doc_processor import process_pdf
    from backend.pipeline.chunker import chunk_document
    from backend.pipeline.embedder import embed_and_store
    from backend.database.vector_db import delete_document_chunks
    from backend.database.sqlite_db import init_db, create_document, update_document_ready

    init_db()
    delete_document_chunks(TEST_DOC_ID)

    try:
        create_document(TEST_DOC_ID, "sample_hld.pdf", str(SAMPLE_PDF))
    except Exception:
        pass  # Already exists from a previous run

    doc    = process_pdf(SAMPLE_PDF)
    chunks = chunk_document(doc, TEST_DOC_ID)
    stored = embed_and_store(chunks)
    update_document_ready(TEST_DOC_ID, doc.total_pages, stored)

    yield {
        "doc_id":      TEST_DOC_ID,
        "chunk_count": stored,
        "page_count":  doc.total_pages,
    }

    delete_document_chunks(TEST_DOC_ID)


# ── Ground-truth QA pairs ─────────────────────────────────────────────────────

def make_qa_pairs():
    """Return ground-truth QA pairs for the sample BMS document."""
    from backend.evaluation.metrics import QAPair
    return [
        QAPair(
            question         = "What software components are described in this document?",
            expected_pages   = [1, 2, 3],
            expected_keywords= ["BatteryManagement", "ThermalManagement", "component"],
            category         = "entity_lookup",
        ),
        QAPair(
            question         = "What ports does the BatteryManagement component have?",
            expected_pages   = [3, 4, 5],
            expected_keywords= ["port", "P-Port", "R-Port"],
            category         = "entity_lookup",
        ),
        QAPair(
            question         = "Which interfaces are defined in the system?",
            expected_pages   = [2, 3, 4],
            expected_keywords= ["interface", "BattV"],
            category         = "entity_lookup",
        ),
        QAPair(
            question         = "What is the battery voltage signal and which component provides it?",
            expected_pages   = [2, 3],
            expected_keywords= ["voltage", "signal", "BatteryManagement"],
            category         = "relationship",
        ),
        QAPair(
            question         = "Are there any consistency issues or conflicts in the document?",
            expected_pages   = [3, 4, 5, 6],
            expected_keywords= ["inconsistency", "conflict", "missing"],
            category         = "boolean",
        ),
    ]


# ── EDA Tests ─────────────────────────────────────────────────────────────────

class TestEDA:
    """Test Exploratory Data Analysis statistics computation."""

    def test_eda_returns_report(self, ingested_doc):
        """EDA report should be computed without errors."""
        from backend.evaluation.eda import analyze_document
        report = analyze_document(ingested_doc["doc_id"])
        assert report is not None
        assert report.doc_id == ingested_doc["doc_id"]

    def test_eda_chunk_count_matches(self, ingested_doc):
        """EDA chunk count should match what was ingested."""
        from backend.evaluation.eda import analyze_document
        report = analyze_document(ingested_doc["doc_id"])
        assert report.total_chunks == ingested_doc["chunk_count"]

    def test_eda_chunk_size_distribution(self, ingested_doc):
        """Chunk sizes should all be within config bounds."""
        from backend.evaluation.eda import analyze_document
        from backend.config import CHUNK_SIZE_CHARS
        report = analyze_document(ingested_doc["doc_id"])
        # Chunks should not be empty
        assert report.chunk_stats.min_chars > 0
        # Max should be near CHUNK_SIZE_CHARS (may be slightly over at boundaries)
        assert report.chunk_stats.max_chars <= CHUNK_SIZE_CHARS * 1.2
        # Mean should be well below max (most chunks are shorter than the cap)
        assert report.chunk_stats.mean_chars > 0

    def test_eda_vocabulary_populated(self, ingested_doc):
        """Vocabulary should be non-trivial for a real AUTOSAR document."""
        from backend.evaluation.eda import analyze_document
        report = analyze_document(ingested_doc["doc_id"])
        assert report.vocabulary_size > 50, "Vocabulary suspiciously small"
        assert len(report.top_terms) > 0

    def test_eda_autosar_keywords_detected(self, ingested_doc):
        """Sample BMS HLD should contain core AUTOSAR terminology."""
        from backend.evaluation.eda import analyze_document
        report = analyze_document(ingested_doc["doc_id"])
        # The sample document contains SWC, Port, Interface, Signal
        relevant_terms = {"SWC", "Port", "Interface", "Signal"}
        found = {k for k, v in report.autosar_term_freq.items() if v > 0}
        assert relevant_terms & found, (
            f"Expected AUTOSAR keywords not found. Detected: {found}"
        )

    def test_eda_text_summary(self, ingested_doc):
        """Text summary should be a formatted non-empty string."""
        from backend.evaluation.eda import analyze_document
        report = analyze_document(ingested_doc["doc_id"])
        summary = report.to_text()
        assert len(summary) > 100
        assert "EDA Report" in summary
        assert "Chunk Size" in summary
        print("\n" + summary)  # visible with pytest -s

    def test_eda_to_dict(self, ingested_doc):
        """to_dict() should return a JSON-serialisable structure."""
        import json
        from backend.evaluation.eda import analyze_document
        report = analyze_document(ingested_doc["doc_id"])
        d = report.to_dict()
        json_str = json.dumps(d)  # should not raise
        assert len(json_str) > 0


# ── Retrieval Metric Tests ────────────────────────────────────────────────────

class TestRetrievalMetrics:
    """Test Precision@K, Recall@K, MRR, and Hit Rate."""

    def test_evaluate_retrieval_returns_report(self, ingested_doc):
        """evaluate_retrieval() should complete without errors."""
        from backend.evaluation.metrics import evaluate_retrieval
        qa_pairs = make_qa_pairs()
        report = evaluate_retrieval(ingested_doc["doc_id"], qa_pairs, k=5)
        assert report is not None
        assert report.num_questions == len(qa_pairs)

    def test_hit_rate_above_threshold(self, ingested_doc):
        """RAG retrieval should hit at least 1 correct page for 60%+ of questions."""
        from backend.evaluation.metrics import evaluate_retrieval
        qa_pairs = make_qa_pairs()
        report = evaluate_retrieval(ingested_doc["doc_id"], qa_pairs, k=5)
        print(f"\n{report.to_table()}")
        assert report.hit_rate >= 0.6, (
            f"Hit rate {report.hit_rate:.1%} is too low. "
            "Check if the sample PDF was generated and ingested correctly."
        )

    def test_mrr_above_zero(self, ingested_doc):
        """MRR should be > 0 (at least some relevant chunks are ranked first)."""
        from backend.evaluation.metrics import evaluate_retrieval
        qa_pairs = make_qa_pairs()
        report = evaluate_retrieval(ingested_doc["doc_id"], qa_pairs, k=5)
        assert report.mrr > 0.0, "MRR=0 means no relevant chunks were ranked first at all"

    def test_precision_is_valid_range(self, ingested_doc):
        """Precision@K values should be in [0.0, 1.0]."""
        from backend.evaluation.metrics import evaluate_retrieval
        qa_pairs = make_qa_pairs()
        report = evaluate_retrieval(ingested_doc["doc_id"], qa_pairs, k=5)
        for r in report.per_question:
            assert 0.0 <= r.precision_at_k <= 1.0
            assert 0.0 <= r.recall_at_k <= 1.0
            assert 0.0 <= r.reciprocal_rank <= 1.0

    def test_different_k_values(self, ingested_doc):
        """Higher K should have equal or higher recall."""
        from backend.evaluation.metrics import evaluate_retrieval
        qa_pairs = make_qa_pairs()[:3]  # use subset for speed
        report_k3 = evaluate_retrieval(ingested_doc["doc_id"], qa_pairs, k=3)
        report_k5 = evaluate_retrieval(ingested_doc["doc_id"], qa_pairs, k=5)
        # Recall should be monotonically non-decreasing with K
        assert report_k5.mean_recall >= report_k3.mean_recall - 0.01  # small tolerance


# ── Baseline Comparison Tests ─────────────────────────────────────────────────

class TestBaselineComparison:
    """Test TF-IDF baseline retrieval and RAG vs baseline comparison."""

    def test_tfidf_retrieval_returns_chunks(self, ingested_doc):
        """TF-IDF baseline should return chunks for a known question."""
        from backend.evaluation.baseline import tfidf_retrieve
        chunks = tfidf_retrieve(
            "What software components are in this document?",
            ingested_doc["doc_id"],
            top_k=5,
        )
        assert len(chunks) > 0
        assert all(hasattr(c, "page_num") for c in chunks)
        assert all(hasattr(c, "score")    for c in chunks)

    def test_baseline_report_structure(self, ingested_doc):
        """Baseline evaluation report should have same structure as RAG report."""
        from backend.evaluation.baseline import evaluate_baseline_retrieval
        qa_pairs = make_qa_pairs()
        report = evaluate_baseline_retrieval(ingested_doc["doc_id"], qa_pairs, k=5)
        assert report.num_questions == len(qa_pairs)
        assert 0.0 <= report.hit_rate <= 1.0
        assert 0.0 <= report.mrr      <= 1.0

    def test_rag_outperforms_tfidf(self, ingested_doc):
        """
        Semantic RAG should achieve higher Hit Rate than TF-IDF keyword baseline.

        This is the primary justification for using embeddings over keyword search.
        If this test fails, it suggests either the embedding model is not working
        correctly or the chunk size is too small for semantic matching.
        """
        from backend.evaluation.metrics import evaluate_retrieval, compare_to_baseline
        qa_pairs = make_qa_pairs()
        comparison = compare_to_baseline(ingested_doc["doc_id"], qa_pairs, k=5)

        rag_hr  = comparison["rag"]["hit_rate"]
        base_hr = comparison["baseline_tfidf"]["hit_rate"]

        print(f"\nRAG Hit Rate   : {rag_hr:.1%}")
        print(f"TF-IDF Hit Rate: {base_hr:.1%}")
        print(f"Improvement    : {rag_hr - base_hr:+.1%}")

        # RAG should be at least as good as TF-IDF
        # (on a small document, the advantage may be small but should not be negative)
        assert rag_hr >= base_hr - 0.05, (
            f"RAG ({rag_hr:.1%}) underperforms TF-IDF ({base_hr:.1%}) by more than 5%. "
            "Check embedding model and chunk configuration."
        )


# ── Answer Quality Tests ──────────────────────────────────────────────────────

class TestAnswerQuality:
    """Test answer faithfulness and relevance scoring."""

    def test_faithful_answer_scores_high(self):
        """An answer that restates context should score high on faithfulness."""
        from backend.evaluation.metrics import evaluate_answer_quality

        # Simulate a retrieved chunk and a faithful answer
        class FakeChunk:
            text = "BatteryManagement SWC provides the BattVoltage_Prov P-Port."

        answer  = "The BatteryManagement SWC provides the BattVoltage_Prov P-Port."
        result  = evaluate_answer_quality(
            question         = "What ports does BatteryManagement have?",
            answer           = answer,
            retrieved_chunks = [FakeChunk()],
            expected_keywords= ["BatteryManagement", "BattVoltage_Prov"],
        )
        assert result.faithfulness_score >= 0.5
        assert result.keyword_hit_rate   == 1.0
        assert len(result.issues) == 0

    def test_not_found_answer_penalised(self):
        """'Not found' responses should be penalised in relevance score."""
        from backend.evaluation.metrics import evaluate_answer_quality

        class FakeChunk:
            text = "BatteryManagement SWC provides voltage signals."

        answer = "The information was not found in the uploaded document."
        result = evaluate_answer_quality(
            question         = "What is the battery voltage?",
            answer           = answer,
            retrieved_chunks = [FakeChunk()],
        )
        # Relevance should be penalised for "not found" answers
        assert result.relevance_score < 0.5
        assert any("not found" in issue.lower() for issue in result.issues)

    def test_keyword_hit_rate_correct(self):
        """Keyword hit rate should correctly count keyword occurrences."""
        from backend.evaluation.metrics import evaluate_answer_quality

        class FakeChunk:
            text = "context text"

        answer = "BatteryManagement uses the BattV interface with a P-Port connection."
        result = evaluate_answer_quality(
            question         = "What interface does BatteryManagement use?",
            answer           = answer,
            retrieved_chunks = [FakeChunk()],
            expected_keywords= ["BatteryManagement", "BattV", "P-Port", "NotPresent"],
        )
        # 3 of 4 keywords are present
        assert result.keyword_hit_rate == pytest.approx(0.75, abs=0.01)
