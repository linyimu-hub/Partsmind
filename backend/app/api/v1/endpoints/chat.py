"""
app/api/v1/endpoints/chat.py
─────────────────────────────
POST /chat/message         — 同步聊天端点（非流式）
POST /chat/message/stream  — 流式聊天端点（SSE）
GET  /chat/sessions
GET  /chat/sessions/{id}
POST /chat/feedback
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.db.session import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.chat import (
    AgentResponse,
    ChatMessageResponse,
    ChatRequest,
    ChatSessionResponse,
    FeedbackRequest,
)
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/message", response_model=AgentResponse)
async def send_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步聊天端点（保留作为 fallback）"""
    service = ChatService(db)
    return await service.handle_message(request, current_user)


@router.post("/message/stream")
async def send_message_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    流式聊天端点 — 用 SSE (Server-Sent Events) 推流答案。
    前端用 fetch + ReadableStream 解析。
    """
    service = ChatService(db)
    return StreamingResponse(
        service.handle_message_stream(request, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    responses = []
    for s in sessions:
        count_result = await db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == s.id)
        )
        responses.append(
            ChatSessionResponse(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                message_count=count_result.scalar() or 0,
            )
        )
    return responses


@router.get("/sessions/{session_id}", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatMessage)
        .join(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = Feedback(
        user_id=current_user.id,
        message_id=data.message_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(fb)
    await db.flush()
    return {"status": "ok", "feedback_id": str(fb.id)}
