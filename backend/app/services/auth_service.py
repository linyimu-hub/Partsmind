"""
app/services/auth_service.py
────────────────────────────
JWT authentication logic.

Pattern: Service layer owns all business logic.
         Endpoints just call service methods and return results.

Security decisions:
- Passwords hashed with bcrypt (work factor 12)
- Access token: short-lived (60min), stored in memory
- Refresh token: long-lived (7 days), stored in httpOnly cookie
- Token payload minimal: only user_id + role (avoids stale data issues)
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import TokenResponse, UserCreate

logger = get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + expires_delta
    payload["iat"] = datetime.now(UTC)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_token_pair(user_id: UUID, role: str) -> TokenResponse:
    """Create access + refresh token pair for a user."""
    sub = str(user_id)
    access_token = _create_token(
        {"sub": sub, "role": role, "type": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = _create_token(
        {"sub": sub, "type": "refresh"},
        timedelta(days=settings.refresh_token_expire_days),
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises UnauthorizedException on failure."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError as e:
        logger.warning("auth.token_invalid", error=str(e))
        raise UnauthorizedException("Invalid or expired token")


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, data: UserCreate) -> User:
        # Check email not already taken
        existing = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        if existing.scalar_one_or_none():
            from app.core.exceptions import ValidationException
            raise ValidationException(f"Email {data.email} is already registered")

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        self.db.add(user)
        await self.db.flush()  # get the ID without committing
        logger.info("auth.user_registered", user_id=str(user.id), email=user.email)
        return user

    async def login(self, email: str, password: str) -> tuple[User, TokenResponse]:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedException("Account is deactivated")

        tokens = create_token_pair(user.id, user.role)
        logger.info("auth.login_success", user_id=str(user.id))
        return user, tokens

    async def get_current_user(self, token: str) -> User:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise UnauthorizedException("Invalid token type")

        user_id = payload.get("sub")
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")
        return user
