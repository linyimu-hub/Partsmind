"""
app/tasks/ingest.py
────────────────────
Celery task: process uploaded document through the full pipeline.

Pipeline steps:
  1. Set status → PROCESSING
  2. Parse file (PDF/DOCX → text chunks)
  3. Embed each chunk (OpenAI API, batched)
  4. Save chunks + embeddings to PostgreSQL
  5. Set status → COMPLETED
  On any error → set status FAILED + save error_message

Batching strategy:
  OpenAI allows up to 2048 texts per embed call.
  We batch in groups of 100 to balance latency vs API limits.
  Each batch is one API call (reduces overhead vs 1-per-chunk).

Idempotency:
  If the task runs twice (e.g. worker crash + retry),
  we delete existing chunks first, then re-process.
  This makes the task safe to retry.
"""

import asyncio
import time
from pathlib import Path
from uuid import UUID

from celery import shared_task
from openai import OpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Sync OpenAI client for Celery (Celery tasks are sync by default)
_openai = OpenAI(api_key=settings.openai_api_key)

EMBED_BATCH_SIZE = 100   # texts per OpenAI embedding API call


@shared_task(
    name="app.tasks.ingest.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,   # seconds between retries
    queue="ingest",
)
def process_document(self, document_id: str) -> dict:
    """
    Main ingestion task. Called by the upload endpoint after saving the file.

    Args:
        document_id: UUID string of the Document record in PostgreSQL

    Returns:
        dict with chunk_count and processing time
    """
    t_start = time.monotonic()
    doc_uuid = UUID(document_id)

    # Run the async pipeline in a sync context
    # (Celery doesn't natively support async tasks)
    try:
        result = asyncio.run(_run_pipeline(doc_uuid))
        elapsed = round(time.monotonic() - t_start, 2)
        logger.info(
            "ingest.task_complete",
            document_id=document_id,
            chunks=result["chunk_count"],
            elapsed_s=elapsed,
        )
        return {**result, "elapsed_seconds": elapsed}

    except Exception as exc:
        logger.error(
            "ingest.task_failed",
            document_id=document_id,
            error=str(exc),
            attempt=self.request.retries,
        )
        # Update document status to FAILED before retry/give-up
        asyncio.run(_mark_failed(doc_uuid, str(exc)))

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


async def _run_pipeline(document_id: UUID) -> dict:
    """Full async pipeline: parse → chunk → embed → store."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        # ── 1. Load document record ────────────────────────────
        from sqlalchemy import select
        from app.models.document import Document, DocumentStatus, DocumentChunk, DocEmbedding

        result = await db.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            raise ValueError(f"Document {document_id} not found in DB")

        # ── 2. Set status → PROCESSING ─────────────────────────
        document.status = DocumentStatus.PROCESSING
        await db.commit()
        logger.info("ingest.processing", doc_id=str(document_id), file=document.filename)

        # ── 3. Parse file ──────────────────────────────────────
        from app.services.document_parser import parse_document
        file_path = Path(document.storage_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        parsed = parse_document(file_path)
        logger.info(
            "ingest.parsed",
            chunks=len(parsed.chunks),
            language=parsed.detected_language,
        )

        # ── 4. Idempotency: delete existing chunks if re-processing ──
        from sqlalchemy import delete
        await db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await db.flush()

        # ── 5. Embed all chunks (batched) ──────────────────────
        texts = [chunk.content for chunk in parsed.chunks]
        embeddings = await _embed_in_batches(texts)

        # ── 6. Save chunks + embeddings ────────────────────────
        for i, (parsed_chunk, embedding) in enumerate(zip(parsed.chunks, embeddings)):
            db_chunk = DocumentChunk(
                document_id=document_id,
                content=parsed_chunk.content,
                chunk_index=parsed_chunk.chunk_index,
                chunk_metadata=parsed_chunk.metadata,
            )
            db.add(db_chunk)
            await db.flush()  # get db_chunk.id

            db_embedding = DocEmbedding(
                chunk_id=db_chunk.id,
                embedding=embedding,
            )
            db.add(db_embedding)

            # Commit in batches to avoid huge transactions
            if (i + 1) % 50 == 0:
                await db.commit()
                logger.info("ingest.progress", processed=i + 1, total=len(texts))

        # ── 7. Update document status ──────────────────────────
        document.status = DocumentStatus.COMPLETED
        document.chunk_count = len(parsed.chunks)
        await db.commit()

    await engine.dispose()
    return {"chunk_count": len(parsed.chunks)}


async def _embed_in_batches(texts: list[str]) -> list[list[float]]:
    """
    Embed texts in batches using OpenAI API.
    Uses sync client in executor to avoid blocking the event loop.
    """
    all_embeddings: list[list[float]] = []

    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start : batch_start + EMBED_BATCH_SIZE]

        # Run sync OpenAI call in thread pool (non-blocking)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda b=batch: _openai.embeddings.create(
                model=settings.openai_embedding_model,
                input=b,
            ),
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        logger.info(
            "ingest.embed_batch",
            batch_start=batch_start,
            batch_size=len(batch),
            total_so_far=len(all_embeddings),
        )

    return all_embeddings


async def _mark_failed(document_id: UUID, error_message: str) -> None:
    """Update document status to FAILED with error details."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from app.models.document import Document, DocumentStatus

    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = error_message[:1000]  # truncate for DB column
            await db.commit()

    await engine.dispose()
