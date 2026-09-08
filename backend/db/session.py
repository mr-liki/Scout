"""
Database session and connection setup for SCOUTJOBS production.

Conservative pooling for single VM deployment.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine

from backend.api.config import get_settings


def get_engine():
    """Create sync engine for migrations and worker."""
    settings = get_settings()
    # psycopg (v3) supports both sync and async engines from the same URL --
    # no conversion needed (and no psycopg2 dependency required).
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )


def get_async_engine():
    """Create async engine for FastAPI."""
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI route handlers."""
    engine = get_async_engine()
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_session():
    """Get sync session for worker/background tasks."""
    engine = get_engine()
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    return Session()
