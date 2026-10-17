"""
sqlite_db.py — SQLite persistence layer for AutoHLD.

Handles all structured metadata: document records, query history,
extracted entities, and inconsistency findings.

All functions use explicit SQL — no ORM — to keep behaviour transparent and
easy to inspect with any SQLite browser.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import SQLITE_PATH
from backend.models.schemas import (
    DocumentRecord,
    InconsistencyItem,
)

# Thread-local storage ensures each thread gets its own connection,
# which is the standard pattern for SQLite in a multi-threaded server.
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if necessary."""
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(
            str(SQLITE_PATH),
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        _local.conn.row_factory = sqlite3.Row   # rows accessible as dicts
        _local.conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


# ── Schema initialisation ─────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create all tables if they do not already exist.

    Called once at application startup from main.py.
    """
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id      TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            page_count  INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'processing',
            error_msg   TEXT,
            file_path   TEXT
        );

        CREATE TABLE IF NOT EXISTS queries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id     TEXT NOT NULL REFERENCES documents(doc_id),
            question   TEXT NOT NULL,
            answer     TEXT NOT NULL,
            sources    TEXT NOT NULL,   -- JSON array of SourceCitation objects
            model_used TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS extracted_entities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id      TEXT NOT NULL REFERENCES documents(doc_id),
            entity_type TEXT NOT NULL,  -- component | port | signal | interface
            name        TEXT NOT NULL,
            details     TEXT NOT NULL,  -- JSON blob
            page_ref    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS inconsistencies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id      TEXT NOT NULL REFERENCES documents(doc_id),
            severity    TEXT NOT NULL,  -- warning | error
            category    TEXT NOT NULL,
            description TEXT NOT NULL,
            page_refs   TEXT NOT NULL   -- JSON array of page numbers
        );
    """)
    conn.commit()


# ── Document CRUD ─────────────────────────────────────────────────────────────

def create_document(
    doc_id: str,
    filename: str,
    file_path: str,
) -> None:
    """Insert a new document record with status 'processing'."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO documents (doc_id, filename, upload_time, status, file_path)
        VALUES (?, ?, ?, 'processing', ?)
        """,
        (doc_id, filename, datetime.now(timezone.utc).isoformat(), file_path),
    )
    conn.commit()


def update_document_ready(
    doc_id: str,
    page_count: int,
    chunk_count: int,
) -> None:
    """Mark a document as successfully processed."""
    conn = _get_conn()
    conn.execute(
        """
        UPDATE documents
        SET status = 'ready', page_count = ?, chunk_count = ?
        WHERE doc_id = ?
        """,
        (page_count, chunk_count, doc_id),
    )
    conn.commit()


def update_document_error(doc_id: str, error_msg: str | None) -> None:
    """Mark a document as failed with an error message, or clear a previous error."""
    conn = _get_conn()
    conn.execute(
        "UPDATE documents SET status = 'error', error_msg = ? WHERE doc_id = ?",
        (error_msg, doc_id),
    )
    conn.commit()


def update_document_processing(doc_id: str) -> None:
    """Reset a document's status to 'processing' (used during repair/re-ingestion)."""
    conn = _get_conn()
    conn.execute(
        "UPDATE documents SET status = 'processing', error_msg = NULL WHERE doc_id = ?",
        (doc_id,),
    )
    conn.commit()


