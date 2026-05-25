#!/usr/bin/env python3
"""
Create the initial admin user.
Run once after `make migrate`.

Usage:
  python scripts/seed/create_admin.py
  python scripts/seed/create_admin.py --email admin@company.com --password Admin123
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.user import User, UserRole
from app.services.auth_service import hash_password


async def create_admin(email: str, password: str, name: str) -> None:
    engine = create_async_engine(settings.database_url)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=name,
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"✅ Admin created: {email}")
        print(f"   User ID: {user.id}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email",    default="admin@partsmind.com")
    parser.add_argument("--password", default="Admin123!")
    parser.add_argument("--name",     default="System Admin")
    args = parser.parse_args()
    asyncio.run(create_admin(args.email, args.password, args.name))
