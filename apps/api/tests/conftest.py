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
