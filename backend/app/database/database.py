"""Async SQLAlchemy engine/session setup. PostgreSQL is the source of truth
in every real environment; tests substitute a SQLite (aiosqlite) engine via
the `get_db` dependency override in tests/conftest.py.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False, hide_parameters=True, pool_pre_ping=True)

# expire_on_commit=False: without this, touching an ORM attribute after a
# commit (e.g. while serializing a just-created row into a response schema)
# triggers an implicit lazy load outside the async greenlet context and
# raises MissingGreenlet.
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
