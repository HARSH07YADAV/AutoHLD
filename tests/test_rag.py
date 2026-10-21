"""
test_rag.py — Tests for the Phase 2 RAG pipeline.

Tests retriever, prompt builder, and full RAG flow.
The LLM client is mocked so Ollama is NOT required to run these tests.

Run:
    pytest tests/test_rag.py -v
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

SAMPLE_PDF = Path(__file__).parent.parent / "demo" / "sample_docs" / "sample_hld.pdf"
TEST_DOC_ID = "pytest_rag_test"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ingested_doc():
    """
    Ingest the sample PDF once for all RAG tests.
    Cleans up after the module finishes.
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

    # Minimal SQLite record so rag.ask() can validate the doc
    try:
        create_document(TEST_DOC_ID, "sample_hld.pdf", str(SAMPLE_PDF))
    except Exception:
        pass  # Already exists from a previous run

    doc    = process_pdf(SAMPLE_PDF)
    chunks = chunk_document(doc, TEST_DOC_ID)
    stored = embed_and_store(chunks)

    update_document_ready(TEST_DOC_ID, doc.total_pages, stored)

    yield {"doc_id": TEST_DOC_ID, "chunk_count": stored, "page_count": doc.total_pages}

    delete_document_chunks(TEST_DOC_ID)


# ── Retriever tests ───────────────────────────────────────────────────────────

