"""
schemas.py — Pydantic models for all API request/response structures.

All data that crosses an API boundary is validated against these models.
FastAPI uses these for automatic input validation and OpenAPI docs generation.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Document records ──────────────────────────────────────────────────────────

class DocumentRecord(BaseModel):
    """Stored metadata for an uploaded document."""
    doc_id:      str
    filename:    str
    upload_time: datetime
    page_count:  int  = 0
    chunk_count: int  = 0
    status:      str  = "processing"   # processing | ready | error
    error_msg:   Optional[str] = None


class UploadResponse(BaseModel):
    """Returned immediately after a file is accepted for processing."""
    doc_id:  str
    status:  str
    message: str


class StatusResponse(BaseModel):
    """Returned by GET /status/{doc_id}."""
    doc_id:      str
    filename:    str
    status:      str
    page_count:  int
    chunk_count: int
    error_msg:   Optional[str] = None


# ── Chunk metadata ────────────────────────────────────────────────────────────

class ChunkMetadata(BaseModel):
    """Metadata stored alongside every vector in ChromaDB."""
    doc_id:      str
    filename:    str
    page_num:    int
    section:     str       = ""    # section heading, empty string if not detected
    chunk_index: int
    has_table:   bool      = False
    char_count:  int       = 0


# ── Q&A (Phase 2 — defined here so schemas are complete) ─────────────────────

class AskRequest(BaseModel):
    doc_id:   str
    question: str = Field(..., min_length=3, max_length=2000)


class SourceCitation(BaseModel):
    """A single retrieved chunk that was used to ground an answer."""
    page:    int
    section: str
    excerpt: str
    score:   float


class AskResponse(BaseModel):
    answer:     str
    sources:    list[SourceCitation]
    model:      str
    model_used: str = ""   # alias for frontend compatibility

    def model_post_init(self, __context):
        # Keep model_used in sync with model if not set explicitly
        if not self.model_used:
            self.model_used = self.model


# ── Extraction (Phase 3) ──────────────────────────────────────────────────────

class ExtractedComponent(BaseModel):
    name:     str
    swc_type: str = ""
    page:     int
    details:  dict[str, Any] = {}


class ExtractedPort(BaseModel):
    name:      str
    direction: str   # P-Port | R-Port | unknown
    interface: str   = ""
    component: str   = ""
    page:      int


class ExtractedSignal(BaseModel):
    name: str
    page: int


class ExtractedInterface(BaseModel):
    name: str
    kind: str  = ""  # SenderReceiver | ClientServer | unknown
    page: int


class ExtractedEntities(BaseModel):
    doc_id:     str
    components: list[ExtractedComponent] = []
    ports:      list[ExtractedPort]      = []
    signals:    list[ExtractedSignal]    = []
    interfaces: list[ExtractedInterface] = []


# ── Inconsistency (Phase 3) ───────────────────────────────────────────────────

class InconsistencyItem(BaseModel):
    severity:    str        # warning | error
    category:    str
    description: str
    pages:       list[int]  = []


class InconsistencyReport(BaseModel):
    doc_id:   str
    items:    list[InconsistencyItem]
    summary:  dict[str, int]   # { "errors": N, "warnings": M }
