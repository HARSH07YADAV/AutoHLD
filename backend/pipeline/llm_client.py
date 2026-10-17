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

    Tries the configured OLLAMA_BASE_URL first, then falls back to
    localhost:11434. This handles both Docker (http://ollama:11434)
    and host-native (http://localhost:11434) deployments.

    Used by the health endpoint and the UI status indicator.
    """
    _fallback = "http://localhost:11434"
    urls = [OLLAMA_BASE_URL]
    if "localhost" not in OLLAMA_BASE_URL and "127.0.0.1" not in OLLAMA_BASE_URL:
        urls.append(_fallback)

    for url in urls:
        try:
            req = urllib.request.Request(f"{url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            continue
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
            "num_predict": 2048, # max tokens in the response
        },
    }

    logger.debug("Calling Ollama: model=%s, messages=%d", OLLAMA_MODEL, len(messages))

    # Try primary URL, then fallback to localhost if the primary is a Docker hostname
    _FALLBACK_URL = "http://localhost:11434"
    urls_to_try = [url]
    if "localhost" not in url and "127.0.0.1" not in url:
        urls_to_try.append(url.replace(OLLAMA_BASE_URL, _FALLBACK_URL).replace(
            OLLAMA_BASE_URL.rstrip("/"), _FALLBACK_URL
        ))
        # Simpler approach: always add localhost fallback when not already localhost
        urls_to_try = [url, f"{_FALLBACK_URL}/api/chat"]

    last_exc: Exception | None = None
    for try_url in urls_to_try:
        try:
            data = json.dumps(payload).encode("utf-8")
            req  = urllib.request.Request(
                try_url,
                data    = data,
                headers = {"Content-Type": "application/json"},
                method  = "POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                body   = resp.read().decode("utf-8")
                result = json.loads(body)

            answer = result.get("message", {}).get("content", "").strip()
            model  = result.get("model", OLLAMA_MODEL)

            if not answer:
                raise ValueError("Ollama returned an empty response.")

            if try_url != url:
                logger.info("Used fallback Ollama URL: %s", try_url)
            logger.debug("Ollama response: %d chars, model=%s", len(answer), model)
            return answer, f"ollama/{model}"

        except urllib.error.HTTPError as exc:
            # Ollama returns HTTP 500 with an error body when model is not found
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            if exc.code == 404 or "not found" in err_body.lower() or "pull" in err_body.lower():
                raise ConnectionError(
                    f"Ollama model '{OLLAMA_MODEL}' is not available. "
                    f"Run: `ollama pull {OLLAMA_MODEL}` — or update OLLAMA_MODEL in .env."
                ) from exc
            last_exc = exc
            logger.debug("Ollama HTTP %d at %s: %s — trying next.", exc.code, try_url, err_body[:200])
            continue
        except urllib.error.URLError as exc:
            reason = str(exc.reason) if hasattr(exc, 'reason') else str(exc)
            if 'timed out' in reason.lower() or 'timeout' in reason.lower():
                raise ConnectionError(
                    f"Ollama request timed out after 300 s. "
                    "The model may be too slow — try a smaller model like qwen2.5:1.5b."
                ) from exc
            last_exc = exc
            logger.debug("Ollama URL %s failed: %s — trying next.", try_url, exc)
            continue
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ollama returned invalid JSON: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error calling Ollama at %s: %s", try_url, exc)
            raise ValueError(f"Ollama inference error: {exc}") from exc

    # All URLs failed
    raise ConnectionError(
        f"Cannot reach Ollama at {OLLAMA_BASE_URL} or {_FALLBACK_URL}. "
        "Make sure Ollama is running: `ollama serve`"
    ) from last_exc


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
