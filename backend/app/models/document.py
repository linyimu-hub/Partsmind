"""
app/models/document.py
──────────────────────
Document and DocumentChunk models for the RAG pipeline.

Processing pipeline:
  Upload → PENDING
  Celery picks up → PROCESSING
  Chunked + embedded → COMPLETED
  Any error → FAILED (with error_message)

DocumentChunk stores the actual text.
DocEmbedding stores the vector (separate table = can re-embed without losing chunks).
"""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "pdf" | "docx"
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        String(20), default=DocumentStatus.PENDING, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metadata: who uploaded, which department, etc.
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document {self.filename} [{self.status}]>"


class DocumentChunk(Base):
    """
    One document → many chunks (typically 300-500 tokens each with 50-token overlap).
    metadata stores page number, section title, etc. for citation display.
    """
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # e.g. {"page": 3, "section": "Return Policy", "char_start": 1240}
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    embedding: Mapped["DocEmbedding | None"] = relationship(
        back_populates="chunk", cascade="all, delete-orphan", uselist=False
    )


class DocEmbedding(Base):
    """Vector embedding for a document chunk."""
    __tablename__ = "doc_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        unique=True,    # one embedding per chunk
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    chunk: Mapped["DocumentChunk"] = relationship(back_populates="embedding")
