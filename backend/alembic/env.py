"""
alembic/env.py
──────────────
Async Alembic configuration.
Reads DATABASE_URL from settings (not hardcoded).
Imports all models so autogenerate can detect schema changes.
"""
#导入异步库
import asyncio

#导入日志配置库
from logging.config import fileConfig

from alembic import context

#创建异步数据库引擎
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401 — triggers all model imports
from app.core.config import settings

# ← must import all models before Base.metadata
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
#自动迁移核心，指定目标元数据
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    #数据库地址
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        #SQL参数直接展开
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
