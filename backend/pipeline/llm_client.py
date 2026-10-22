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

import os
from typing import Generator

logger = logging.getLogger(__name__)


_cached_working_model: str | None = None


def _get_all_installed_models(base_url: str) -> list[str]:
    """Query /api/tags and return a list of model names installed on the Ollama instance."""
    try:
        tag_url = f"{base_url.rstrip('/')}/api/tags"
        req = urllib.request.Request(tag_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", []) if "name" in m]
    except Exception:
        return []


def get_effective_model(base_url: str) -> str:
    """Return the confirmed available model name, avoiding 404 retries on every question."""
    global _cached_working_model
    if _cached_working_model:
        return _cached_working_model

    installed = _get_all_installed_models(base_url)
    if not installed:
        _cached_working_model = OLLAMA_MODEL
        return _cached_working_model

    # Check exact match
    if OLLAMA_MODEL in installed:
        _cached_working_model = OLLAMA_MODEL
        return _cached_working_model

    # Check prefix match (e.g., "gemma3:4b" vs "gemma3")
    configured_prefix = OLLAMA_MODEL.split(":")[0]
    for m in installed:
        if m.startswith(configured_prefix):
            _cached_working_model = m
            return _cached_working_model

    # Fall back to first available installed model
    _cached_working_model = installed[0]
    logger.info(
        "Auto-selected installed Ollama model '%s' (configured: '%s')",
        _cached_working_model, OLLAMA_MODEL
    )
    return _cached_working_model


def _get_ollama_options() -> dict:
    """
    Return tuned Ollama options to minimize prompt eval time and latency.

    Key tuning decisions:
    - num_ctx=1536: Smaller KV-cache = 30-40% faster prompt evaluation vs 2048.
      Our RAG prompts (system + 3 chunks + question) fit comfortably within 1536 tokens.
    - num_predict=300: Keeps answers concise; 300 tokens ≈ 220 words, sufficient for
      technical Q&A. Prevents runaway generation.
    - keep_alive: Set at call-site to -1 (infinite) so Ollama never unloads the model.
    - repeat_last_n=32: Smaller sliding window for repeat detection; faster than 64.
    - num_thread: Use all logical cores up to 12 for CPU inference.
    """
    cpu_count = os.cpu_count() or 4
    return {
        "temperature":    0.1,    # precise technical answers
        "num_ctx":        1536,   # 1536 < 2048 → ~35% faster prompt eval; fits RAG prompts
        "num_predict":    300,    # 300 tokens ≈ 220 words; concise technical answers
        "repeat_penalty": 1.1,    # mild repetition penalty
        "repeat_last_n":  32,     # smaller window = faster per-token repeat check
        "num_thread":     min(12, max(4, cpu_count)),  # use more threads on 16-core CPU
    }


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


def stream_generate(messages: list[dict[str, str]]) -> Generator[dict, None, None]:
    """
    Stream tokens from the configured LLM one by one as they are generated.

    Yields dicts of:
      {"type": "token", "content": "..."}
      {"type": "done", "model": "...", "full_text": "..."}
    """
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        yield from _openai_stream(messages)
    else:
        yield from _ollama_stream(messages)


def warm_up_llm() -> None:
    """
    Pre-warm the local Ollama LLM so model weights are loaded in RAM before the first request.

    Uses the /api/chat endpoint (same as production code) with keep_alive=-1 so the model
    stays resident indefinitely and is never unloaded between requests. This eliminates the
    8-9s cold-start penalty on the first user query.
    """
    if LLM_PROVIDER == "openai":
        return
    try:
        base = OLLAMA_BASE_URL.rstrip('/')
        model_to_warm = get_effective_model(base)
        url = f"{base}/api/chat"
        # Use /api/chat (same path as production) so the same KV-cache slot is reused.
        # keep_alive=-1 means the model stays in memory indefinitely (until Ollama is restarted).
        payload = {
            "model": model_to_warm,
            "messages": [{"role": "user", "content": "AUTOSAR"}],
            "stream":   False,
            "keep_alive": -1,          # never unload: eliminates cold-start on every request
            "options": {
                "num_predict": 2,      # minimal generation; just enough to load weights
                "num_ctx":     512,    # tiny context for warm-up; fast to evaluate
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        logger.info("Ollama model '%s' pre-warmed successfully (keep_alive=-1).", model_to_warm)
    except Exception as exc:
        logger.warning("Ollama warm-up failed (model will cold-start on first request): %s", exc)


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


def _get_first_available_model(base_url: str) -> str | None:
    """Query Ollama /api/tags and return the first installed model name, or None."""
    models = _get_all_installed_models(base_url)
    return models[0] if models else None


def _ollama_generate(messages: list[dict[str, str]]) -> tuple[str, str]:
    """
    Call the Ollama /api/chat endpoint (chat completion format).

    Ollama chat API accepts the same message format as OpenAI.
    Returns the assistant's response content.
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    _FALLBACK_URL = "http://localhost:11434"
    urls_to_try = [url]
    if "localhost" not in url and "127.0.0.1" not in url:
        urls_to_try.append(f"{_FALLBACK_URL}/api/chat")

    effective_model = get_effective_model(urls_to_try[0].split("/api")[0])
    payload = {
        "model":      effective_model,
        "messages":   messages,
        "stream":     False,
        "keep_alive": -1,            # never unload; warm-up guarantees model is resident
        "options":    _get_ollama_options(),
    }

    logger.debug("Calling Ollama: model=%s, messages=%d", effective_model, len(messages))

    last_exc: Exception | None = None
    for try_url in urls_to_try:
        try:
            base_url = try_url.split("/api")[0]
            payload["model"] = get_effective_model(base_url)
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
            model  = result.get("model", payload["model"])

            if not answer:
                raise ValueError("Ollama returned an empty response.")

            if try_url != url:
                logger.info("Used fallback Ollama URL: %s", try_url)
            logger.debug("Ollama response: %d chars, model=%s", len(answer), model)
            return answer, f"ollama/{model}"

        except urllib.error.HTTPError as exc:
            # Ollama returns HTTP 404 or 500 with an error body when model is not found
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            if exc.code == 404 or "not found" in err_body.lower() or "pull" in err_body.lower():
                # Attempt automatic discovery of available installed model
                available = _get_first_available_model(try_url.split("/api")[0])
                if available and available != payload["model"]:
                    logger.warning("Configured model '%s' not found. Auto-switching to available model '%s'", payload["model"], available)
                    payload["model"] = available
                    try:
                        data = json.dumps(payload).encode("utf-8")
                        retry_req = urllib.request.Request(
                            try_url,
                            data    = data,
                            headers = {"Content-Type": "application/json"},
                            method  = "POST",
                        )
                        with urllib.request.urlopen(retry_req, timeout=300) as resp:
                            body = resp.read().decode("utf-8")
                            result = json.loads(body)
                        ans = result.get("message", {}).get("content", "").strip()
                        if ans:
                            return ans, f"ollama/{available}"
                    except Exception as retry_err:
                        logger.debug("Auto-switch retry failed: %s", retry_err)

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


def _ollama_stream(messages: list[dict[str, str]]) -> Generator[dict, None, None]:
    """
    Stream tokens from Ollama using line-delimited JSON.
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    _FALLBACK_URL = "http://localhost:11434"
    urls_to_try = [url]
    if "localhost" not in url and "127.0.0.1" not in url:
        urls_to_try.append(f"{_FALLBACK_URL}/api/chat")

    effective_model = get_effective_model(urls_to_try[0].split("/api")[0])
    payload = {
        "model":      effective_model,
        "messages":   messages,
        "stream":     True,
        "keep_alive": -1,            # never unload; eliminates 8-9s cold-start penalty
        "options":    _get_ollama_options(),
    }

    last_exc: Exception | None = None
    for try_url in urls_to_try:
        try:
            base_url = try_url.split("/api")[0]
            payload["model"] = get_effective_model(base_url)
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                try_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            full_text = []
            final_model = payload["model"]

            with urllib.request.urlopen(req, timeout=180) as resp:
                for line in resp:
                    if not line:
                        continue
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    try:
                        chunk_obj = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue

                    if "model" in chunk_obj:
                        final_model = chunk_obj["model"]

                    content = chunk_obj.get("message", {}).get("content", "")
                    if content:
                        full_text.append(content)
                        yield {"type": "token", "content": content}

                    if chunk_obj.get("done", False):
                        break

            full_answer = "".join(full_text).strip()
            yield {
                "type": "done",
                "model": f"ollama/{final_model}",
                "full_text": full_answer,
            }
            return

        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            if exc.code == 404 or "not found" in err_body.lower() or "pull" in err_body.lower():
                available = _get_first_available_model(try_url.split("/api")[0])
                if available and available != payload["model"]:
                    logger.warning("Configured model '%s' not found. Retrying stream with '%s'", payload["model"], available)
                    payload["model"] = available
                    try:
                        data = json.dumps(payload).encode("utf-8")
                        retry_req = urllib.request.Request(
                            try_url,
                            data=data,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        full_text = []
                        with urllib.request.urlopen(retry_req, timeout=180) as retry_resp:
                            for line in retry_resp:
                                if not line:
                                    continue
                                line_str = line.decode("utf-8").strip()
                                if not line_str:
                                    continue
                                try:
                                    chunk_obj = json.loads(line_str)
                                except json.JSONDecodeError:
                                    continue
                                content = chunk_obj.get("message", {}).get("content", "")
                                if content:
                                    full_text.append(content)
                                    yield {"type": "token", "content": content}
                                if chunk_obj.get("done", False):
                                    break
                        yield {
                            "type": "done",
                            "model": f"ollama/{available}",
                            "full_text": "".join(full_text).strip(),
                        }
                        return
                    except Exception as retry_err:
                        logger.debug("Auto-switch retry stream failed: %s", retry_err)

                raise ConnectionError(
                    f"Ollama model '{OLLAMA_MODEL}' is not available. "
                    f"Run: `ollama pull {OLLAMA_MODEL}` or update OLLAMA_MODEL in .env."
                ) from exc
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            logger.warning("Ollama stream error at %s: %s", try_url, exc)
            continue

    raise ConnectionError(
        f"Cannot connect to Ollama for streaming at {OLLAMA_BASE_URL} or {_FALLBACK_URL}."
    ) from last_exc


def _openai_stream(messages: list[dict[str, str]]) -> Generator[dict, None, None]:
    """Stream chat completions from OpenAI using SSE."""
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model":       OPENAI_MODEL,
        "messages":    messages,
        "temperature": 0.1,
        "max_tokens":  1024,
        "stream":      True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            method="POST",
        )
        full_text = []
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data_part = line[5:].strip()
                if data_part == "[DONE]":
                    break
                try:
                    obj = json.loads(data_part)
                    delta = obj["choices"][0]["delta"].get("content", "")
                    if delta:
                        full_text.append(delta)
                        yield {"type": "token", "content": delta}
                except Exception:
                    continue

        yield {
            "type": "done",
            "model": f"openai/{OPENAI_MODEL}",
            "full_text": "".join(full_text).strip(),
        }
    except Exception as exc:
        raise ConnectionError(f"OpenAI streaming error: {exc}") from exc
