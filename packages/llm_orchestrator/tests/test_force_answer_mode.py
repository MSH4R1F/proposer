"""Tests for STREAM_C_FORCE_ANSWER (recovery plan Task 4).

When the flag is on (default), the IRAC JSON schema must omit "uncertain"
from the allowed outcome enum and any IssuePrediction that still ends up
with outcome=UNCERTAIN must be remapped to SPLIT with raw_confidence
capped at 0.50, evidence_strength=INSUFFICIENT, and a "[forced-answer
fallback" prefix on the reasoning so the remap is auditable.
"""

from __future__ import annotations

import pytest

from llm_orchestrator.models.prediction_v2 import (
    EvidenceStrength,
    IssueOutcome,
    IssuePrediction,
    IssueType,
)
from llm_orchestrator.pipeline.issue_predictor import IssuePredictor
from llm_orchestrator.prompts.prediction_v2 import build_irac_json_schema


@pytest.fixture(autouse=True)
def _clean_force_answer_env(monkeypatch):
    monkeypatch.delenv("STREAM_C_FORCE_ANSWER", raising=False)
    yield


def _make_uncertain_prediction(
    *,
    raw_confidence: float = 0.30,
    reasoning: str = "Original reasoning.",
    evidence_strength: EvidenceStrength = EvidenceStrength.MODERATE,
) -> IssuePrediction:
    return IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="Cleaning dispute",
        outcome=IssueOutcome.UNCERTAIN,
        raw_confidence=raw_confidence,
        reasoning=reasoning,
        evidence_strength=evidence_strength,
        data_completeness_impact="OK",
    )


def _make_concrete_prediction(
    *,
    outcome: IssueOutcome = IssueOutcome.TENANT_WINS,
    raw_confidence: float = 0.85,
) -> IssuePrediction:
    return IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="Cleaning dispute",
        outcome=outcome,
        raw_confidence=raw_confidence,
        reasoning="Concrete reasoning.",
        evidence_strength=EvidenceStrength.STRONG,
        data_completeness_impact="OK",
    )


# ---------------------------------------------------------------------------
# 1. UNCERTAIN → SPLIT remap when flag on
# ---------------------------------------------------------------------------


def test_force_answer_remaps_uncertain_to_split(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    pred = _make_uncertain_prediction(
        raw_confidence=0.85,
        reasoning="LLM was unsure.",
        evidence_strength=EvidenceStrength.MODERATE,
    )
    out = IssuePredictor._apply_forced_answer(pred)
    assert out.outcome == IssueOutcome.SPLIT
    assert out.raw_confidence <= 0.50
    assert out.evidence_strength == EvidenceStrength.INSUFFICIENT


# ---------------------------------------------------------------------------
# 2. Flag off: uncertain stays
# ---------------------------------------------------------------------------


def test_force_answer_disabled_keeps_uncertain(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "0")
    pred = _make_uncertain_prediction(raw_confidence=0.30)
    out = IssuePredictor._apply_forced_answer(pred)
    assert out.outcome == IssueOutcome.UNCERTAIN
    assert out.raw_confidence == pytest.approx(0.30)
    assert out.evidence_strength == EvidenceStrength.MODERATE
    assert "forced-answer fallback" not in (out.reasoning or "")


# ---------------------------------------------------------------------------
# 3. Concrete outcomes are unchanged
# ---------------------------------------------------------------------------


def test_force_answer_does_not_change_concrete_outcomes(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    for outcome in (
        IssueOutcome.TENANT_WINS,
        IssueOutcome.LANDLORD_WINS,
        IssueOutcome.SPLIT,
    ):
        pred = _make_concrete_prediction(outcome=outcome, raw_confidence=0.85)
        out = IssuePredictor._apply_forced_answer(pred)
        assert out.outcome == outcome
        assert out.raw_confidence == pytest.approx(0.85)
        assert out.evidence_strength == EvidenceStrength.STRONG
        assert "forced-answer fallback" not in (out.reasoning or "")


# ---------------------------------------------------------------------------
# 4. Schema text excludes "uncertain" outcome enum when forced
# ---------------------------------------------------------------------------


def test_build_irac_json_schema_excludes_uncertain_when_forced(monkeypatch):
    """Under STREAM_C_FORCE_ANSWER=1, the schema's outcome enum line must
    not list "uncertain" as an allowed value, and the schema must contain
    explicit "Do not answer uncertain" instruction."""
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    schema_text = build_irac_json_schema()
    # The enum constraint line listing the allowed outcome values.
    assert (
        '"outcome" MUST be exactly one of: "tenant_wins", "landlord_wins", "split"'
        in schema_text
    )
    # The legacy 4-value enum line must NOT appear.
    assert (
        '"outcome" MUST be exactly one of: "tenant_wins", "landlord_wins", "split", "uncertain"'
        not in schema_text
    )
    # Explicit instruction surfaced.
    assert "Do not answer uncertain" in schema_text


# ---------------------------------------------------------------------------
# 5. Schema text keeps "uncertain" when flag off
# ---------------------------------------------------------------------------


def test_build_irac_json_schema_keeps_uncertain_when_unforced(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "0")
    schema_text = build_irac_json_schema()
    assert (
        '"outcome" MUST be exactly one of: "tenant_wins", "landlord_wins", "split", "uncertain"'
        in schema_text
    )


# ---------------------------------------------------------------------------
# 6. Fallback marker is present in reasoning so analysis can spot remaps
# ---------------------------------------------------------------------------


def test_force_answer_fallback_reasoning_marker(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    pred = _make_uncertain_prediction(reasoning="Insufficient info.")
    out = IssuePredictor._apply_forced_answer(pred)
    assert out.reasoning is not None
    assert out.reasoning.startswith("[forced-answer fallback")
    # Original reasoning preserved after the prefix.
    assert "Insufficient info." in out.reasoning


# ---------------------------------------------------------------------------
# 7. Default-on: when env var unset, behaviour matches forced (Hard
# Constraint 1 from the recovery plan).
# ---------------------------------------------------------------------------


def test_force_answer_default_on(monkeypatch):
    monkeypatch.delenv("STREAM_C_FORCE_ANSWER", raising=False)
    pred = _make_uncertain_prediction(raw_confidence=0.80)
    out = IssuePredictor._apply_forced_answer(pred)
    assert out.outcome == IssueOutcome.SPLIT
    assert out.raw_confidence == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# 8. Cap is a ceiling, not a floor: low-confidence stays low.
# ---------------------------------------------------------------------------


def test_force_answer_low_confidence_unchanged(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    pred = _make_uncertain_prediction(raw_confidence=0.10)
    out = IssuePredictor._apply_forced_answer(pred)
    assert out.outcome == IssueOutcome.SPLIT
    assert out.raw_confidence == pytest.approx(0.10)
