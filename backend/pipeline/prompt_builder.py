"""
prompt_builder.py — Assemble the final prompt sent to the LLM.

Responsibility:
  Combine the system instruction, retrieved document chunks (as grounded
  context), and the user's question into a single prompt string.

Design rules enforced here:
  1. The LLM is explicitly instructed to answer ONLY from the provided context.
  2. If the answer is not in the context, it must say so — no invention.
  3. Every piece of context is labelled with [Page N | Section: X] so the LLM
     can reference page numbers accurately in its answer.
  4. The system prompt never leaks implementation details to the user.
  5. Answers must be concise and engineering-focused.
"""

from __future__ import annotations

from backend.pipeline.retriever import RetrievedChunk

# ── System prompt ─────────────────────────────────────────────────────────────
# This is the engineering persona instruction sent as the system/context role.
# It is never shown to the user in the UI.

_SYSTEM_PROMPT = """You are an AUTOSAR architecture analysis assistant embedded in an engineering document review tool.

Your role is to answer questions about the AUTOSAR High-Level Design (HLD) document that has been uploaded by the engineer.

STRICT RULES:
1. Answer ONLY using information present in the document excerpts provided below.
2. If the answer cannot be found in the excerpts, respond with exactly:
   "The information was not found in the uploaded document."
3. Do not use any knowledge from your training data about AUTOSAR, automotive systems, or software architecture unless it is directly confirmed by the document excerpts.
4. Always cite the page number when you reference specific information. Format citations as: (Page N) or (Pages N, M).
5. Be precise and technical. Use the exact component names, port names, interface names, and signal names as they appear in the document.
6. Keep answers concise. Do not pad with unnecessary explanation.
7. Do not speculate or infer beyond what the document states.
8. If asked about something partially covered, answer only the part that is covered and note what is missing.
"""

# ── Context block template ────────────────────────────────────────────────────

def _format_chunk(chunk: RetrievedChunk) -> str:
    """
    Format a single retrieved chunk as a labelled context block.

    Example output:
        [Page 12 | Section: 2.1 BatteryManagement SWC]
        The BatteryManagement SWC provides voltage monitoring via BattV_Prov...
    """
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

    Returns a list of role/content dicts compatible with both the Ollama
    and OpenAI chat completion APIs:
        [
            {"role": "system",  "content": "..."},
            {"role": "user",    "content": "..."},
        ]

    Parameters
    ----------
    question : str
        The engineer's natural language question.
    chunks : list[RetrievedChunk]
        Top-k chunks from the retriever, ordered by relevance.
    filename : str
        Original document filename, used as a label in the context header.

    Returns
    -------
    list[dict]
        Chat message list ready to send to the LLM client.
    """
    # Build the context section from retrieved chunks
    if chunks:
        doc_label = f'Document: "{filename}"' if filename else "the uploaded document"
        context_header = (
            f"The following excerpts are from {doc_label}. "
            f"Use ONLY these excerpts to answer the question.\n\n"
            f"{'─' * 60}\n"
        )
        context_blocks = "\n\n".join(_format_chunk(c) for c in chunks)
        context_section = context_header + context_blocks
    else:
        # No chunks retrieved — the LLM should still respond appropriately
        context_section = (
            "No relevant excerpts were found in the document for this question."
        )

    user_content = (
        f"{context_section}\n\n"
        f"{'─' * 60}\n"
        f"QUESTION: {question.strip()}"
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]


def build_no_doc_prompt(question: str) -> list[dict[str, str]]:
    """
    Fallback prompt used when no document is selected.
    Returns a polite refusal rather than answering from training data.
    """
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
