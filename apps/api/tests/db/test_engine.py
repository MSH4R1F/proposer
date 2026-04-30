import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.src.db.engine import create_engine_from_url, make_sessionmaker


@pytest.mark.asyncio
async def test_create_engine_returns_async_engine() -> None:
    engine = create_engine_from_url("postgresql+asyncpg://x:y@localhost:5432/z")
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_make_sessionmaker_returns_async_sessionmaker() -> None:
    engine = create_engine_from_url("postgresql+asyncpg://x:y@localhost:5432/z")
    sm = make_sessionmaker(engine)
    assert isinstance(sm, async_sessionmaker)
    session = sm()
    assert isinstance(session, AsyncSession)
    await session.close()
    await engine.dispose()
