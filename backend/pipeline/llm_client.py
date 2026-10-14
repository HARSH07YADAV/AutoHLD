"""
llm_client.py — Abstraction layer for LLM inference.

Supports two backends, selected via the LLM_PROVIDER config value:
  - "ollama"  : Local Ollama server (default, no API key needed)
  - "openai"  : OpenAI API (requires OPENAI_API_KEY in .env)

The rest of the pipeline (rag.py) calls only `generate()` — it never
knows which backend is running. Switching providers is a one-line .env change.

Ollama API reference: https://github.com/ollama/ollama/blob/main/docs/api.md
OpenAI API reference: https://platform.openai.com/docs/api-reference/chat
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from backend.config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

def generate(messages: list[dict[str, str]]) -> tuple[str, str]:
    """
    Send a chat message list to the configured LLM and return the response.

    Parameters
    ----------
    messages : list[dict]
        Chat messages in OpenAI format: [{"role": "...", "content": "..."}, ...]
        The system message (if any) is the first element.

    Returns
    -------
    tuple[str, str]
        (answer_text, model_identifier)
        answer_text       — the LLM's response text
        model_identifier  — which model produced the answer (for UI display)
    """
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return _openai_generate(messages)
    else:
        return _ollama_generate(messages)


def is_ollama_available() -> bool:
    """
    Check if the Ollama server is reachable.

    Used by the health endpoint and the UI status indicator.
    """
    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Ollama backend ────────────────────────────────────────────────────────────

def _ollama_generate(messages: list[dict[str, str]]) -> tuple[str, str]:
    """
    Call the Ollama /api/chat endpoint (chat completion format).

    Ollama chat API accepts the same message format as OpenAI.
    Returns the assistant's response content.
    """
    url     = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": messages,
        "stream":   False,       # get the full response at once
        "options": {
            "temperature": 0.1,  # low temperature → precise, less creative
            "num_predict": 1024, # max tokens in the response
        },
    }

    logger.debug("Calling Ollama: model=%s, messages=%d", OLLAMA_MODEL, len(messages))

    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data    = data,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body   = resp.read().decode("utf-8")
            result = json.loads(body)

        answer = result.get("message", {}).get("content", "").strip()
        model  = result.get("model", OLLAMA_MODEL)

        if not answer:
            raise ValueError("Ollama returned an empty response.")

        logger.debug("Ollama response: %d chars, model=%s", len(answer), model)
        return answer, f"ollama/{model}"

    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running: `ollama serve`"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON: {exc}") from exc


# ── OpenAI backend ────────────────────────────────────────────────────────────

def _openai_generate(messages: list[dict[str, str]]) -> tuple[str, str]:
    """
    Call the OpenAI /v1/chat/completions endpoint.

    Used as a fallback when OPENAI_API_KEY is set in .env.
    """
    url     = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model":       OPENAI_MODEL,
        "messages":    messages,
        "temperature": 0.1,
        "max_tokens":  1024,
    }

    logger.debug("Calling OpenAI: model=%s", OPENAI_MODEL)

    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data    = data,
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body   = resp.read().decode("utf-8")
            result = json.loads(body)

        answer = result["choices"][0]["message"]["content"].strip()
        model  = result.get("model", OPENAI_MODEL)

        logger.debug("OpenAI response: %d chars, model=%s", len(answer), model)
        return answer, f"openai/{model}"

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"OpenAI API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot reach OpenAI API: {exc}") from exc
