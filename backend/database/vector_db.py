"""
vector_db.py — ChromaDB client wrapper for AutoHLD.

Provides a clean interface for storing and querying chunk embeddings.
ChromaDB runs embedded (in-process) with persistent local storage — no
separate server process is needed.
"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings

from backend.config import CHROMA_DIR, CHROMA_COLLECTION

# ── Client singleton ──────────────────────────────────────────────────────────
# Initialised once when this module is first imported.

_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None   = None


def _get_collection() -> chromadb.Collection:
    """
    Return the ChromaDB collection, creating the client and collection on
    first access (lazy initialisation).
    """
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},   # cosine similarity
        )
    return _collection


# ── Write operations ──────────────────────────────────────────────────────────

def store_chunks(
    ids:        list[str],
    embeddings: list[list[float]],
    documents:  list[str],
    metadatas:  list[dict],
) -> None:
    """
    Insert a batch of chunk embeddings into ChromaDB.

    Parameters
    ----------
    ids:        Unique string IDs — format: "{doc_id}_chunk_{index}"
    embeddings: Parallel list of 384-dim float vectors
    documents:  Parallel list of raw chunk text (stored for retrieval display)
    metadatas:  Parallel list of metadata dicts (doc_id, page_num, section, …)
    """
    col = _get_collection()

    # ChromaDB upserts — safe to call again if ingestion is re-run
    col.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def delete_document_chunks(doc_id: str) -> None:
    """
    Remove all chunks belonging to a specific document.

    Called when a document is re-processed or deleted.
    """
    col = _get_collection()
    col.delete(where={"doc_id": doc_id})


# ── Read operations ───────────────────────────────────────────────────────────

def query_chunks(
    query_embedding: list[float],
    doc_id:          str,
    n_results:       int = 5,
) -> list[dict]:
    """
    Find the top-n most similar chunks for a query within a specific document.

    Returns a list of dicts, each containing:
        text     – the chunk text
        metadata – the ChunkMetadata fields (page_num, section, …)
        score    – cosine distance (lower = more similar; 0.0 is identical)
    """
    col = _get_collection()

    results = col.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"doc_id": doc_id},
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    # ChromaDB returns lists-of-lists (one inner list per query embedding)
    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append(
            {
                "text":     text,
                "metadata": meta,
                "score":    round(1 - dist, 4),  # convert distance → similarity
            }
        )

    return chunks


def get_all_chunks_for_doc(doc_id: str) -> list[dict]:
    """
    Return ALL stored chunks for a document (used by the extractor).

    ChromaDB does not support a simple "get all" with a where filter in older
    versions, so we use a dummy query with a very large n_results.
    """
    col     = _get_collection()
    results = col.get(
        where={"doc_id": doc_id},
        include=["documents", "metadatas"],
    )

    chunks = []
    for text, meta in zip(results["documents"], results["metadatas"]):
        chunks.append({"text": text, "metadata": meta})
    return chunks


def collection_count(doc_id: str) -> int:
    """Return the number of chunks stored for a document."""
    col     = _get_collection()
    results = col.get(where={"doc_id": doc_id}, include=[])
    return len(results["ids"])
