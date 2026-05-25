"""
app/db/base.py
──────────────
SQLAlchemy declarative base + common mixin.

All ORM models inherit from Base.
TimestampMixin adds created_at / updated_at automatically.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


class TimestampMixin:
    """
    Adds created_at and updated_at columns.
    updated_at is automatically refreshed on UPDATE by the DB trigger.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """Primary key as UUID (better for distributed systems, no enumeration attacks)."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
