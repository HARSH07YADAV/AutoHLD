"""
text_utils.py — Text cleaning and structural analysis helpers.
"""

import re
from backend.config import AUTOSAR_KEYWORDS


# ── Heading detection ─────────────────────────────────────────────────────────

# Patterns that strongly suggest a line is a section heading:
# e.g. "3.2 BatteryManagement Software Component"
#      "4.1.3 Port Definitions"
#      "OVERVIEW", "INTERFACE DESCRIPTION"
_NUMBERED_HEADING = re.compile(
    r"^\s*(\d+\.)+\d*\s+[A-Z][A-Za-z0-9\s\-_/()]{3,80}$"
)
_ALLCAPS_HEADING = re.compile(
    r"^\s*[A-Z][A-Z0-9\s\-_/]{4,60}$"
)

def is_likely_heading(line: str, font_size: float | None = None) -> bool:
    """
    Heuristically decide whether a line of text is a section heading.

    Uses numbered pattern, all-caps pattern, and optional font-size hint
    from pdfplumber (a larger-than-body font size strongly suggests a heading).
    """
    line = line.strip()
    if not line or len(line) > 120:
        return False
    if font_size is not None and font_size >= 13.0:
        return True
    if _NUMBERED_HEADING.match(line):
        return True
    if _ALLCAPS_HEADING.match(line):
        return True
    return False


# ── AUTOSAR keyword detection ─────────────────────────────────────────────────

def contains_autosar_keyword(text: str) -> bool:
    """Return True if the text contains at least one known AUTOSAR keyword."""
    for kw in AUTOSAR_KEYWORDS:
        if kw in text:
            return True
    return False


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Normalise whitespace in extracted PDF text.

    pdfplumber sometimes produces double spaces, stray newlines inside
    sentences, or unicode ligatures. This function corrects the most common
    issues without stripping meaningful content.
    """
    # Replace unicode ligatures (ﬁ, ﬂ, etc.)
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")

    # Collapse runs of whitespace within a line
    text = re.sub(r"[ \t]+", " ", text)

    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove lines that are pure whitespace
    lines = [ln.rstrip() for ln in text.split("\n")]
    text  = "\n".join(lines)

    # Collapse more than two consecutive blank lines into two
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ── Rough token estimator ─────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """
    Return a rough token count (1 token ≈ 4 characters).

    Used to reason about chunk sizes without importing a full tokeniser.
    """
    return max(1, len(text) // 4)


# ── Table formatting ──────────────────────────────────────────────────────────

def table_to_text(table: list[list[str | None]]) -> str:
    """
    Convert a pdfplumber table (list of rows, each a list of cell strings)
    into a compact plain-text representation.

    None cells (merged cells in the source PDF) are replaced with empty strings.
    """
    if not table:
        return ""

    rows = []
    for row in table:
        cells = [str(cell).strip() if cell is not None else "" for cell in row]
        rows.append(" | ".join(cells))

    return "\n".join(rows)
