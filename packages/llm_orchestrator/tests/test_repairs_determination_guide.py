"""The repairs prompt must define the determination classes, not just name them."""
from llm_orchestrator.pipeline.issue_predictor import (
    REPAIRS_DETERMINATION_GUIDE,
    REPAIRS_RAG_CALIBRATION_ADDENDUM,
    _REPAIRS_NO_RAG_SYSTEM_PROMPT,
)


def test_guide_defines_every_determination_class():
    for cls in (
        "no_maladministration", "service_failure", "maladministration",
        "severe_maladministration", "reasonable_redress",
        "resolved_with_intervention", "outside_jurisdiction",
    ):
        assert cls in REPAIRS_DETERMINATION_GUIDE


def test_guide_contains_discriminating_criteria():
    assert "BEFORE the Ombudsman" in REPAIRS_DETERMINATION_GUIDE  # reasonable_redress test
    assert "AGGRAVATORS" in REPAIRS_DETERMINATION_GUIDE           # severe test
    assert "no_maladministration" in REPAIRS_DETERMINATION_GUIDE  # class must be present
    assert "Base rates" in REPAIRS_DETERMINATION_GUIDE            # base-rate calibration added 2026-06-10
    assert "previously_offered" in REPAIRS_DETERMINATION_GUIDE    # RR amount semantics added 2026-06-10


def test_no_rag_system_prompt_includes_guide():
    assert REPAIRS_DETERMINATION_GUIDE in _REPAIRS_NO_RAG_SYSTEM_PROMPT


def test_rag_calibration_addendum_content():
    # Confidence semantics: probability of the predicted outcome, not citation coverage.
    assert "raw_confidence" in REPAIRS_RAG_CALIBRATION_ADDENDUM
    assert "subjective probability" in REPAIRS_RAG_CALIBRATION_ADDENDUM
    # Amount requirement + RR prior-offer semantics.
    assert "predicted_amount is REQUIRED" in REPAIRS_RAG_CALIBRATION_ADDENDUM
    assert "prior offer" in REPAIRS_RAG_CALIBRATION_ADDENDUM


def test_no_rag_system_prompt_excludes_rag_addendum():
    # The addendum targets the retrieval-bearing path only; no-RAG modes have
    # their own flag-gated amount clause (STREAM_C_NO_RAG_PREDICT_AMOUNTS).
    assert REPAIRS_RAG_CALIBRATION_ADDENDUM not in _REPAIRS_NO_RAG_SYSTEM_PROMPT
