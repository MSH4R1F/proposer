from pathlib import Path
import importlib
from types import SimpleNamespace
import sys
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "packages"))

from apps.api.src.main import app
from apps.api.src.services.mediation_service import MediationService


@pytest.fixture
def mock_claude_client():
    client = MagicMock()
    client.generate_response = AsyncMock(
        return_value="Mediator placeholder response for tests."
    )
    client.send_message = AsyncMock(
        return_value="Mediator placeholder response for tests."
    )
    return client


@pytest.fixture
def test_dispute():
    def _factory(dispute_id: str = "disp-1") -> Any:
        dispute_module = importlib.import_module("llm_orchestrator.models.dispute")
        DisputeCase = dispute_module.DisputeCase
        DisputeStatus = dispute_module.DisputeStatus
        return DisputeCase(
            dispute_id=dispute_id,
            status=DisputeStatus.READY_FOR_MEDIATION,
            tenant_session_id="tenant-sess-1",
            landlord_session_id="landlord-sess-1",
            deposit_amount=1000.0,
        )

    return _factory


@pytest.fixture
def test_prediction():
    return {
        "prediction_id": "pred-1",
        "overall_outcome": "tenant_wins",
        "overall_confidence": 0.75,
        "predicted_settlement_range": [600, 900],
        "timestamp": "2026-01-01T00:00:00",
    }


@pytest.fixture
def mediation_service(tmp_path, test_dispute, test_prediction):
    dispute = test_dispute()

    mock_dispute_service = MagicMock()
    mock_dispute_service.get_dispute = AsyncMock(return_value=dispute)
    mock_dispute_service._save_dispute = MagicMock()

    mock_intake_service = MagicMock()
    mock_intake_service.get_case_file_by_session = AsyncMock(
        side_effect=lambda session_id: SimpleNamespace(
            case_id="case-tenant" if session_id == "tenant-sess-1" else "case-landlord"
        )
    )

    mock_prediction_service = MagicMock()
    mock_prediction_service.list_predictions_for_case = AsyncMock(
        return_value=[{"prediction_id": "pred-1"}]
    )
    mock_prediction_service.get_prediction = AsyncMock(return_value=test_prediction)

    with (
        patch(
            "apps.api.src.services.dispute_service.get_dispute_service",
            return_value=mock_dispute_service,
        ),
        patch(
            "apps.api.src.services.intake_service.get_intake_service",
            return_value=mock_intake_service,
        ),
        patch(
            "apps.api.src.services.prediction_service.get_prediction_service",
            return_value=mock_prediction_service,
        ),
    ):
        service = MediationService()
        service.mediations_dir = tmp_path / "mediations"
        service.mediations_dir.mkdir(parents=True, exist_ok=True)
        service._mediations = {}

        yield service


@pytest_asyncio.fixture
async def async_client():
    async_client_cls = cast(Any, AsyncClient)
    async with async_client_cls(app=app, base_url="http://test") as client:
        yield client


# --- DB fixtures (Task 3.0) ---
import subprocess
import os
import uuid
from typing import AsyncIterator

from pytest_postgresql import factories
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Use a session-scoped Postgres process started by pytest-postgresql.
postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")


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
    # parents[3] is repo root: this conftest lives at apps/api/tests/conftest.py
    # so parents[0]=tests, [1]=api, [2]=apps, [3]=repo root.
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True, env=env, cwd=Path(__file__).resolve().parents[3],
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
