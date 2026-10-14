"""
file_utils.py — File handling helpers for uploads and storage.
"""

import uuid
import shutil
from pathlib import Path

from backend.config import UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB


def generate_doc_id() -> str:
    """Return a short unique document identifier."""
    return uuid.uuid4().hex[:12]


def validate_pdf(filename: str, size_bytes: int) -> str | None:
    """
    Validate the uploaded file.

    Returns an error message string if invalid, or None if the file is acceptable.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return f"Only PDF files are accepted. Received: '{suffix}'"
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        return f"File exceeds the {MAX_UPLOAD_SIZE_MB} MB limit ({size_bytes // (1024*1024)} MB received)."
    return None


def save_upload(file_bytes: bytes, doc_id: str, original_filename: str) -> Path:
    """
    Save raw PDF bytes to the uploads directory.

    Returns the absolute path to the saved file.
    """
    safe_name   = Path(original_filename).name  # strip any directory traversal
    target_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    target_path.write_bytes(file_bytes)
    return target_path


def get_upload_path(doc_id: str, filename: str) -> Path:
    """Reconstruct the upload path from doc_id and filename."""
    safe_name = Path(filename).name
    return UPLOAD_DIR / f"{doc_id}_{safe_name}"


def delete_upload(path: Path) -> None:
    """Remove a previously saved upload file if it exists."""
    if path.exists():
        path.unlink()
