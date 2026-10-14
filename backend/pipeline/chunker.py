"""
chunker.py — Split extracted page content into overlapping text chunks.

Responsibility: receive a list of PageContent objects and produce a flat list
of Chunk objects. Every chunk carries its source page number and section
heading so that citations are always traceable.

Design decisions:
  - Chunking is character-based (not token-based) to avoid a heavy tokeniser
    dependency. At ~4 chars/token, CHUNK_SIZE_CHARS ≈ 450 tokens.
  - Overlap prevents sentences from being unrecoverably split at chunk edges.
  - The "current_section" variable tracks the last seen heading across pages.
    If page 12 starts a section called "3.2 BatteryManagement", all chunks
    from that page (and subsequent pages until the next heading) carry that
    section name.
  - AUTOSAR-specific: lines containing AUTOSAR keywords are never split mid-line.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from backend.config import CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS
from backend.pipeline.doc_processor import DocumentContent, PageContent
from backend.utils.text_utils import contains_autosar_keyword

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """
    A single text segment ready for embedding.

    All fields here are stored as ChromaDB metadata alongside the vector,
    guaranteeing that the source page is never lost.
    """
    chunk_id:    str          # e.g. "doc_abc123_chunk_047"
    doc_id:      str
    filename:    str
    text:        str          # the actual text that gets embedded
    page_num:    int          # 1-indexed source page — MUST always be set
    section:     str          # last seen section heading (may be empty)
    chunk_index: int          # sequential index within the document
    has_table:   bool = False
    char_count:  int  = 0

    def __post_init__(self):
        self.char_count = len(self.text)


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_document(doc_content: DocumentContent, doc_id: str) -> list[Chunk]:
    """
    Convert a DocumentContent (output of doc_processor) into a flat list of
    Chunk objects ready for embedding.

    Parameters
    ----------
    doc_content : DocumentContent
        The parsed document from process_pdf().
    doc_id : str
        The document identifier — stored in every chunk for filtering later.

    Returns
    -------
    list[Chunk]
        Ordered list of chunks. chunk_index is sequential across the whole doc.
    """
    chunks: list[Chunk] = []
    chunk_index = 0
    current_section = ""      # tracks the last known section heading

    for page in doc_content.pages:
        if page.is_empty:
            # Update section from headings even on otherwise empty pages
            if page.headings:
                current_section = page.headings[-1]
            continue

        # Update current section from this page's headings (if any)
        if page.headings:
            current_section = page.headings[-1]

        # Build the full text for this page
        page_text = page.full_text()
        if not page_text.strip():
            continue

        # Split the page's text into chunks
        page_chunks = _split_text(
            text          = page_text,
            page_num      = page.page_num,
            section       = current_section,
            has_table     = bool(page.tables),
            doc_id        = doc_id,
            filename      = doc_content.filename,
            start_index   = chunk_index,
        )

        chunks.extend(page_chunks)
        chunk_index += len(page_chunks)

    logger.info(
        "Chunked '%s' into %d chunks across %d non-empty pages.",
        doc_content.filename,
        len(chunks),
        len(doc_content.non_empty_pages),
    )
    return chunks


# ── Internal helpers ──────────────────────────────────────────────────────────

def _split_text(
    text:        str,
    page_num:    int,
    section:     str,
    has_table:   bool,
    doc_id:      str,
    filename:    str,
    start_index: int,
) -> list[Chunk]:
    """
    Split a block of text into overlapping character-level chunks.

    The algorithm walks through the text with a sliding window:
      - Each window is CHUNK_SIZE_CHARS wide.
      - The next window starts CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS from
        the start of the previous one (overlap).
      - Splits are made at the nearest sentence boundary (. ! ?) or newline
        within the last 15% of the window, so sentences are not cut mid-way.
      - AUTOSAR keyword lines are kept whole.
    """
    if not text.strip():
        return []

    chunks: list[Chunk] = []
    local_index = 0
    pos = 0

    while pos < len(text):
        # Determine raw end of this window
        end = min(pos + CHUNK_SIZE_CHARS, len(text))

        # If we haven't reached the end of the text, try to find a clean break
        if end < len(text):
            end = _find_break_point(text, pos, end)

        chunk_text = text[pos:end].strip()

        if chunk_text:
            chunk = Chunk(
                chunk_id    = f"{doc_id}_chunk_{start_index + local_index:04d}",
                doc_id      = doc_id,
                filename    = filename,
                text        = chunk_text,
                page_num    = page_num,
                section     = section,
                chunk_index = start_index + local_index,
                has_table   = has_table,
            )
            chunks.append(chunk)
            local_index += 1

        # Advance with overlap: step forward by (CHUNK_SIZE - OVERLAP)
        step = max(CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS, 100)
        pos += step

        # Stop if we're in the overlap zone near the end
        if pos >= len(text):
            break

    return chunks


def _find_break_point(text: str, start: int, proposed_end: int) -> int:
    """
    Find the nearest clean break point at or before proposed_end.

    Preference order:
    1. Paragraph break (\\n\\n) — highest quality split
    2. Sentence-ending punctuation followed by a space (. ! ?)
    3. Newline
    4. Space
    5. If none found within 15% of the window, use proposed_end as-is

    The search window is the last 15% of the chunk so we don't produce
    tiny fragments.
    """
    search_start = proposed_end - max(int(CHUNK_SIZE_CHARS * 0.15), 50)
    search_start = max(search_start, start)

    window = text[search_start:proposed_end]

    # 1. Paragraph break
    idx = window.rfind("\n\n")
    if idx != -1:
        return search_start + idx + 2

    # 2. Sentence-ending punctuation
    for punct in (". ", "! ", "? "):
        idx = window.rfind(punct)
        if idx != -1:
            return search_start + idx + 2

    # 3. Newline
    idx = window.rfind("\n")
    if idx != -1:
        return search_start + idx + 1

    # 4. Space
    idx = window.rfind(" ")
    if idx != -1:
        return search_start + idx + 1

    # 5. Hard cut
    return proposed_end
