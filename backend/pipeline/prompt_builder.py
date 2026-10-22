"""
prompt_builder.py — Assemble grounded, multi-excerpt prompts for AutoHLD.

Responsibilities:
  1. Provide an engineering persona prompt that strictly grounds answers in document excerpts.
  2. Prevent false refusals: instruct the model to synthesize answers across multiple excerpts
     and handle natural-language summaries, synonyms, and partial coverage gracefully.
  3. Enforce accurate page-level citations: (Page N) or (Pages N, M).
  4. Ensure clean, structured output without duplicate points or boilerplate repetitions.
  5. Distinguish document-verified facts from genuine information gaps.
"""

from __future__ import annotations

from backend.pipeline.retriever import RetrievedChunk

# ── System prompt ─────────────────────────────────────────────────────────────
# Kept concise to minimize prompt-eval time on CPU inference.
# Every 100 tokens saved ≈ 40ms saved on prompt evaluation.
_SYSTEM_PROMPT = """You are AutoHLD, an automotive engineering assistant embedded in an AUTOSAR design review platform. Answer engineering questions using ONLY the provided document excerpts.

Rules:
1. Answer using ONLY facts present in the excerpts. Do NOT invent data, port names, or specs.
2. If the excerpts contain no relevant evidence, respond with: "This information was not found in the selected document."
3. Be concise and direct (target 80–200 words). Use bullet points for lists. State each fact once.
4. Give exact names, port directions (P-Port/R-Port), signals, and ASIL ratings as documented.
5. Cite page numbers for every claim: (Page N) or (Pages N, M)."""


def _format_chunk(chunk: RetrievedChunk) -> str:
    """Format a single retrieved chunk as a labelled context block."""
    section_label = f" | Section: {chunk.section}" if chunk.section else ""
    header = f"[Page {chunk.page_num}{section_label}]"
    return f"{header}\n{chunk.text.strip()}"


def _format_chunk_text(chunk: RetrievedChunk, text: str) -> str:
    """Format a chunk with an explicit (possibly trimmed) text string."""
    section_label = f" | Section: {chunk.section}" if chunk.section else ""
    header = f"[Page {chunk.page_num}{section_label}]"
    return f"{header}\n{text}"


# ── Public API ────────────────────────────────────────────────────────────────

def build_prompt(
    question:  str,
    chunks:    list[RetrievedChunk],
    filename:  str = "",
) -> list[dict[str, str]]:
    """
    Build the message list for the LLM.

    Returns a list of role/content dicts compatible with both Ollama
    and OpenAI chat completion APIs:
        [
            {"role": "system",  "content": "..."},
            {"role": "user",    "content": "..."},
        ]
    """
    if chunks:
        doc_label = f'"{filename}"' if filename else "the uploaded document"
        numbered_blocks = []
        # Cap each chunk text at 900 chars to prevent oversized prompts
        for i, c in enumerate(chunks, 1):
            chunk_text = c.text.strip()
            if len(chunk_text) > 900:
                chunk_text = chunk_text[:900] + "…"
            numbered_blocks.append(f"--- Excerpt {i} ---\n{_format_chunk_text(c, chunk_text)}")

        context_header = (
            f"SOURCE SPECIFICATION: {doc_label}\n"
            f"Verified excerpt(s) from document:\n\n"
        )
        context_blocks = "\n\n".join(numbered_blocks)
        context_section = context_header + context_blocks
    else:
        context_section = (
            "No relevant excerpts were found in the document for this question. "
            'You MUST respond with: "This information was not found in the selected document."'
        )

    user_content = (
        f"{context_section}\n\n"
        f"{'─' * 40}\n"
        f"QUESTION: {question.strip()}\n\n"
        f"INSTRUCTION: Answer concisely with exact technical details and page citations (Page N)."
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]


def build_no_doc_prompt(question: str) -> list[dict[str, str]]:
    """Fallback prompt used when no document is selected."""
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"QUESTION: {question.strip()}\n\n"
                "Note: No document has been uploaded or selected."
            ),
        },
    ]
