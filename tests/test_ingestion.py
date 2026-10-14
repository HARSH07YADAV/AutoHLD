"""
test_ingestion.py — Integration tests for the Phase 1 ingestion pipeline.

Tests the full chain: PDF parsing → chunking → embedding → ChromaDB storage.
Runs against the sample_hld.pdf in demo/sample_docs/.

Run with:
    pytest tests/test_ingestion.py -v
"""

import pytest
from pathlib import Path

SAMPLE_PDF = Path(__file__).parent.parent / "demo" / "sample_docs" / "sample_hld.pdf"


# ── Prerequisites check ───────────────────────────────────────────────────────

def test_sample_pdf_exists():
    """The sample PDF must exist before any other test can run."""
    assert SAMPLE_PDF.exists(), (
        f"Sample PDF not found at {SAMPLE_PDF}. "
        "Run: python demo/generate_sample_pdf.py"
    )


# ── DocProcessor tests ────────────────────────────────────────────────────────

class TestDocProcessor:
    def test_process_returns_document_content(self):
        from backend.pipeline.doc_processor import process_pdf, DocumentContent
        result = process_pdf(SAMPLE_PDF)
        assert isinstance(result, DocumentContent)

    def test_page_count(self):
        from backend.pipeline.doc_processor import process_pdf
        result = process_pdf(SAMPLE_PDF)
        assert result.total_pages >= 5, "Expected at least 5 pages in the sample PDF"

    def test_page_numbers_are_sequential_and_one_indexed(self):
        from backend.pipeline.doc_processor import process_pdf
        result = process_pdf(SAMPLE_PDF)
        for i, page in enumerate(result.pages, start=1):
            assert page.page_num == i, f"Page at index {i} has page_num={page.page_num}"

    def test_non_empty_pages_have_text(self):
        from backend.pipeline.doc_processor import process_pdf
        result = process_pdf(SAMPLE_PDF)
        for page in result.non_empty_pages:
            assert page.full_text().strip(), f"Page {page.page_num} is non-empty but full_text() is blank"

    def test_headings_detected(self):
        from backend.pipeline.doc_processor import process_pdf
        result = process_pdf(SAMPLE_PDF)
        all_headings = [h for p in result.pages for h in p.headings]
        assert len(all_headings) > 0, "Expected at least one heading to be detected"

    def test_tables_extracted(self):
        from backend.pipeline.doc_processor import process_pdf
        result = process_pdf(SAMPLE_PDF)
        pages_with_tables = [p for p in result.pages if p.tables]
        assert len(pages_with_tables) > 0, "Expected at least one page with a table"

    def test_autosar_content_flagged(self):
        from backend.pipeline.doc_processor import process_pdf
        result = process_pdf(SAMPLE_PDF)
        autosar_pages = [p for p in result.pages if p.has_autosar_content]
        assert len(autosar_pages) > 0, "Expected AUTOSAR content to be detected on at least one page"

    def test_raises_on_missing_file(self):
        from backend.pipeline.doc_processor import process_pdf
        with pytest.raises(FileNotFoundError):
            process_pdf(Path("/tmp/nonexistent_file.pdf"))


# ── Chunker tests ─────────────────────────────────────────────────────────────

class TestChunker:
    @pytest.fixture(scope="class")
    def doc_content(self):
        from backend.pipeline.doc_processor import process_pdf
        return process_pdf(SAMPLE_PDF)

    def test_produces_chunks(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        chunks = chunk_document(doc_content, "test_doc_001")
        assert len(chunks) > 0, "Expected at least one chunk"

    def test_every_chunk_has_page_num(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        chunks = chunk_document(doc_content, "test_doc_001")
        for chunk in chunks:
            assert chunk.page_num >= 1, f"Chunk {chunk.chunk_id} has invalid page_num={chunk.page_num}"

    def test_every_chunk_has_doc_id(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        chunks = chunk_document(doc_content, "test_doc_001")
        for chunk in chunks:
            assert chunk.doc_id == "test_doc_001"

    def test_chunk_ids_are_unique(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        chunks = chunk_document(doc_content, "test_doc_001")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"

    def test_chunk_text_not_empty(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        chunks = chunk_document(doc_content, "test_doc_001")
        for chunk in chunks:
            assert chunk.text.strip(), f"Chunk {chunk.chunk_id} has empty text"

    def test_chunk_size_within_limit(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        from backend.config import CHUNK_SIZE_CHARS
        chunks = chunk_document(doc_content, "test_doc_001")
        # Allow 10% slack for sentence-boundary adjustments
        max_allowed = int(CHUNK_SIZE_CHARS * 1.1)
        for chunk in chunks:
            assert len(chunk.text) <= max_allowed, (
                f"Chunk {chunk.chunk_id} is too large: {len(chunk.text)} chars"
            )

    def test_section_preserved(self, doc_content):
        from backend.pipeline.chunker import chunk_document
        chunks = chunk_document(doc_content, "test_doc_001")
        # At least some chunks should have a non-empty section
        sections = [c.section for c in chunks if c.section]
        assert len(sections) > 0, "Expected at least some chunks to carry a section heading"


# ── Embedder tests ────────────────────────────────────────────────────────────

class TestEmbedder:
    def test_embed_query_returns_correct_dimension(self):
        from backend.pipeline.embedder import embed_query, get_embedding_dimension
        vector = embed_query("What are the provider ports of the BatteryManagement SWC?")
        assert isinstance(vector, list)
        assert len(vector) == get_embedding_dimension()

    def test_embed_query_values_are_floats(self):
        from backend.pipeline.embedder import embed_query
        vector = embed_query("test query")
        assert all(isinstance(v, float) for v in vector)


# ── Full ingestion pipeline test ──────────────────────────────────────────────

class TestFullIngestion:
    """
    End-to-end test: parse → chunk → embed → store → verify in ChromaDB.
    Uses a unique doc_id to avoid polluting any real data.
    """
    TEST_DOC_ID = "pytest_ingestion_test"

    def test_full_pipeline_stores_chunks(self):
        from backend.pipeline.doc_processor import process_pdf
        from backend.pipeline.chunker import chunk_document
        from backend.pipeline.embedder import embed_and_store
        from backend.database.vector_db import collection_count, delete_document_chunks

        # Clean up any previous test run
        delete_document_chunks(self.TEST_DOC_ID)

        doc   = process_pdf(SAMPLE_PDF)
        chunks = chunk_document(doc, self.TEST_DOC_ID)
        stored = embed_and_store(chunks)

        assert stored > 0, "Expected chunks to be stored"
        count = collection_count(self.TEST_DOC_ID)
        assert count == stored, f"ChromaDB count ({count}) != stored ({stored})"

    def test_retrieval_returns_results(self):
        from backend.pipeline.embedder import embed_query
        from backend.database.vector_db import query_chunks

        query_vec = embed_query("What are the provider ports of the BatteryManagement SWC?")
        results   = query_chunks(query_vec, self.TEST_DOC_ID, n_results=3)

        assert len(results) > 0, "Expected at least one result"
        for r in results:
            assert "text"     in r
            assert "metadata" in r
            assert "score"    in r
            assert r["metadata"]["page_num"] >= 1
            assert 0.0 <= r["score"] <= 1.0

    def test_cleanup(self):
        """Remove the test data after tests complete."""
        from backend.database.vector_db import delete_document_chunks, collection_count
        delete_document_chunks(self.TEST_DOC_ID)
        assert collection_count(self.TEST_DOC_ID) == 0
