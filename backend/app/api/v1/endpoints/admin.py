"""
app/api/v1/endpoints/admin.py
──────────────────────────────
Admin-only analytics and management endpoints.

GET /admin/analytics/overview   — key metrics dashboard
GET /admin/analytics/feedback   — thumbs up/down breakdown
GET /admin/analytics/failures   — low-confidence + downvoted answers
GET /admin/documents            — document management
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import require_admin
from app.db.session import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentStatus
from app.models.feedback import Feedback
from app.models.product import Product
from app.models.user import User

router = APIRouter()


@router.get("/analytics/overview")
async def get_overview(
    days: int = 7,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Dashboard overview metrics for the last N days.
    This is what you show in the live demo to impress the interviewer.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total queries
    total_q = await db.scalar(
        sa.select(sa.func.count(ChatMessage.id))
        .where(ChatMessage.role == "assistant")
        .where(ChatMessage.created_at >= since)
    )

    # Average confidence
    avg_conf = await db.scalar(
        sa.select(sa.func.avg(ChatMessage.confidence))
        .where(ChatMessage.role == "assistant")
        .where(ChatMessage.created_at >= since)
    )

    # Average latency
    avg_lat = await db.scalar(
        sa.select(sa.func.avg(ChatMessage.latency_ms))
        .where(ChatMessage.role == "assistant")
        .where(ChatMessage.created_at >= since)
    )

    # Feedback breakdown
    total_up = await db.scalar(
        sa.select(sa.func.count(Feedback.id))
        .where(Feedback.rating == "up")
        .where(Feedback.created_at >= since)
    )
    total_down = await db.scalar(
        sa.select(sa.func.count(Feedback.id))
        .where(Feedback.rating == "down")
        .where(Feedback.created_at >= since)
    )

    # Docs processed
    docs_ok = await db.scalar(
        sa.select(sa.func.count(Document.id))
        .where(Document.status == DocumentStatus.COMPLETED)
    )

    total_products = await db.scalar(sa.select(sa.func.count(Product.id)))

    total_feedback = (total_up or 0) + (total_down or 0)
    satisfaction = (
        round((total_up or 0) / total_feedback, 3) if total_feedback else None
    )

    return {
        "period_days": days,
        "total_queries": total_q or 0,
        "avg_confidence": round(float(avg_conf), 3) if avg_conf else None,
        "avg_latency_ms": round(float(avg_lat)) if avg_lat else None,
        "feedback": {
            "thumbs_up": total_up or 0,
            "thumbs_down": total_down or 0,
            "satisfaction_rate": satisfaction,
        },
        "knowledge_base": {
            "documents_indexed": docs_ok or 0,
            "total_products": total_products or 0,
        },
    }


@router.get("/analytics/failures")
async def get_failure_cases(
    limit: int = 20,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Returns low-confidence answers and downvoted responses.
    This is your failure case analysis — feeds prompt improvement.

    Workflow:
      1. Admin reviews this list weekly
      2. Identifies patterns (e.g., "questions about compatibility often fail")
      3. Adds those cases to EVAL_DATASET
      4. Improves the relevant prompt
      5. Runs eval to confirm improvement
    """
    # Low confidence answers (< 0.55)
    low_conf_result = await db.execute(
        sa.select(ChatMessage)
        .where(ChatMessage.role == "assistant")
        .where(ChatMessage.confidence < 0.55)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit // 2)
    )
    low_conf = low_conf_result.scalars().all()

    # Downvoted answers
    downvoted_result = await db.execute(
        sa.select(ChatMessage, Feedback)
        .join(Feedback, Feedback.message_id == ChatMessage.id)
        .where(Feedback.rating == "down")
        .order_by(Feedback.created_at.desc())
        .limit(limit // 2)
    )
    downvoted_rows = downvoted_result.all()

    failures = []

    for msg in low_conf:
        failures.append({
            "type": "low_confidence",
            "message_id": str(msg.id),
            "content_preview": msg.content[:200],
            "confidence": msg.confidence,
            "latency_ms": msg.latency_ms,
            "tools_used": msg.tools_used,
            "created_at": msg.created_at.isoformat(),
        })

    for msg, fb in downvoted_rows:
        failures.append({
            "type": "downvoted",
            "message_id": str(msg.id),
            "content_preview": msg.content[:200],
            "confidence": msg.confidence,
            "user_comment": fb.comment,
            "created_at": msg.created_at.isoformat(),
        })

    # Sort by recency
    failures.sort(key=lambda x: x["created_at"], reverse=True)
    return failures[:limit]


@router.get("/analytics/top-queries")
async def get_top_queries(
    limit: int = 20,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Most frequent user queries — useful for:
    - Understanding what users actually search for
    - Identifying missing products to add to the catalog
    - Prioritizing which document sections to expand
    """
    result = await db.execute(
        sa.select(ChatMessage.content, sa.func.count().label("count"))
        .where(ChatMessage.role == "user")
        .group_by(ChatMessage.content)
        .order_by(sa.desc("count"))
        .limit(limit)
    )
    rows = result.all()
    return [
        {"query": row.content[:200], "count": row.count}
        for row in rows
    ]
