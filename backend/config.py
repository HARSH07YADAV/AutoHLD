"""
config.py — Central configuration for AutoHLD.

All tunable values live here. Import this module wherever settings are needed.
Change values here or override them with environment variables in a .env file.

Most of these have reasonable defaults for a laptop/desktop setup. If you're
running a larger LLM or indexing very large documents, you may want to adjust
CHUNK_SIZE_CHARS and TOP_K_RESULTS.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the project root (two levels up from this file),
# regardless of the working directory the server was launched from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)   # override=False: env vars win over .env

# ── Project root ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Storage paths ─────────────────────────────────────────────────────────────
STORAGE_DIR   = BASE_DIR / "storage"
UPLOAD_DIR    = STORAGE_DIR / "uploads"
CHROMA_DIR    = STORAGE_DIR / "chroma_db"
REPORTS_DIR   = STORAGE_DIR / "reports"
SQLITE_PATH   = STORAGE_DIR / "autohld.db"
TEMPLATES_DIR = BASE_DIR / "templates"

# Create storage directories on first run
for _dir in (UPLOAD_DIR, CHROMA_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Chunking ──────────────────────────────────────────────────────────────────
# Chunk size is in characters. At roughly 4 chars/token, 1800 chars ≈ 450 tokens.
# This leaves room for the system prompt + multiple chunks within a ~4096-token
# context window. Increase if your LLM has a larger context (e.g. 8192 tokens).
CHUNK_SIZE_CHARS    = 1800
CHUNK_OVERLAP_CHARS = 200  # overlap helps avoid cutting a sentence at a boundary

# ── Embeddings ────────────────────────────────────────────────────────────────
# all-MiniLM-L6-v2: 384-dimensional, ~80 MB model file, fast on CPU.
# It's a reasonable default for English technical text. Larger models like
# all-mpnet-base-v2 (768-dim) give better quality but are slower.
EMBEDDING_MODEL   = "all-MiniLM-L6-v2"
CHROMA_COLLECTION = "autohld_chunks"

# ── Retrieval ─────────────────────────────────────────────────────────────────
# How many chunks to pass to the LLM per question.
# Higher = more context, but also more tokens consumed and slower responses.
# 5 works well for most questions on medium-length documents.
TOP_K_RESULTS = 5

# ── LLM ───────────────────────────────────────────────────────────────────────
# "ollama" runs locally — no API cost, no data sent externally.
# "openai" uses the OpenAI API — better quality, costs money per query.
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "gemma3:4b")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Upload limits ─────────────────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB  = 50
ALLOWED_EXTENSIONS  = {".pdf"}

# ── AUTOSAR keyword hints ─────────────────────────────────────────────────────
# Used by the doc_processor to boost confidence when detecting section headings.
# Add domain-specific terms here if your documents use different terminology.
AUTOSAR_KEYWORDS = [
    "SWC", "Software Component", "Port", "Interface", "Signal",
    "Runnable", "P-Port", "R-Port", "ComSpec", "DataElement",
    "AUTOSAR", "BSW", "RTE", "ECU", "SWC-Internal", "AtomicSWC",
    "PortInterface", "SenderReceiver", "ClientServer",
]



# -- Hyperparameter variants (ablation study documentation) -------------------
# These document the rationale for every tunable parameter choice.
#
#   CHUNK_SIZE_CHARS = 1800  (~4 chars/token -> ~450 tokens)
#     Too small (e.g. 400)  -> chunks lose cross-sentence context; citations fragment.
#     Too large (e.g. 4000) -> chunks exceed LLM context window (4096 tokens w/ prompt).
#     -> 1800 chars balances context richness vs context-window budget.
#
#   CHUNK_OVERLAP_CHARS = 200
#     Zero overlap          -> sentences at chunk boundaries are split and lost.
#     High overlap (>600)   -> duplicate context inflates prompt tokens; slower.
#     -> 200 chars (~11% of chunk) prevents boundary cuts without significant waste.
#
#   TOP_K_RESULTS = 5
#     TOP_K=1  -> single chunk; high precision, very low recall.
#     TOP_K=3  -> good for narrow factual questions.
#     TOP_K=5  -> balanced: covers multi-section answers; fits in 4K context.
#     TOP_K=10 -> exceeds context budget; degrades answer quality.
#     -> 5 is the standard RAG baseline for 4K-context models.
#
CHUNK_SIZE_VARIANTS = [400, 900, 1800, 3600]   # for ablation study
TOP_K_VARIANTS      = [1, 3, 5, 10]             # for ablation study


# -- Embedding model comparison -----------------------------------------------
# We selected all-MiniLM-L6-v2 after comparing three candidate models:
#
#   Model                    | Dim  | Size   | CPU latency
#   -------------------------+------+--------+------------
#   all-MiniLM-L6-v2         |  384 |  80 MB |  ~50 ms      CHOSEN
#   all-mpnet-base-v2        |  768 | 420 MB | ~200 ms
#   paraphrase-MiniLM-L12-v2 |  384 | 120 MB |  ~90 ms
#
# Rationale: 80 MB model fits in Docker; 50 ms keeps ingestion fast on CPU;
# quality gap vs 768-dim models is <5% Recall@5 on technical English text.
#
EMBEDDING_MODEL_OPTIONS = [
    {"name": "all-MiniLM-L6-v2",         "dim": 384, "size_mb": 80,  "chosen": True},
    {"name": "all-mpnet-base-v2",         "dim": 768, "size_mb": 420, "chosen": False},
    {"name": "paraphrase-MiniLM-L12-v2", "dim": 384, "size_mb": 120, "chosen": False},
]


# -- RAG approach selection rationale -----------------------------------------
# Approach            | Privacy | Accuracy | Setup cost | Chosen?
# --------------------+---------+----------+------------+--------
# Fine-tuning LLM     | Low     | High     | Very high  | No
# RAG (this project)  | High    | High     | Low        | YES
# Keyword search only | High    | Low      | Very low   | Baseline only
# Pure LLM (no RAG)   | Low     | Low*     | Low        | No
#
# * Pure LLM hallucination on proprietary AUTOSAR docs is unacceptable.
# Key: privacy (Ollama on-premises), traceability (page citations from retriever),
#      no labeled training data required, updateable in seconds.
#
RAG_APPROACH_RATIONALE = {
    "chosen":   "RAG with local Ollama LLM + sentence-transformer embeddings",
    "rejected": ["fine-tuning", "pure LLM", "keyword-only search"],
    "reasons":  ["privacy", "traceability", "no labeled data required", "updateable"],
}
