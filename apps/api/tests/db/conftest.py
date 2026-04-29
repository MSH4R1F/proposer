from __future__ import annotations

import os
import socket
import subprocess
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from pytest_postgresql import factories
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# Use a session-scoped Postgres process started by pytest-postgresql.
# Pick the port ourselves so pytest-postgresql does not call port_for, which
# shells out to sysctl on macOS and fails under the Codex sandbox.
postgresql_proc = factories.postgresql_proc(port=_unused_tcp_port(), unixsocketdir="/tmp")


def _admin_url(postgresql_proc) -> str:
    return (
        f"postgresql://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/postgres"
    )


def _async_url_for_db(postgresql_proc, db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/{db_name}"
    )


@pytest.fixture(scope="session")
def _migrated_template(postgresql_proc):
    """Create a template DB and run Alembic against it once per session."""
    import psycopg

    template_name = f"proposer_template_{uuid.uuid4().hex[:8]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name}")
        conn.execute(f"CREATE DATABASE {template_name}")

    template_url = _async_url_for_db(postgresql_proc, template_name)
    env = {**os.environ, "DATABASE_URL": template_url}
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True,
        env=env,
        cwd=Path(__file__).resolve().parents[4],
    )
    yield template_name
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name} WITH (FORCE)")


@pytest_asyncio.fixture
async def db_sessionmaker(postgresql_proc, _migrated_template):
    """One isolated migrated database/sessionmaker per test."""
    import psycopg

    db_name = f"proposer_test_{uuid.uuid4().hex[:12]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {db_name} TEMPLATE {_migrated_template}")

    url = _async_url_for_db(postgresql_proc, db_name)
    engine = create_async_engine(url, poolclass=NullPool, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield sm
    await engine.dispose()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest_asyncio.fixture
async def db_session(db_sessionmaker) -> AsyncIterator[AsyncSession]:
    """One AsyncSession from the per-test DB."""
    async with db_sessionmaker() as session:
        yield session
        await session.rollback()
