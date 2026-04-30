"""Tests for graceful KG-build degradation in PredictionService (SHA-33 Task 5).

NOTE: These tests were written for the pre-SHA-102 PredictionService
architecture (in-memory _sessions, mutable graph_builder/prediction_engine
attributes, get_intake_service legacy singleton). After SHA-102, the
service's graph_builder/prediction_engine are read-only @properties and
all reads go through a UnitOfWork. The tests below bypass __init__ via
__new__() and assign to those properties directly, which now raises
AttributeError.

The KG fallback behavior they cover is still exercised end-to-end by
apps/api/tests/db/test_prediction_service.py (which uses the proper
db_sessionmaker fixture). These older tests are skipped pending a rewrite
to the UoW pattern; remove the skip marker once they're rewritten.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_orchestrator.models.prediction_v2 import PredictionMode

pytestmark = pytest.mark.skip(
    reason="Legacy-architecture tests; SHA-102 made graph_builder/prediction_engine read-only @properties. "
    "Rewrite using db_sessionmaker fixture to exercise the same KG fallback path."
)


@pytest.mark.asyncio
async def test_kg_build_exception_degrades_to_rag_only(tmp_path):
    """When GraphBuilder.build raises, the service must:
    1. log a structured event,
    2. call prediction_engine.predict with mode=RAG_ONLY and knowledge_graph=None,
    3. NOT bubble the exception to the caller.
    """
    from apps.api.src.services.prediction_service import PredictionService

    svc = PredictionService.__new__(PredictionService)
    svc.graph_builder = MagicMock()
    svc.graph_builder.build.side_effect = ValueError(
        "temporal validator: damage event before tenancy start"
    )
    svc.kg_store = MagicMock()
    svc.predictions_dir = tmp_path / "preds"
    svc.predictions_dir.mkdir()
    svc.dispute_predictions_dir = tmp_path / "disputes"
    svc.dispute_predictions_dir.mkdir()

    fake_prediction = SimpleNamespace(
        prediction_id="pred_001",
        metadata={},
        model_dump=lambda mode="json": {"prediction_id": "pred_001"},
    )
    svc.prediction_engine = MagicMock()
    svc.prediction_engine.predict = AsyncMock(return_value=fake_prediction)

    intake_service = MagicMock()
    case_file = SimpleNamespace(case_id="case_test")
    intake_service.get_case_file = AsyncMock(return_value=case_file)
    intake_service.get_session_id_for_case = AsyncMock(return_value=None)

    with patch(
        "apps.api.src.services.prediction_service.get_intake_service",
        return_value=intake_service,
    ):
        result = await svc.generate_prediction(case_id="case_test")

    assert result is fake_prediction
    svc.prediction_engine.predict.assert_awaited_once()
    call_kwargs = svc.prediction_engine.predict.await_args.kwargs
    assert call_kwargs["mode"] == PredictionMode.RAG_ONLY
    assert call_kwargs["knowledge_graph"] is None


@pytest.mark.asyncio
async def test_successful_kg_build_uses_hybrid_mode(tmp_path):
    """When KG builds successfully, default mode is HYBRID and the KG flows through."""
    from apps.api.src.services.prediction_service import PredictionService

    svc = PredictionService.__new__(PredictionService)
    fake_kg = SimpleNamespace(nodes=[1, 2, 3], edges=[1, 2])
    svc.graph_builder = MagicMock()
    svc.graph_builder.build.return_value = fake_kg
    svc.kg_store = MagicMock()
    svc.predictions_dir = tmp_path / "preds"
    svc.predictions_dir.mkdir()
    svc.dispute_predictions_dir = tmp_path / "disputes"
    svc.dispute_predictions_dir.mkdir()

    fake_prediction = SimpleNamespace(
        prediction_id="pred_002",
        metadata={},
        model_dump=lambda mode="json": {"prediction_id": "pred_002"},
    )
    svc.prediction_engine = MagicMock()
    svc.prediction_engine.predict = AsyncMock(return_value=fake_prediction)

    intake_service = MagicMock()
    case_file = SimpleNamespace(case_id="case_ok")
    intake_service.get_case_file = AsyncMock(return_value=case_file)
    intake_service.get_session_id_for_case = AsyncMock(return_value=None)

    with patch(
        "apps.api.src.services.prediction_service.get_intake_service",
        return_value=intake_service,
    ):
        await svc.generate_prediction(case_id="case_ok")

    call_kwargs = svc.prediction_engine.predict.await_args.kwargs
    assert call_kwargs["mode"] == PredictionMode.HYBRID
    assert call_kwargs["knowledge_graph"] is fake_kg
