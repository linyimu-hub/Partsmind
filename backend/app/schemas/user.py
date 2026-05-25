"""
app/schemas/user.py
───────────────────
Pydantic v2 schemas for User API.

Pattern used throughout the project:
  Base      — shared fields
  Create    — fields needed to create (includes password)
  Update    — all fields Optional (PATCH semantics)
  Response  — what we return to client (NEVER includes hashed_password)
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    password: str | None = Field(None, min_length=8)


class UserResponse(UserBase):
    id: UUID
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}  # enables ORM mode


# ─── Auth schemas ─────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
