"""
bench_performance.py — AutoHLD Q&A Pipeline Performance Benchmark.

Measures latency for every stage of the pipeline and outputs a comparative
before/after report. Run AFTER starting the server with:

    uvicorn backend.main:app --host 0.0.0.0 --port 8000

Usage:
    cd /home/anchorpoint/AutoHLD
    .venv/bin/python tests/bench_performance.py [--doc-id DOC_ID] [--warmup N] [--runs N]

The script uses the /api/ask/stream SSE endpoint (same path as the UI)
and measures:
  - Retrieval latency (ChromaDB + BM25 + RRF)
  - Time-to-first-token (TTFT)
  - Generation duration
  - Total end-to-end latency
  - Token generation speed (tok/s)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


BASE_URL = "http://localhost:8000"

# ── 10 representative AUTOSAR HLD questions ───────────────────────────────────
BENCHMARK_QUESTIONS = [
    "What are the main software components in this document?",
    "What is the overall system architecture?",
    "List all P-Port and R-Port interfaces mentioned.",
    "What are the safety requirements and ASIL ratings?",
    "Describe the battery management functions.",
    "What communication protocols are used (CAN, UDS, LIN)?",
    "What watchdog mechanisms are described?",
    "What thermal management strategies are defined?",
    "List the diagnostic event manager (DEM) functions.",
    "What are the startup and shutdown sequences?",
]


@dataclass
class RequestResult:
    question: str
    retrieval_s: float = 0.0
    ttft_s: float = 0.0
    generation_s: float = 0.0
    total_s: float = 0.0
    token_count: int = 0
    tokens_per_sec: float = 0.0
    chunks_used: int = 0
    error: Optional[str] = None
    answer_preview: str = ""


def _stream_request(doc_id: str, question: str, timeout: int = 120) -> RequestResult:
    """Fire a single SSE streaming request and collect timing metrics."""
    result = RequestResult(question=question)
    url = f"{BASE_URL}/api/ask/stream"
    payload = json.dumps({"doc_id": doc_id, "question": question}).encode()

    t_wall_start = time.perf_counter()

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            buffer = b""
            for chunk in resp:
                buffer += chunk
                # Parse complete SSE blocks
                while b"\n\n" in buffer:
                    block, buffer = buffer.split(b"\n\n", 1)
                    block_str = block.decode("utf-8")
                    event = "message"
                    data_str = ""
                    for line in block_str.split("\n"):
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str += line[5:].strip()

                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if event == "sources":
                        result.retrieval_s = data.get("retrieval_time_s", 0.0)
                    elif event == "done":
                        timings = data.get("timings", {})
                        result.retrieval_s = timings.get("retrieval_s", result.retrieval_s)
                        result.ttft_s = timings.get("ttft_s", 0.0)
                        result.generation_s = timings.get("generation_s", 0.0)
                        result.total_s = timings.get("total_s", 0.0)
                        result.token_count = timings.get("token_count", 0)
                        result.tokens_per_sec = timings.get("tokens_per_sec", 0.0)
                        result.chunks_used = timings.get("chunks_used", 0)
                        answer = data.get("answer", "")
                        result.answer_preview = answer[:100].replace("\n", " ")
                        break
                    elif event == "error":
                        result.error = data.get("error", "unknown error")
                        break

    except urllib.error.URLError as e:
        result.error = f"Connection error: {e}"
    except Exception as e:
        result.error = str(e)

    # Fallback: if server didn't return timings, use wall time
    if result.total_s == 0.0 and result.error is None:
        result.total_s = round(time.perf_counter() - t_wall_start, 3)

    return result


def _get_ready_doc_id(preferred: Optional[str] = None) -> str:
    """Auto-detect a ready document from the backend."""
    if preferred:
        return preferred
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/documents", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            docs = data if isinstance(data, list) else data.get("documents", [])
            for doc in docs:
                if doc.get("status") == "ready" and doc.get("chunk_count", 0) > 5:
                    return doc["doc_id"]
    except Exception:
        pass
    raise RuntimeError("No ready document found. Upload a PDF first.")


def _print_separator(char: str = "\u2500", width: int = 72):
    print(char * width)


def run_benchmark(doc_id: str, warmup: int = 2, runs: int = 1) -> None:
    print()
    _print_separator("\u2550")
    print("  AutoHLD Q&A Pipeline \u2014 Performance Benchmark")
    _print_separator("\u2550")
    print(f"  Server  : {BASE_URL}")
    print(f"  Doc ID  : {doc_id}")
    print(f"  Warm-up : {warmup} request(s) (discarded)")
    print(f"  Runs    : {runs} run(s) per question x {len(BENCHMARK_QUESTIONS)} questions")
    print(f"  Total   : {len(BENCHMARK_QUESTIONS) * (warmup + runs)} requests")
    _print_separator()

    # Warm-up rounds
    if warmup > 0:
        print(f"\n[Warm-up] Sending {warmup} warm-up request(s) to load Ollama model...")
        for i in range(warmup):
            q = BENCHMARK_QUESTIONS[i % len(BENCHMARK_QUESTIONS)]
            r = _stream_request(doc_id, q, timeout=120)
            status = f"OK {r.total_s:.1f}s" if not r.error else f"ERR {r.error[:60]}"
            print(f"  Warm-up {i+1}/{warmup}: {status}")

    # Timed benchmark runs
    print(f"\n[Benchmark] Running {runs} timed run(s) per question...\n")

    all_results: list[RequestResult] = []
    question_summaries: list[dict] = []

    for qi, question in enumerate(BENCHMARK_QUESTIONS, 1):
        q_results: list[RequestResult] = []
        for run_i in range(runs):
            r = _stream_request(doc_id, question, timeout=120)
            q_results.append(r)
            all_results.append(r)

            status = "ERROR" if r.error else "OK"
            print(
                f"  Q{qi:02d}[{run_i+1}] {status:<5} "
                f"retr={r.retrieval_s:.3f}s  TTFT={r.ttft_s:.3f}s  "
                f"gen={r.generation_s:.3f}s  total={r.total_s:.2f}s  "
                f"{r.tokens_per_sec:.0f}tok/s  chunks={r.chunks_used}"
            )
            if r.error:
                print(f"         ERROR: {r.error}")

        ok_results = [r for r in q_results if not r.error]
        if ok_results:
            question_summaries.append({
                "question": question[:60],
                "median_total_s": statistics.median(r.total_s for r in ok_results),
                "median_ttft_s": statistics.median(r.ttft_s for r in ok_results),
                "median_tok_per_s": statistics.median(r.tokens_per_sec for r in ok_results),
                "errors": len(q_results) - len(ok_results),
            })
        print()

    # Aggregate statistics
    ok_all = [r for r in all_results if not r.error]
    errors = [r for r in all_results if r.error]

    _print_separator("\u2550")
    print("  BENCHMARK RESULTS SUMMARY")
    _print_separator("\u2550")

    if not ok_all:
        print("  ALL REQUESTS FAILED. Check server is running and document is ready.")
        return

    totals = [r.total_s for r in ok_all]
    ttfts  = [r.ttft_s for r in ok_all]
    retrs  = [r.retrieval_s for r in ok_all]
    gens   = [r.generation_s for r in ok_all]
    toks   = [r.tokens_per_sec for r in ok_all]

    print(f"\n  Requests: {len(ok_all)} succeeded, {len(errors)} failed\n")
    print(f"  {'Metric':<32} {'Median':>8}  {'Min':>8}  {'Max':>8}  {'p95':>8}")
    _print_separator()

    def _row(label, vals, unit="s"):
        if not vals:
            return
        s = sorted(vals)
        median = statistics.median(s)
        p95 = s[max(0, int(len(s) * 0.95) - 1)]
        print(f"  {label:<32} {median:>7.3f}{unit}  {min(s):>7.3f}{unit}  "
              f"{max(s):>7.3f}{unit}  {p95:>7.3f}{unit}")

    _row("Total end-to-end latency", totals)
    _row("Time-to-first-token (TTFT)", ttfts)
    _row("Retrieval stage", retrs)
    _row("Generation stage", gens)
    print()

    median_tok = statistics.median(toks)
    median_total = statistics.median(totals)
    median_ttft  = statistics.median(ttfts)

    print(f"  Median token generation speed:  {median_tok:.1f} tok/s")
    print(f"  Median chunk count used:        "
          f"{statistics.median(r.chunks_used for r in ok_all):.0f}")
    print(f"  Median token count (answers):   "
          f"{statistics.median(r.token_count for r in ok_all):.0f}")

    _print_separator()

    # Performance assessment
    print(f"\n  Performance Assessment (warm model, gemma3:4b, CPU-only, i5-13450HX):")

    def _assess(label, val, good, acceptable, unit="s"):
        emoji = "OK" if val < good else ("WARN" if val < acceptable else "SLOW")
        print(f"  {label:<28} {val:.2f}{unit}  [{emoji}]")

    _assess("Median total latency:", median_total, 6, 12)
    _assess("Median TTFT:         ", median_ttft, 1.5, 3.5)
    print(f"  {'Token speed:':28} {median_tok:.1f}tok/s  "
          f"[{'OK' if median_tok >= 40 else 'WARN' if median_tok >= 20 else 'SLOW'}]")

    print(f"\n  Hardware ceiling (gemma3:4b Q4_K_M on i5-13450HX):")
    print(f"    ~55 tok/s generation, ~100ms prompt eval per 100 tokens")
    print(f"    150-token answer: ~3.0s expected | 250-token: ~4.6s expected")
    print(f"    Cold-start penalty: 8-9s (eliminated by keep_alive=-1 warm-up)")

    _print_separator("\u2550")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoHLD Q&A Pipeline Benchmark")
    parser.add_argument("--doc-id", default=None, help="Document ID to benchmark against")
    parser.add_argument("--warmup", type=int, default=2,
                        help="Number of warm-up requests (default: 2)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Timed runs per question (default: 1)")
    parser.add_argument("--url", default="http://localhost:8000",
                        help="Base server URL")
    args = parser.parse_args()

    BASE_URL = args.url

    try:
        doc_id = _get_ready_doc_id(args.doc_id)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    run_benchmark(doc_id=doc_id, warmup=args.warmup, runs=args.runs)
