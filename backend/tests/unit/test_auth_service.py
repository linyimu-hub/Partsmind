"""
Unit tests for AuthService.

Tests are isolated — no real DB, no real tokens.
We mock the DB session and verify behavior.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import UnauthorizedException
from app.models.user import User, UserRole
from app.services.auth_service import (
    AuthService,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)


# ─── Password hashing ─────────────────────────────────────────
def test_hash_password_is_not_plaintext():
    hashed = hash_password("MyPassword1")
    assert hashed != "MyPassword1"
    assert len(hashed) > 20


def test_verify_password_correct():
    hashed = hash_password("MyPassword1")
    assert verify_password("MyPassword1", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("MyPassword1")
    assert verify_password("WrongPassword", hashed) is False


# ─── JWT tokens ───────────────────────────────────────────────
def test_token_pair_roundtrip():
    user_id = uuid4()
    tokens = create_token_pair(user_id, UserRole.USER)
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"

    payload = decode_token(tokens.access_token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == UserRole.USER
    assert payload["type"] == "access"


def test_decode_invalid_token_raises():
    with pytest.raises(UnauthorizedException):
        decode_token("not.a.valid.token")


# ─── AuthService ──────────────────────────────────────────────
@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_login_wrong_password_raises(mock_db):
    """Login with wrong password must raise UnauthorizedException."""
    fake_user = User(
        id=uuid4(),
        email="test@example.com",
        hashed_password=hash_password("CorrectPass1"),
        full_name="Test User",
        is_active=True,
        role=UserRole.USER,
    )
    # Mock DB to return our fake user
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = fake_user
    mock_db.execute.return_value = result_mock

    service = AuthService(mock_db)
    with pytest.raises(UnauthorizedException):
        await service.login("test@example.com", "WrongPass1")


@pytest.mark.asyncio
async def test_login_inactive_user_raises(mock_db):
    """Inactive user cannot log in."""
    fake_user = User(
        id=uuid4(),
        email="inactive@example.com",
        hashed_password=hash_password("CorrectPass1"),
        full_name="Inactive User",
        is_active=False,
        role=UserRole.USER,
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = fake_user
    mock_db.execute.return_value = result_mock

    service = AuthService(mock_db)
    with pytest.raises(UnauthorizedException, match="deactivated"):
        await service.login("inactive@example.com", "CorrectPass1")
