"""AsyncEngine + sessionmaker factory."""

from __future__ import annotations

import re
import ssl

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _normalize_tls(url: str) -> tuple[str, dict]:
    """asyncpg uses ``ssl=``, not libpq ``sslmode=``. Translate a ``sslmode``
    query param (e.g. Supabase's ``sslmode=require``) into asyncpg's
    ``connect_args``, stripping the unsupported param from the URL. URLs without
    ``sslmode`` (e.g. the local dev database) are returned unchanged with empty
    connect_args, so existing local/test behavior is preserved.

    ``sslmode=require`` (libpq) means *encrypt but do not verify the server
    certificate*. asyncpg's ``ssl=True`` instead does full ``verify-full``,
    which fails against Supabase's pooler because it presents a private-CA
    (effectively self-signed) certificate chain. So for ``require``/``prefer``/
    ``allow`` we hand asyncpg an explicit non-verifying TLS context; only the
    ``verify-ca``/``verify-full`` modes get certificate verification.

    Note: ``APIConfig`` still validates the *original* DATABASE_URL string for
    ``sslmode=require`` (the production guardrail), so keep it in the env var.
    """
    if "sslmode=" not in url:
        return url, {}
    match = re.search(r"sslmode=([^&]*)", url)
    mode = (match.group(1) if match else "").lower()
    stripped = re.sub(r"[?&]sslmode=[^&]*", "", url)
    # If the removed param was the leading "?...", promote the next "&" to "?".
    if "?" not in stripped and "&" in stripped:
        stripped = stripped.replace("&", "?", 1)
    stripped = stripped.rstrip("?&")
    if mode in ("require", "prefer", "allow"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return stripped, {"ssl": ctx}
    # verify-ca / verify-full → full verification via the default context.
    return stripped, {"ssl": True}


def create_engine_from_url(
    url: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 5,
    pool_timeout: int = 10,
    pool_pre_ping: bool = True,
) -> AsyncEngine:
    url, connect_args = _normalize_tls(url)
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=pool_pre_ping,
        connect_args=connect_args,
        future=True,
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
