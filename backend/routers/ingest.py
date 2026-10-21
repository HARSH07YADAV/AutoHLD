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
from backend.database.vector_db import delete_document_chunks, collection_count
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


@router.post("/upload/sample", response_model=UploadResponse)
async def load_sample_document(background_tasks: BackgroundTasks) -> UploadResponse:
    """Load the built-in synthetic AUTOSAR BMS HLD PDF for testing and evaluation."""
    sample_path = Path(__file__).resolve().parent.parent.parent / "demo" / "sample_docs" / "sample_hld.pdf"
    if not sample_path.exists():
        from demo.generate_sample_pdf import build_pdf
        build_pdf()
    file_bytes = sample_path.read_bytes()
    doc_id = generate_doc_id()
    filename = "AUTOSAR_BMS_HighLevelDesign.pdf"
    file_path = save_upload(file_bytes, doc_id, filename)
    sqlite_db.create_document(doc_id, filename, str(file_path))
    background_tasks.add_task(run_ingestion, doc_id, file_path, filename)
    logger.info("Loaded sample document: doc_id=%s filename=%s", doc_id, filename)
    return UploadResponse(
        doc_id  = doc_id,
        status  = "processing",
        message = "Sample AUTOSAR BMS document loaded. Processing started.",
    )


@router.get("/status/{doc_id}", response_model=StatusResponse)
async def get_status(doc_id: str) -> StatusResponse:
    """Return the current ingestion status for a document.

    Also reports whether the vector store is in sync with the database
    (chunk_count > 0 but vector_count == 0 means re-upload is needed).
    """
    doc = sqlite_db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    # Detect vector store / SQLite mismatch
    if doc.status == "ready" and doc.chunk_count > 0:
        vec_count = collection_count(doc_id)
        if vec_count == 0:
            logger.warning(
                "doc_id=%s shows %d chunks in SQLite but 0 in ChromaDB — vector store is out of sync.",
                doc_id, doc.chunk_count,
            )
            # Return synthetic error so the UI can prompt for re-upload
            return StatusResponse(
                doc_id      = doc.doc_id,
                filename    = doc.filename,
                status      = "error",
                page_count  = doc.page_count,
                chunk_count = doc.chunk_count,
                error_msg   = (
                    "Vector store is out of sync with the database. "
                    "Please delete and re-upload this document to fix it."
                ),
            )

    return StatusResponse(
        doc_id      = doc.doc_id,
        filename    = doc.filename,
        status      = doc.status,
        page_count  = doc.page_count,
        chunk_count = doc.chunk_count,
        error_msg   = doc.error_msg,
    )


@router.post("/repair/{doc_id}")
async def repair_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    Re-ingest a document whose vector store has become out of sync.

    Use this when the document shows as 'ready' in the database but
    Q&A fails because ChromaDB has no chunks for it.
    The document PDF must still exist on disk.
    """
    doc = sqlite_db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    file_path = get_upload_path(doc_id, doc.filename)
    if not file_path.exists():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Original PDF file not found on disk. "
                "Please delete this document and re-upload the PDF."
            ),
        )

    logger.info("Repair requested for doc_id=%s — resetting and re-ingesting.", doc_id)

    # Clean up stale ChromaDB data and reset status to processing
    try:
        delete_document_chunks(doc_id)
    except Exception as exc:
        logger.warning("ChromaDB cleanup during repair failed: %s", exc)

    sqlite_db.update_document_error(doc_id, None)  # clear error
    sqlite_db.update_document_processing(doc_id)   # set status=processing

    background_tasks.add_task(run_ingestion, doc_id, file_path, doc.filename)

    return JSONResponse(content={
        "doc_id": doc_id,
        "status": "processing",
        "message": f"Re-ingestion started for '{doc.filename}'.",
    })


@router.get("/documents")
async def list_documents() -> JSONResponse:
    """Return all documents in the system, newest first.

    Each entry includes a ``needs_repair`` flag set to True when the
    document is marked ready but has no chunks in the vector store —
    the client should prompt the user to use the repair or re-upload flow.
    """
    docs = sqlite_db.list_documents()
    result = []
    for d in docs:
        vec_count = 0
        needs_repair = False
        if d.status == "ready" and d.chunk_count > 0:
            try:
                vec_count = collection_count(d.doc_id)
                needs_repair = (vec_count == 0)
            except Exception:
                pass  # ChromaDB unavailable — don't block the list

        result.append({
            "doc_id":       d.doc_id,
            "filename":     d.filename,
            "upload_time":  d.upload_time.isoformat(),
            "page_count":   d.page_count,
            "chunk_count":  d.chunk_count,
            "status":       "error" if needs_repair else d.status,
            "error_msg":    (
                "Vector store out of sync — please delete and re-upload."
                if needs_repair else d.error_msg
            ),
            "needs_repair": needs_repair,
            "vector_count": vec_count,
        })
    return JSONResponse(content=result)


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
