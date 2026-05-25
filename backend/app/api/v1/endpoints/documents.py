"""
app/api/v1/endpoints/documents.py
──────────────────────────────────
POST /documents/upload          — upload PDF/DOCX, trigger ingestion
GET  /documents                 — list all documents (admin)
GET  /documents/{id}/status     — poll ingestion status
DELETE /documents/{id}          — delete document + chunks
"""

import uuid
from pathlib import Path
from typing import Any

import aiofiles
import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user, require_admin
from app.core.config import settings
from app.core.exceptions import (
    FileTooLargeException,
    NotFoundException,
    UnsupportedFileTypeException,
)
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.tasks.ingestion_tasks import process_document

logger = get_logger(__name__)
router = APIRouter()

# MIME → file type mapping
ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    description: str = Form(default=""),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Upload a document for async ingestion.
    Returns immediately with document_id and task_id.
    Client should poll /documents/{id}/status.
    """
    # ── Validate file type ────────────────────────────────────────
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise UnsupportedFileTypeException(
            f"File type '{content_type}' not supported. "
            f"Accepted: PDF, DOCX"
        )

    file_type = ALLOWED_MIME_TYPES[content_type]

    # ── Validate file size ────────────────────────────────────────
    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise FileTooLargeException(
            f"File size {size_mb:.1f}MB exceeds limit of {settings.max_upload_size_mb}MB"
        )

    # ── Save to storage ───────────────────────────────────────────
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{uuid.uuid4()}.{file_type}"
    storage_path = upload_dir / safe_filename

    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(file_bytes)

    logger.info(
        "document.uploaded",
        filename=file.filename,
        size_mb=round(size_mb, 2),
        storage_path=str(storage_path),
    )

    # ── Create DB record ──────────────────────────────────────────
    doc = Document(
        filename=safe_filename,
        original_filename=file.filename or "unknown",
        file_type=file_type,
        file_size_bytes=len(file_bytes),
        storage_path=safe_filename,
        status=DocumentStatus.PENDING,
        doc_metadata={"description": description, "uploaded_by": str(current_user.id)},
    )
    db.add(doc)
    await db.flush()

    # ── Dispatch Celery task ──────────────────────────────────────
    task = process_document.delay(str(doc.id))

    logger.info(
        "document.ingestion_queued",
        document_id=str(doc.id),
        task_id=task.id,
    )

    return {
        "document_id": str(doc.id),
        "task_id": task.id,
        "status": "pending",
        "message": "Document uploaded. Processing started in background.",
        "poll_url": f"/api/v1/documents/{doc.id}/status",
    }


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Poll ingestion status. Client calls this every 2-3 seconds."""
    result = await db.execute(
        sa.select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")

    return {
        "document_id": str(doc.id),
        "filename": doc.original_filename,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat(),
    }


@router.get("", response_model=list[dict])
async def list_documents(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all documents with status (admin only)."""
    result = await db.execute(
        sa.select(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "filename": d.original_filename,
            "file_type": d.file_type,
            "status": d.status,
            "chunk_count": d.chunk_count,
            "size_bytes": d.file_size_bytes,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete document, all its chunks, and embeddings (CASCADE).
    Also removes file from storage.
    """
    result = await db.execute(
        sa.select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")

    # Delete file from storage
    storage_path = Path(settings.upload_dir) / doc.storage_path
    if storage_path.exists():
        storage_path.unlink()

    await db.delete(doc)  # CASCADE handles chunks + embeddings
    logger.info("document.deleted", document_id=str(document_id))
