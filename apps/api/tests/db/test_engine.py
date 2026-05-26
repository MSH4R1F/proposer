import ssl

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.src.db.engine import (
    _normalize_tls,
    create_engine_from_url,
    make_sessionmaker,
)


def test_normalize_tls_no_sslmode_is_unchanged() -> None:
    url = "postgresql+asyncpg://x:y@localhost:5432/z"
    out, connect_args = _normalize_tls(url)
    assert out == url
    assert connect_args == {}


def test_normalize_tls_require_uses_non_verifying_context() -> None:
    # Supabase's pooler presents a private-CA cert; sslmode=require means
    # "encrypt, do NOT verify" (libpq semantics). asyncpg's ssl=True would do
    # full verify-full and fail, so we must hand it a non-verifying context.
    url = (
        "postgresql+asyncpg://u:p@aws-1-eu-central-1.pooler.supabase.com"
        ":5432/postgres?sslmode=require"
    )
    out, connect_args = _normalize_tls(url)
    assert "sslmode=" not in out
    assert out.endswith("/postgres")
    ctx = connect_args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_normalize_tls_preserves_other_query_params() -> None:
    url = "postgresql+asyncpg://u:p@host:5432/db?application_name=app&sslmode=require"
    out, _ = _normalize_tls(url)
    assert "application_name=app" in out
    assert "sslmode=" not in out
    assert "?" in out and not out.endswith(("?", "&"))


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
