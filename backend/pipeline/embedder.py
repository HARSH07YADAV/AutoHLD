"""
embedder.py — Generate embeddings for chunks and store them in ChromaDB.

Responsibility: load the sentence-transformer model once at startup,
embed a list of Chunk objects in batches, and write all vectors to ChromaDB
via the vector_db wrapper.

The model (all-MiniLM-L6-v2) produces 384-dimensional float32 vectors.
It runs entirely on CPU — no GPU required — and takes ~80 MB of memory.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

from backend.config import EMBEDDING_MODEL
from backend.database import vector_db
from backend.pipeline.chunker import Chunk

if TYPE_CHECKING:
    pass

import functools

logger = logging.getLogger(__name__)

# ── Model singleton ───────────────────────────────────────────────────────────
# The model is loaded once when this module is first imported and reused for
# every subsequent call. Loading takes ~3–5 seconds; embedding is fast after that.

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
        dim = getattr(_model, 'get_embedding_dimension', None) or getattr(_model, 'get_sentence_embedding_dimension', None)
        logger.info("Embedding model loaded (vector dim: %s)", dim() if dim else '?')
    return _model


def warm_up_embedder() -> None:
    """Pre-warm embedding model in the background so user requests are instantaneous."""
    try:
        model = _get_model()
        model.encode("AUTOSAR high level design warmup", normalize_embeddings=True)
        logger.info("Embedding model pre-warmed successfully.")
    except Exception as exc:
        logger.warning("Embedder warm-up failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def embed_and_store(chunks: list[Chunk], batch_size: int = 64) -> int:
    """
    Embed a list of Chunk objects and persist them to ChromaDB.

    Processes chunks in batches to avoid memory pressure on large documents.
    Uses ChromaDB upsert — safe to call multiple times (idempotent).

    Parameters
    ----------
    chunks : list[Chunk]
        Output of chunker.chunk_document().
    batch_size : int
        Number of chunks to embed in one SentenceTransformer call.
        Smaller values use less memory; larger values are faster.

    Returns
    -------
    int
        Total number of chunks successfully stored.
    """
    if not chunks:
        logger.warning("embed_and_store called with empty chunk list.")
        return 0

    model = _get_model()
    total_stored = 0

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]

        # Extract texts for the batch
        texts = [c.text for c in batch]

        # Embed — returns a numpy array of shape (len(batch), 384)
        logger.debug("Embedding batch %d–%d …", batch_start, batch_start + len(batch))
        vectors = model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,   # normalise so cosine ≈ dot product
        )

        # Build parallel lists for ChromaDB
        ids        = [c.chunk_id for c in batch]
        embeddings = [vec.tolist() for vec in vectors]
        documents  = texts
        metadatas  = [
            {
                "doc_id":      c.doc_id,
                "filename":    c.filename,
                "page_num":    c.page_num,
                "section":     c.section,
                "chunk_index": c.chunk_index,
                "has_table":   str(c.has_table),  # ChromaDB metadata values must be str/int/float
                "char_count":  c.char_count,
            }
            for c in batch
        ]

        vector_db.store_chunks(
            ids        = ids,
            embeddings = embeddings,
            documents  = documents,
            metadatas  = metadatas,
        )

        total_stored += len(batch)
        logger.debug("Stored %d chunks so far.", total_stored)

    logger.info("Embedding complete: %d chunks stored in ChromaDB.", total_stored)
    return total_stored


@functools.lru_cache(maxsize=1024)
def _cached_embed_query(query: str) -> tuple[float, ...]:
    model = _get_model()
    vector = model.encode(
        query,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return tuple(vector.tolist())


def embed_query(query: str) -> list[float]:
    """
    Embed a single query string for retrieval.

    Uses an LRU cache and the same model and normalisation as embed_and_store, so cosine
    similarities are directly comparable.

    Parameters
    ----------
    query : str
        The user's natural language question.

    Returns
    -------
    list[float]
        A 384-dimensional normalised embedding vector.
    """
    normalized_q = query.strip()
    return list(_cached_embed_query(normalized_q))


def get_embedding_dimension() -> int:
    """Return the output vector dimension of the loaded model."""
    model = _get_model()
    if hasattr(model, 'get_embedding_dimension'):
        return model.get_embedding_dimension()
    if hasattr(model, 'get_sentence_embedding_dimension'):
        return model.get_sentence_embedding_dimension()
    # Final fallback: encode a dummy string and check the shape
    import numpy as np
    dummy = model.encode(['x'], convert_to_numpy=True)
    return int(np.array(dummy).shape[-1])
