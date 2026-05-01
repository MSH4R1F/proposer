"""Tests for the PREDICTION_MODE env var (SHA-33 Task 8)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_orchestrator.models.prediction_v2 import PredictionMode


def test_prediction_mode_default_hybrid(monkeypatch):
    monkeypatch.delenv("PREDICTION_MODE", raising=False)
    from apps.api.src.config import APIConfig

    cfg = APIConfig()
    assert cfg.prediction_mode == "hybrid"


def test_prediction_mode_env_override_rag_only(monkeypatch):
    monkeypatch.setenv("PREDICTION_MODE", "rag_only")
    from apps.api.src.config import APIConfig

    cfg = APIConfig()
    assert cfg.prediction_mode == "rag_only"


def test_prediction_mode_env_lowercased(monkeypatch):
    monkeypatch.setenv("PREDICTION_MODE", "LLM_ONLY")
    from apps.api.src.config import APIConfig

    cfg = APIConfig()
    assert cfg.prediction_mode == "llm_only"


def test_retrieval_strategy_default_chunk_rag(monkeypatch):
    monkeypatch.delenv("RETRIEVAL_STRATEGY", raising=False)
    from apps.api.src.config import APIConfig

    cfg = APIConfig()
    assert cfg.retrieval_strategy == "chunk_rag"


def test_retrieval_strategy_env_lowercased(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_STRATEGY", "PROPOSITION_PAGERANK")
    from apps.api.src.config import APIConfig

    cfg = APIConfig()
    assert cfg.retrieval_strategy == "proposition_pagerank"


@pytest.mark.skip(
    reason="Legacy-architecture test: SHA-102 made graph_builder/prediction_engine "
    "read-only @properties; service reads now go through a UnitOfWork. "
    "Rewrite using db_sessionmaker fixture; behavior covered by "
    "apps/api/tests/db/test_prediction_service.py."
)
@pytest.mark.asyncio
async def test_prediction_service_respects_config_default_mode(tmp_path, monkeypatch):
    """When no mode_override given, service reads default from config."""
    monkeypatch.setattr(
        "apps.api.src.services.prediction_service.config",
        SimpleNamespace(
            prediction_mode="rag_only",
            data_dir=tmp_path,
        ),
    )
    from apps.api.src.services.prediction_service import PredictionService

    svc = PredictionService.__new__(PredictionService)
    fake_kg = SimpleNamespace(nodes=[1], edges=[])
    svc.graph_builder = MagicMock()
    svc.graph_builder.build.return_value = fake_kg
    svc.kg_store = MagicMock()
    svc.predictions_dir = tmp_path / "preds"
    svc.predictions_dir.mkdir()
    svc.dispute_predictions_dir = tmp_path / "disputes"
    svc.dispute_predictions_dir.mkdir()

    fake_pred = SimpleNamespace(
        prediction_id="p1", metadata={},
        model_dump=lambda mode="json": {"prediction_id": "p1"},
    )
    svc.prediction_engine = MagicMock()
    svc.prediction_engine.predict = AsyncMock(return_value=fake_pred)

    intake = MagicMock()
    intake.get_case_file = AsyncMock(return_value=SimpleNamespace(case_id="c1"))
    intake.get_session_id_for_case = AsyncMock(return_value=None)

    with patch(
        "apps.api.src.services.prediction_service.get_intake_service",
        return_value=intake,
    ):
        await svc.generate_prediction(case_id="c1")

    call_kwargs = svc.prediction_engine.predict.await_args.kwargs
    assert call_kwargs["mode"] == PredictionMode.RAG_ONLY


@pytest.mark.skip(
    reason="Legacy-architecture test: see test_prediction_service_respects_config_default_mode."
)
@pytest.mark.asyncio
async def test_mode_override_beats_config(tmp_path, monkeypatch):
    """Per-call mode_override takes precedence over config default."""
    monkeypatch.setattr(
        "apps.api.src.services.prediction_service.config",
        SimpleNamespace(
            prediction_mode="rag_only",  # config says rag_only
            data_dir=tmp_path,
        ),
    )
    from apps.api.src.services.prediction_service import PredictionService

    svc = PredictionService.__new__(PredictionService)
    fake_kg = SimpleNamespace(nodes=[1], edges=[])
    svc.graph_builder = MagicMock()
    svc.graph_builder.build.return_value = fake_kg
    svc.kg_store = MagicMock()
    svc.predictions_dir = tmp_path / "preds"
    svc.predictions_dir.mkdir()
    svc.dispute_predictions_dir = tmp_path / "disputes"
    svc.dispute_predictions_dir.mkdir()

    fake_pred = SimpleNamespace(
        prediction_id="p2", metadata={},
        model_dump=lambda mode="json": {"prediction_id": "p2"},
    )
    svc.prediction_engine = MagicMock()
    svc.prediction_engine.predict = AsyncMock(return_value=fake_pred)

    intake = MagicMock()
    intake.get_case_file = AsyncMock(return_value=SimpleNamespace(case_id="c2"))
    intake.get_session_id_for_case = AsyncMock(return_value=None)

    with patch(
        "apps.api.src.services.prediction_service.get_intake_service",
        return_value=intake,
    ):
        # Override at call site → KG_ONLY beats config's rag_only
        await svc.generate_prediction(
            case_id="c2", mode_override=PredictionMode.KG_ONLY,
        )

    call_kwargs = svc.prediction_engine.predict.await_args.kwargs
    assert call_kwargs["mode"] == PredictionMode.KG_ONLY
