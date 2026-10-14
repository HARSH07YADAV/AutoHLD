# ─────────────────────────────────────────────────────────────────────────────
# AutoHLD — Dockerfile
#
# Builds a slim, CPU-only image for the AutoHLD FastAPI application.
#
# What happens during build:
#   1. Start from a minimal Python 3.12 base image
#   2. Install CPU-only PyTorch first (avoids pulling a large CUDA build)
#   3. Install the rest of the Python dependencies
#   4. Copy only the application source (no venv, no git history, no storage)
#   5. Pre-download the sentence-transformer embedding model so the first
#      request is not slow (model is baked into the image)
#
# Storage (uploads, chroma_db, reports, sqlite) is kept OUTSIDE the image
# and mounted as a volume — see docker-compose.yml.
# ─────────────────────────────────────────────────────────────────────────────

# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# ── Build-time arguments ──────────────────────────────────────────────────────
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2

# ── System dependencies ───────────────────────────────────────────────────────
# pdfplumber / pdfminer need some native libs; curl is for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first so Docker can cache the pip layer separately.
COPY requirements.txt .

# Install CPU-only PyTorch before sentence-transformers to avoid the large
# CUDA build being pulled in as a dependency.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# ── Pre-download embedding model ──────────────────────────────────────────────
# Bake the sentence-transformer model into the image so the first request
# is not blocked by a model download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# ── Application source ────────────────────────────────────────────────────────
COPY backend/   ./backend/
COPY frontend/  ./frontend/

# ── Runtime storage directories ───────────────────────────────────────────────
# These are placeholders; the actual data lives in the mounted volume.
RUN mkdir -p storage/uploads storage/chroma_db storage/reports templates

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
# PYTHONPATH=. is required so that "from backend.xxx import yyy" works correctly.
ENV PYTHONPATH=/app

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
