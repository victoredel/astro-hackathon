"""
Async SQLAlchemy engine and session factory.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings
from db.models import Base

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
