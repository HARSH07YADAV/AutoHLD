"""
ingest.py (router) — HTTP endpoints for document upload and status.

POST /api/upload   — Accept a PDF, validate it, save it, start background ingestion.
GET  /api/status/{doc_id} — Return current processing status.
GET  /api/documents        — Return all documents (for document selector).
DELETE /api/documents/{doc_id} — Remove a document and all its data.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from backend.database import sqlite_db
from backend.database.vector_db import delete_document_chunks
from backend.models.schemas import StatusResponse, UploadResponse
from backend.pipeline.ingest import run_ingestion
from backend.utils.file_utils import (
    generate_doc_id,
    save_upload,
    validate_pdf,
    get_upload_path,
    delete_upload,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ingestion"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    Accept a PDF upload, validate it, persist it, and start async ingestion.

    The ingestion runs in the background — the endpoint returns immediately
    with a doc_id that the client uses to poll /status/{doc_id}.
    """
    # Read all bytes up front so we can validate size
    file_bytes = await file.read()

    error = validate_pdf(file.filename or "unknown.pdf", len(file_bytes))
    if error:
        raise HTTPException(status_code=400, detail=error)

    doc_id   = generate_doc_id()
    filename = file.filename or f"{doc_id}.pdf"

    # Save file to disk
    file_path = save_upload(file_bytes, doc_id, filename)

    # Create initial SQLite record (status = processing)
    sqlite_db.create_document(doc_id, filename, str(file_path))

    # Schedule ingestion as a background task
    background_tasks.add_task(run_ingestion, doc_id, file_path, filename)

    logger.info("Accepted upload: doc_id=%s filename=%s", doc_id, filename)

    return UploadResponse(
        doc_id  = doc_id,
        status  = "processing",
        message = f"Document '{filename}' accepted. Processing started.",
    )


@router.get("/status/{doc_id}", response_model=StatusResponse)
async def get_status(doc_id: str) -> StatusResponse:
    """Return the current ingestion status for a document."""
    doc = sqlite_db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    return StatusResponse(
        doc_id      = doc.doc_id,
        filename    = doc.filename,
        status      = doc.status,
        page_count  = doc.page_count,
        chunk_count = doc.chunk_count,
        error_msg   = doc.error_msg,
    )


@router.get("/documents")
async def list_documents() -> JSONResponse:
    """Return all documents in the system, newest first."""
    docs = sqlite_db.list_documents()
    return JSONResponse(
        content=[
            {
                "doc_id":      d.doc_id,
                "filename":    d.filename,
                "upload_time": d.upload_time.isoformat(),
                "page_count":  d.page_count,
                "chunk_count": d.chunk_count,
                "status":      d.status,
                "error_msg":   d.error_msg,
            }
            for d in docs
        ]
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> JSONResponse:
    """
    Remove a document from SQLite, ChromaDB, and disk.

    Performs a full cascade delete:
    - Removes vector chunks from ChromaDB
    - Deletes the uploaded PDF from disk
    - Cascade-deletes all SQLite records (document, queries, entities, inconsistencies)
    """
    doc = sqlite_db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    # Remove vectors from ChromaDB (ignore errors if collection is empty)
    try:
        delete_document_chunks(doc_id)
    except Exception as exc:
        logger.warning("ChromaDB delete failed for doc_id=%s: %s", doc_id, exc)

    # Remove the uploaded file from disk
    file_path = get_upload_path(doc_id, doc.filename)
    delete_upload(file_path)

    # Cascade-delete all records from SQLite (queries, entities, inconsistencies, document)
    sqlite_db.delete_document(doc_id)

    logger.info("Deleted document: doc_id=%s filename=%s", doc_id, doc.filename)
    return JSONResponse(content={"message": f"Document '{doc_id}' deleted."})
