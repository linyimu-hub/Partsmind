"""
app/db/session.py
─────────────────
Async SQLAlchemy engine + session factory.

Key decisions:
- asyncpg driver (much faster than psycopg2 for async)
- Connection pool sized for production workload
- Session per request via FastAPI Depends
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Engine ───────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,      # detect stale connections
    echo=settings.db_echo,   # log SQL in dev
)

# ─── Session factory ──────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # avoid implicit lazy-loads after commit
    autoflush=False,
)


# ─── FastAPI dependency ───────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a DB session scoped to the HTTP request.
    Auto-commits on success, auto-rolls back on error.

    Usage in endpoint:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Startup ──────────────────────────────────────────────────────────────────
async def init_db() -> None:
    """
    Called at application startup.
    Verifies the DB connection is alive.
    Actual table creation is handled by Alembic migrations.
    """
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        logger.info("db.ping_ok")
    except Exception as e:
        logger.error("db.ping_failed", error=str(e))
        raise
