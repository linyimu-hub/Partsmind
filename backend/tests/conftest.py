"""
Shared pytest fixtures.

For integration tests we spin up a real test DB.
For unit tests we use mocks (no DB needed).
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP client for API integration tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
