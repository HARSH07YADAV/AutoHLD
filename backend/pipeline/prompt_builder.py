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
_SYSTEM_PROMPT = """You are the AutoHLD Technical Q&A Assistant, an automotive systems engineering expert embedded in an AUTOSAR design review platform.

Your mission is to answer engineering questions accurately, concisely, and directly using ONLY the evidence present in the provided document excerpts.

CONCISE ENGINEERING INSTRUCTIONS:
1. Grounding & Evidence:
   - Answer using ONLY facts and architecture in the provided excerpts. Do NOT invent technical data, port names, or specifications not in the excerpts.
   - If the excerpts contain no relevant evidence whatsoever about the asked topic, respond strictly with:
     "This information was not found in the selected document."

2. Concise, Focused Answers:
   - Answer ONLY the specific question asked. Do not dump unrequested background sections or essay introductions.
   - Keep answers direct, concise, and technical (target: 100–250 words using clean bullet points or short paragraphs).
   - Eliminate repetition: state each specification or fact exactly once.

3. Technical Precision:
   - Give exact component names, port directions (P-Port / R-Port), interface names, signals, and ASIL ratings as documented.

4. Page Citations:
   - Always cite source page numbers for every document-supported claim: (Page N) or (Pages N, M).
"""


def _format_chunk(chunk: RetrievedChunk) -> str:
    """Format a single retrieved chunk as a labelled context block."""
    section_label = f" | Section: {chunk.section}" if chunk.section else ""
    header = f"[Page {chunk.page_num}{section_label}]"
    return f"{header}\n{chunk.text.strip()}"


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
        for i, c in enumerate(chunks, 1):
            numbered_blocks.append(f"--- Excerpt {i} ---\n{_format_chunk(c)}")

        context_header = (
            f"SOURCE SPECIFICATION: {doc_label}\n"
            f"Verified excerpt(s) retrieved from document:\n\n"
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
        f"{'─' * 50}\n"
        f"QUESTION: {question.strip()}\n\n"
        f"INSTRUCTION: Answer concisely and directly with exact technical details and page citations (Page N) from the excerpts above."
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