def get_document(doc_id: str) -> Optional[DocumentRecord]:
    """Return a DocumentRecord for the given doc_id, or None if not found."""
    conn  = _get_conn()
    row   = conn.execute(
        "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    if row is None:
        return None
    return DocumentRecord(
        doc_id      = row["doc_id"],
        filename    = row["filename"],
        upload_time = datetime.fromisoformat(row["upload_time"]),
        page_count  = row["page_count"],
        chunk_count = row["chunk_count"],
        status      = row["status"],
        error_msg   = row["error_msg"],
    )


def list_documents() -> list[DocumentRecord]:
    """Return all document records, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY upload_time DESC"
    ).fetchall()
    return [
        DocumentRecord(
            doc_id      = r["doc_id"],
            filename    = r["filename"],
            upload_time = datetime.fromisoformat(r["upload_time"]),
            page_count  = r["page_count"],
            chunk_count = r["chunk_count"],
            status      = r["status"],
            error_msg   = r["error_msg"],
        )
        for r in rows
    ]


def delete_document(doc_id: str) -> None:
    """
    Cascade-delete a document and all its related data from SQLite.

    Deletes from child tables first (queries, entities, inconsistencies)
    then removes the parent documents row.
    """
    conn = _get_conn()
    # Delete child rows first to satisfy FK constraints
    conn.execute("DELETE FROM queries WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM extracted_entities WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM inconsistencies WHERE doc_id = ?", (doc_id,))
    # Finally delete the parent record
    conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
    conn.commit()


# ── Query history ─────────────────────────────────────────────────────────────

def save_query(
    doc_id: str,
    question: str,
    answer: str,
    sources: list[dict],
    model_used: str,
) -> None:
    """Persist a completed Q&A exchange."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO queries (doc_id, question, answer, sources, model_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            question,
            answer,
            json.dumps(sources),
            model_used,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def get_query_history(doc_id: str) -> list[dict]:
    """Return all queries for a document, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM queries WHERE doc_id = ? ORDER BY created_at DESC",
        (doc_id,),
    ).fetchall()
    return [
        {
            "id":         r["id"],
            "question":   r["question"],
            "answer":     r["answer"],
            "sources":    json.loads(r["sources"]),
            "model_used": r["model_used"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ── Extracted entities ────────────────────────────────────────────────────────

def save_entities(doc_id: str, entities: list[dict]) -> None:
    """
    Persist extracted entities (components, ports, signals, interfaces).

    Each entity dict must have: entity_type, name, details (dict), page_ref.
    Clears existing entities for the doc before inserting to allow re-extraction.
    """
    conn = _get_conn()
    conn.execute("DELETE FROM extracted_entities WHERE doc_id = ?", (doc_id,))
    conn.executemany(
        """
        INSERT INTO extracted_entities (doc_id, entity_type, name, details, page_ref)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                doc_id,
                e["entity_type"],
                e["name"],
                json.dumps(e.get("details", {})),
                e.get("page_ref", 0),
            )
            for e in entities
        ],
    )
    conn.commit()


def get_entities(doc_id: str) -> list[dict]:
    """Return all extracted entities for a document."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM extracted_entities WHERE doc_id = ? ORDER BY entity_type, name",
        (doc_id,),
    ).fetchall()
    return [
        {
            "id":          r["id"],
            "entity_type": r["entity_type"],
            "name":        r["name"],
            "details":     json.loads(r["details"]),
            "page_ref":    r["page_ref"],
        }
        for r in rows
    ]


# ── Inconsistencies ───────────────────────────────────────────────────────────

def save_inconsistencies(doc_id: str, items: list[InconsistencyItem]) -> None:
    """Persist inconsistency findings. Clears old findings before inserting."""
    conn = _get_conn()
    conn.execute("DELETE FROM inconsistencies WHERE doc_id = ?", (doc_id,))
    conn.executemany(
        """
        INSERT INTO inconsistencies (doc_id, severity, category, description, page_refs)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (doc_id, item.severity, item.category, item.description, json.dumps(item.pages))
            for item in items
        ],
    )
    conn.commit()


def get_inconsistencies(doc_id: str) -> list[dict]:
    """Return all inconsistency findings for a document."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM inconsistencies WHERE doc_id = ?", (doc_id,)
    ).fetchall()
    return [
        {
            "id":          r["id"],
            "severity":    r["severity"],
            "category":    r["category"],
            "description": r["description"],
            "pages":       json.loads(r["page_refs"]),
        }
        for r in rows
    ]
