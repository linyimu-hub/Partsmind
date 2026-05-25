"""
app/models/chat.py
──────────────────
Chat session and message models.

Design:
- ChatSession groups messages into a conversation
- ChatMessage stores role ("user" | "assistant"), content, and
  structured metadata: sources cited, confidence score, latency
- sources is JSONB: [{"type":"product","id":"uuid","name":"...","relevance":0.91}]
  This powers the "source cards" shown in the UI under each answer
"""

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.user import User


class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="New conversation",
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatSession {self.id} user={self.user_id}>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False  # "user" | "assistant" | "system"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Assistant-only fields (null for user messages)
    # sources: list of products/chunks that grounded this answer
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # Which tools the agent called to produce this answer
    tools_used: Mapped[list[str] | None] = mapped_column(JSONB)

    from app.db.base import TimestampMixin
    from datetime import datetime, timezone
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
