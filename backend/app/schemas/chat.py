"""
app/schemas/chat.py
───────────────────
Chat request/response schemas.

AgentResponse is the most important schema — it's what the frontend
renders as a chat bubble with source cards below it.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: UUID | None = None  # None = start new session
    # Optional image as base64 for multimodal queries
    image_base64: str | None = None
    image_mime_type: str | None = None  # "image/jpeg" | "image/png"


class SourceReference(BaseModel):
    """A source that grounded the agent's answer — displayed as a card in UI."""
    type: str           # "product" | "document_chunk"
    id: str
    name: str
    relevance: float    # 0.0–1.0 cosine similarity
    excerpt: str | None = None   # short text snippet for doc chunks
    url: str | None = None       # product image or doc link


class AgentResponse(BaseModel):
    """Full response from the agent including answer + metadata."""
    session_id: UUID
    message_id: UUID
    content: str
    sources: list[SourceReference] = []
    confidence: float = Field(..., ge=0.0, le=1.0)
    tools_used: list[str] = []
    latency_ms: int
    # If confidence is low, suggest human review
    needs_human_review: bool = False


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    sources: list[SourceReference] | None
    confidence: float | None
    latency_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class FeedbackRequest(BaseModel):
    message_id: UUID
    rating: str = Field(..., pattern="^(up|down)$")
    comment: str | None = Field(None, max_length=1000)
