"""
app/tasks/ingestion_tasks.py
─────────────────────────────
Celery tasks for asynchronous document processing.

Why Celery instead of FastAPI BackgroundTasks?
- FastAPI BackgroundTasks run IN the web server process.
  If the process restarts, the task is lost.
- Celery tasks survive restarts: Redis persists the queue.
- Celery supports retries, dead-letter queues, monitoring (Flower).
- We can scale workers independently from the web server.

Task: process_document
  1. Load document bytes from storage
  2. Parse → clean text
  3. Chunk into overlapping segments
  4. Embed each chunk (batched, cached)
  5. Persist chunks + embeddings to PostgreSQL
  6. Update document status to COMPLETED

On any failure: status → FAILED, error_message saved for debugging.
"""

import asyncio
import uuid
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import Document, DocumentChunk, DocEmbedding, DocumentStatus
from app.services.document_parser import parse_document
from app.services.embedding_service import embed_texts

logger = get_logger(__name__)


def _make_session() -> async_sessionmaker:
    """Create a fresh DB session factory for the Celery worker process."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(
    name="app.tasks.ingestion_tasks.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="ingestion",
)
def process_document(self, document_id: str) -> dict:
    """
    Main ingestion task. Called after file is uploaded to storage.

    Args:
        document_id: UUID string of the Document record (already in DB, status=PENDING)

    Returns:
        {"status": "completed", "chunks": N} on success
    """
    return asyncio.run(_process_document_async(self, document_id))


async def _process_document_async(task, document_id: str) -> dict:
    """Async implementation — Celery tasks are sync, so we use asyncio.run()."""
    AsyncSessionLocal = _make_session()
    doc_uuid = uuid.UUID(document_id)

    async with AsyncSessionLocal() as db:
        # ── Load document record ────────────────────────────────────────
        result = await db.execute(
            sa.select(Document).where(Document.id == doc_uuid)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            logger.error("ingestion.document_not_found", document_id=document_id)
            return {"status": "error", "reason": "not_found"}

        # ── Mark as processing ──────────────────────────────────────────
        doc.status = DocumentStatus.PROCESSING
        await db.commit()
        logger.info("ingestion.started", document_id=document_id, file=doc.filename)

        try:
            # ── Read file from storage ──────────────────────────────────
            storage_path = Path(settings.upload_dir) / doc.storage_path
            if not storage_path.exists():
                raise FileNotFoundError(f"File not found at {storage_path}")

            file_bytes = storage_path.read_bytes()
            logger.info("ingestion.file_loaded", bytes=len(file_bytes))

            # ── Parse ───────────────────────────────────────────────────
            parsed = parse_document(file_bytes, doc.file_type)
            logger.info(
                "ingestion.parsed",
                chars=len(parsed.full_text),
                raw_chunks=len(parsed.chunks),
            )

            if not parsed.chunks:
                raise ValueError("Document produced no text content after parsing")

            # ── Embed all chunks (batched) ──────────────────────────────
            chunk_texts = [chunk.content for chunk in parsed.chunks]
            embeddings = await embed_texts(chunk_texts)
            logger.info("ingestion.embedded", chunks=len(embeddings))

            # ── Persist chunks + embeddings ─────────────────────────────
            # Delete existing chunks (re-ingestion support)
            await db.execute(
                sa.delete(DocumentChunk).where(DocumentChunk.document_id == doc_uuid)
            )

            for i, (chunk, vector) in enumerate(zip(parsed.chunks, embeddings)):
                db_chunk = DocumentChunk(
                    document_id=doc_uuid,
                    content=chunk.content,
                    chunk_index=i,
                    chunk_metadata=chunk.metadata,
                )
                db.add(db_chunk)
                await db.flush()  # get db_chunk.id

                db_embed = DocEmbedding(
                    chunk_id=db_chunk.id,
                    embedding=vector,
                )
                db.add(db_embed)

            # ── Update document status ──────────────────────────────────
            doc.status = DocumentStatus.COMPLETED
            doc.chunk_count = len(parsed.chunks)
            doc.doc_metadata = {**doc.doc_metadata, **parsed.metadata}
            await db.commit()

            logger.info(
                "ingestion.completed",
                document_id=document_id,
                chunks=len(parsed.chunks),
            )
            return {"status": "completed", "chunks": len(parsed.chunks)}

        except Exception as exc:
            await db.rollback()
            # Update to FAILED with error message
            async with AsyncSessionLocal() as error_db:
                await error_db.execute(
                    sa.update(Document)
                    .where(Document.id == doc_uuid)
                    .values(
                        status=DocumentStatus.FAILED,
                        error_message=str(exc)[:1000],
                    )
                )
                await error_db.commit()

            logger.error(
                "ingestion.failed",
                document_id=document_id,
                error=str(exc),
            )

            # Retry with exponential backoff for transient errors
            if isinstance(exc, (ConnectionError, TimeoutError)):
                raise task.retry(exc=exc, countdown=2 ** task.request.retries)

            return {"status": "failed", "error": str(exc)}