class TestRetriever:
    def test_returns_list_of_retrieved_chunks(self, ingested_doc):
        from backend.pipeline.retriever import retrieve, RetrievedChunk
        results = retrieve("What are the software components?", TEST_DOC_ID, top_k=3)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, RetrievedChunk) for r in results)

    def test_every_chunk_has_valid_page_num(self, ingested_doc):
        from backend.pipeline.retriever import retrieve
        results = retrieve("What are the provider ports?", TEST_DOC_ID)
        for r in results:
            assert r.page_num >= 1, f"Invalid page_num={r.page_num}"

    def test_scores_are_between_zero_and_one(self, ingested_doc):
        from backend.pipeline.retriever import retrieve
        results = retrieve("BatteryManagement SWC interfaces", TEST_DOC_ID)
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"Score out of range: {r.score}"

    def test_results_ordered_by_descending_score(self, ingested_doc):
        from backend.pipeline.retriever import retrieve
        results = retrieve("signal list", TEST_DOC_ID, top_k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "Results not in descending score order"

    def test_empty_question_returns_empty(self, ingested_doc):
        from backend.pipeline.retriever import retrieve
        results = retrieve("", TEST_DOC_ID)
        assert results == []

    def test_autosar_specific_query_retrieves_relevant_content(self, ingested_doc):
        from backend.pipeline.retriever import retrieve
        results = retrieve("BatteryManagement provider ports", TEST_DOC_ID, top_k=3)
        # At least one result should mention battery or port
        combined = " ".join(r.text.lower() for r in results)
        assert any(kw in combined for kw in ["batter", "port", "swc", "interface"]), (
            "Expected AUTOSAR-related content in results for AUTOSAR query"
        )


# ── Prompt builder tests ──────────────────────────────────────────────────────

class TestPromptBuilder:
    def test_returns_two_messages(self):
        from backend.pipeline.prompt_builder import build_prompt
        from backend.pipeline.retriever import RetrievedChunk
        chunks = [
            RetrievedChunk(
                text="BattVoltage_Prov is a P-Port of the BatteryManagement SWC.",
                page_num=12, section="2.1 BatteryManagement", chunk_index=0,
                score=0.9, doc_id=TEST_DOC_ID, filename="sample_hld.pdf",
            )
        ]
        messages = build_prompt("What are the ports?", chunks, "sample_hld.pdf")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_message_contains_grounding_rule(self):
        from backend.pipeline.prompt_builder import build_prompt
        messages = build_prompt("test question", [], "test.pdf")
        system_content = messages[0]["content"]
        assert "not found in the uploaded document" in system_content.lower() or \
               "only" in system_content.lower()

    def test_user_message_contains_page_label(self):
        from backend.pipeline.prompt_builder import build_prompt
        from backend.pipeline.retriever import RetrievedChunk
        chunks = [
            RetrievedChunk(
                text="Some architecture text.", page_num=7,
                section="3.1 Overview", chunk_index=0,
                score=0.8, doc_id=TEST_DOC_ID, filename="sample_hld.pdf",
            )
        ]
        messages = build_prompt("What is covered in this section?", chunks)
        user_content = messages[1]["content"]
        assert "[Page 7" in user_content, "Expected page label in user message"

    def test_user_message_contains_question(self):
        from backend.pipeline.prompt_builder import build_prompt
        question = "What interfaces does the PowerControl SWC require?"
        messages = build_prompt(question, [])
        assert question in messages[1]["content"]

    def test_empty_chunks_handled_gracefully(self):
        from backend.pipeline.prompt_builder import build_prompt
        messages = build_prompt("any question", [])
        assert len(messages) == 2
        assert "no relevant excerpts" in messages[1]["content"].lower()


# ── RAG integration tests (LLM mocked) ───────────────────────────────────────

class TestRAGPipeline:
    """
    Full RAG flow tests with the LLM client mocked.
    These tests verify retrieve → prompt → citation assembly
    without requiring Ollama to be running.
    """

    MOCK_ANSWER = (
        "The BatteryManagement SWC has two provider ports: "
        "BattVoltage_Prov (BattVoltage_If) and BattSOC_Prov (BattSOC_If). "
        "It also has one required port: BattTemp_Req (TempSensor_If). (Page 4)"
    )

    def test_ask_returns_rag_answer(self, ingested_doc):
        from backend.pipeline.rag import ask, RAGAnswer
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.return_value = (self.MOCK_ANSWER, "ollama/llama3.2:3b")
            result = ask(TEST_DOC_ID, "What are the ports of BatteryManagement?")
        assert isinstance(result, RAGAnswer)
        assert result.answer == self.MOCK_ANSWER
        assert result.doc_id == TEST_DOC_ID
        assert "ollama" in result.model

    def test_ask_returns_citations(self, ingested_doc):
        from backend.pipeline.rag import ask
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.return_value = (self.MOCK_ANSWER, "ollama/llama3.2:3b")
            result = ask(TEST_DOC_ID, "What are the ports of BatteryManagement?")
        assert len(result.sources) > 0, "Expected at least one source citation"

    def test_citations_have_valid_page_numbers(self, ingested_doc):
        from backend.pipeline.rag import ask
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.return_value = (self.MOCK_ANSWER, "ollama/llama3.2:3b")
            result = ask(TEST_DOC_ID, "BatteryManagement SWC ports")
        for src in result.sources:
            assert src.page >= 1, f"Citation has invalid page: {src.page}"

    def test_citations_have_excerpt_text(self, ingested_doc):
        from backend.pipeline.rag import ask
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.return_value = (self.MOCK_ANSWER, "ollama/llama3.2:3b")
            result = ask(TEST_DOC_ID, "interface definitions")
        for src in result.sources:
            assert src.excerpt.strip(), "Citation excerpt should not be empty"

    def test_citations_deduplicated_by_page(self, ingested_doc):
        from backend.pipeline.rag import ask
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.return_value = (self.MOCK_ANSWER, "ollama/llama3.2:3b")
            result = ask(TEST_DOC_ID, "software components")
        pages = [s.page for s in result.sources]
        assert len(pages) == len(set(pages)), "Duplicate page numbers in citations"

    def test_query_saved_to_sqlite(self, ingested_doc):
        from backend.pipeline.rag import ask
        from backend.database.sqlite_db import get_query_history
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.return_value = (self.MOCK_ANSWER, "ollama/llama3.2:3b")
            ask(TEST_DOC_ID, "What signals are in the signal list?")
        history = get_query_history(TEST_DOC_ID)
        questions = [h["question"] for h in history]
        assert "What signals are in the signal list?" in questions

    def test_invalid_doc_id_raises(self):
        from backend.pipeline.rag import ask
        with pytest.raises(ValueError, match="not found"):
            ask("nonexistent_doc_id_xyz", "test question")

    def test_llm_connection_error_propagates(self, ingested_doc):
        from backend.pipeline.rag import ask
        with patch("backend.pipeline.rag.llm_client.generate") as mock_llm:
            mock_llm.side_effect = ConnectionError("Ollama not reachable")
            with pytest.raises(ConnectionError):
                ask(TEST_DOC_ID, "What are the signal definitions?")

    def test_ask_stream_yields_events(self, ingested_doc):
        from backend.pipeline.rag import ask_stream
        with patch("backend.pipeline.rag.llm_client.stream_generate") as mock_stream:
            mock_stream.return_value = iter([
                {"type": "token", "content": "The "},
                {"type": "token", "content": "BMS system."},
                {"type": "done", "model": "ollama/gemma3:4b", "full_text": "The BMS system."}
            ])
            events = list(ask_stream(TEST_DOC_ID, "What is the architecture?"))

        event_names = [line.split("event: ")[1].split("\n")[0] for line in events if line.startswith("event: ")]
        assert "sources" in event_names
        assert "token" in event_names
        assert "done" in event_names
