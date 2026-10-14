"""
doc_processor.py — PDF parsing and page-level content extraction.

Responsibility: open a PDF file, walk through every page, extract text and
tables, detect section headings, and return a list of PageContent objects.

The page number is set here and never lost — it flows through every
downstream step (chunker → embedder → ChromaDB) so that citations in the
final answer always point back to the correct source page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from backend.utils.text_utils import (
    clean_text,
    is_likely_heading,
    table_to_text,
    contains_autosar_keyword,
)

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """
    All extracted content from a single PDF page.

    page_num is 1-indexed to match what engineers see in a PDF viewer.
    """
    page_num:  int
    text:      str                    # cleaned plain text of the page
    headings:  list[str]              = field(default_factory=list)
    tables:    list[str]              = field(default_factory=list)  # table → plain text
    is_empty:  bool                   = False
    has_autosar_content: bool         = False
    is_likely_scanned:   bool         = False   # True if page has images but no text (OCR needed)
    image_count:         int          = 0        # number of image objects on this page

    def full_text(self) -> str:
        """
        Return a single string that combines headings, body text, and table
        text for this page. This is what gets chunked and embedded.
        """
        parts = []
        if self.headings:
            parts.append("\n".join(self.headings))
        if self.text:
            parts.append(self.text)
        if self.tables:
            parts.append("\n\n".join(self.tables))
        return "\n\n".join(parts).strip()


@dataclass
class DocumentContent:
    """All pages extracted from one PDF file."""
    filename:    str
    total_pages: int
    pages:       list[PageContent] = field(default_factory=list)

    @property
    def non_empty_pages(self) -> list[PageContent]:
        return [p for p in self.pages if not p.is_empty]


# ── Public API ────────────────────────────────────────────────────────────────

def process_pdf(file_path: Path) -> DocumentContent:
    """
    Parse a PDF file and return a DocumentContent with one PageContent per page.

    Raises:
        FileNotFoundError: if file_path does not exist.
        ValueError: if the file cannot be opened as a PDF.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    logger.info("Processing PDF: %s", file_path.name)

    pages: list[PageContent] = []

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            total_pages = len(pdf.pages)
            logger.info("Total pages: %d", total_pages)

            for page_obj in pdf.pages:
                page_num = page_obj.page_number   # 1-indexed in pdfplumber

                try:
                    page_content = _extract_page(page_obj, page_num)
                    pages.append(page_content)
                except Exception as exc:
                    # Never let a single bad page abort the whole document
                    logger.warning("Could not extract page %d: %s", page_num, exc)
                    pages.append(
                        PageContent(
                            page_num=page_num,
                            text="",
                            is_empty=True,
                        )
                    )

    except Exception as exc:
        raise ValueError(f"Failed to open PDF '{file_path.name}': {exc}") from exc

    non_empty = sum(1 for p in pages if not p.is_empty)
    logger.info(
        "Extraction complete: %d/%d pages yielded content",
        non_empty,
        total_pages,
    )

    return DocumentContent(
        filename=file_path.name,
        total_pages=total_pages,
        pages=pages,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_page(page_obj: pdfplumber.page.Page, page_num: int) -> PageContent:
    """
    Extract all content from a single pdfplumber page object.

    Strategy:
    1. Extract tables first (before stripping bounding boxes).
    2. Extract remaining text outside table areas.
    3. Walk line by line to detect headings using font-size hints.
    4. Clean the text.
    5. Detect AUTOSAR keywords.
    """
    # ── Step 1: tables ────────────────────────────────────────────────────────
    raw_tables   = page_obj.extract_tables() or []
    table_texts: list[str] = []

    for tbl in raw_tables:
        converted = table_to_text(tbl)
        if converted.strip():
            table_texts.append(converted)

    # ── Step 2: main text ─────────────────────────────────────────────────────
    # Use extract_text with layout=False for cleaner linear reading order
    raw_text = page_obj.extract_text(x_tolerance=3, y_tolerance=3) or ""

    # ── Step 3: heading detection ─────────────────────────────────────────────
    headings: list[str] = []
    body_lines: list[str] = []

    # Try to get per-word font sizes for more accurate heading detection
    try:
        words_with_font = page_obj.extract_words(
            extra_attrs=["fontname", "size"], keep_blank_chars=False
        )
        # Group words into lines by their top-y position (within 2pt tolerance)
        line_map: dict[float, list] = {}
        for w in words_with_font:
            top = round(w["top"])
            line_map.setdefault(top, []).append(w)

        for top_y in sorted(line_map.keys()):
            words = line_map[top_y]
            line_text = " ".join(w["text"] for w in words).strip()
            if not line_text:
                continue
            # Use the max font size on the line as the heading hint
            sizes = [w.get("size") or 0 for w in words]
            max_size = max(sizes) if sizes else None
            if is_likely_heading(line_text, font_size=max_size):
                headings.append(line_text)
            else:
                body_lines.append(line_text)

        body_text = "\n".join(body_lines)

    except Exception:
        # Fallback: plain line-by-line without font info
        body_lines = []
        for line in raw_text.splitlines():
            if is_likely_heading(line):
                headings.append(line.strip())
            else:
                body_lines.append(line)
        body_text = "\n".join(body_lines)

    # ── Step 4: clean ─────────────────────────────────────────────────────────
    body_text = clean_text(body_text)

    # ── Step 5: AUTOSAR keyword flag ──────────────────────────────────────────
    full = body_text + " ".join(headings)
    has_autosar = contains_autosar_keyword(full)

    # ── Step 6: OCR / scanned page detection ──────────────────────────────────
    # Count image objects on this page using pdfplumber's image list.
    # If a page has images but zero extractable text, it is likely a scanned
    # or image-embedded page — pdfplumber cannot extract text from rasterised
    # content without an OCR layer (e.g. Tesseract).
    try:
        image_count = len(page_obj.images) if hasattr(page_obj, "images") else 0
    except Exception:
        image_count = 0

    is_text_empty = not body_text.strip() and not headings and not table_texts
    is_likely_scanned = (image_count > 0 and is_text_empty)

    if is_likely_scanned:
        logger.warning(
            "Page %d appears to be scanned/image-based (%d image(s), no text extracted). "
            "OCR (e.g. Tesseract) would be required to extract content from this page.",
            page_num, image_count,
        )

    # A page is considered empty if it has no body text, no headings, no tables
    is_empty = is_text_empty

    return PageContent(
        page_num             = page_num,
        text                 = body_text,
        headings             = headings,
        tables               = table_texts,
        is_empty             = is_empty,
        has_autosar_content  = has_autosar,
        is_likely_scanned    = is_likely_scanned,
        image_count          = image_count,
    )

