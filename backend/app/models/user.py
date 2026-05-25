"""
app/models/user.py
──────────────────
User model with role-based access control.

Roles:
  - user:  can search and chat
  - admin: can also upload docs, view analytics
"""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chat import ChatSession
    from app.models.feedback import Feedback


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.role}]>"

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
