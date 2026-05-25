"""
app/models/feedback.py
──────────────────────
User feedback on AI answers — feeds the evaluation pipeline.

rating: "up" | "down"
This simple signal lets us:
1. Track answer quality over time (dashboard)
2. Build evaluation datasets (thumbs-down = failure case to fix)
3. Fine-tune prompts based on what users found unhelpful
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.product import Product


class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The chat message this feedback is about
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # Optional: which product was returned
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    rating: Mapped[str] = mapped_column(String(10), nullable=False)  # "up" | "down"
    comment: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User | None"] = relationship(back_populates="feedbacks")
    product: Mapped["Product | None"] = relationship(back_populates="feedbacks")
