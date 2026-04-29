"""
Pytest configuration for migration scripts tests.

Adds the monorepo `packages/` directory to sys.path so that
`import llm_orchestrator` (without the `packages.` prefix) resolves
correctly — required because issue_predictor.py uses
importlib.import_module("llm_orchestrator.prompts.prediction_v2").

Also provides DB fixtures (db_sessionmaker, db_session) backed by
pytest-postgresql for integration tests that need a real Postgres instance.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from pytest_postgresql import factories
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Repo root is three levels up from this file:
# scripts/migrations/tests/conftest.py → scripts/migrations/tests → scripts/migrations
# → scripts → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES_DIR = _REPO_ROOT / "packages"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_DIR))


# ---------------------------------------------------------------------------
# pytest-postgresql: start one Postgres process for the whole test session
# ---------------------------------------------------------------------------
postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")


def _admin_url(proc) -> str:
    return f"postgresql://{proc.user}:@{proc.host}:{proc.port}/postgres"


def _async_url(proc, db_name: str) -> str:
    return f"postgresql+asyncpg://{proc.user}:@{proc.host}:{proc.port}/{db_name}"


@pytest.fixture(scope="session")
def _migrated_template(postgresql_proc):
    """Create a template DB and run Alembic against it once per test session."""
    import psycopg

    template_name = f"proposer_template_{uuid.uuid4().hex[:8]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name}")
        conn.execute(f"CREATE DATABASE {template_name}")

    template_url = _async_url(postgresql_proc, template_name)
    env = {**os.environ, "DATABASE_URL": template_url}
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True,
        env=env,
        cwd=str(_REPO_ROOT),
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

    url = _async_url(postgresql_proc, db_name)
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
