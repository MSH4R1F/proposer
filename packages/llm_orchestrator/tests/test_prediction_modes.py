"""Tests for the PredictionMode ablation seam (SHA-33)."""

from llm_orchestrator.models.prediction_v2 import PredictionMode


def test_prediction_mode_has_four_modes():
    assert {m.value for m in PredictionMode} == {
        "rag_only",
        "kg_only",
        "hybrid",
        "llm_only",
    }


def test_prediction_mode_hybrid_value():
    assert PredictionMode.HYBRID.value == "hybrid"
    assert PredictionMode.RAG_ONLY.value == "rag_only"
    assert PredictionMode.KG_ONLY.value == "kg_only"
    assert PredictionMode.LLM_ONLY.value == "llm_only"
