"""
app/api/deps/auth.py
────────────────────
FastAPI dependencies for authentication.

Usage in endpoint:
    @router.get("/protected")
    async def endpoint(current_user: User = Depends(get_current_user)):
        ...

    @router.post("/admin-only")
    async def admin_endpoint(user: User = Depends(require_admin)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthService

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    service = AuthService(db)
    return await service.get_current_user(credentials.credentials)


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise ForbiddenException("Admin access required")
    return current_user
