"""Adapter: orchestrator `PredictionResult` → eval `Prediction`.

This is the seam between `packages/llm_orchestrator/` (production runtime) and
`packages/eval/` (evaluation harness). Calibration metrics need P(landlord
wins) per issue and overall; the prediction engine emits "confidence in the
predicted outcome". Conversion happens here.

Mapping policy:
- TENANT_WIN(S) / LANDLORD_WIN(S) / SPLIT → eval.schema.Winner.{TENANT,LANDLORD,SPLIT}
- UNCERTAIN → SPLIT (no eval-schema equivalent; "no clear winner" is the
  conservative read; calibration treats this case as P(landlord)=0.5)
- overall_win_probability:
    * LANDLORD_WIN  → confidence
    * TENANT_WIN    → 1 - confidence
    * SPLIT/UNCERTAIN → 0.5
- total_predicted_gbp = (tenant_recovery or 0) + (landlord_recovery or 0)
- per-issue calibrated_confidence wins over raw_confidence when set
- per-issue predicted_amount=None → Decimal("0")

This module is the only place in `packages/eval/` that imports from
`packages/llm_orchestrator/`. All other eval code stays decoupled.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from eval.metrics.types import IssuePrediction, Prediction
from eval.schema import Winner

if TYPE_CHECKING:
    from llm_orchestrator.models.prediction_v2 import (
        IssuePrediction as OrchestratorIssuePrediction,
        PredictionResult,
    )


def from_prediction_result(result: "PredictionResult") -> Prediction:
    """Adapt orchestrator output for evaluation metrics."""
    overall_winner = _outcome_to_winner(result.overall_outcome.value)
    overall_win_prob = _confidence_to_p_landlord(
        result.overall_outcome.value, float(result.overall_confidence)
    )
    total = Decimal(str(result.tenant_recovery_amount or 0)) + Decimal(
        str(result.landlord_recovery_amount or 0)
    )
    per_issue = [_adapt_issue(ip) for ip in result.issue_predictions]
    return Prediction(
        case_id=result.case_id,
        overall_winner=overall_winner,
        overall_win_probability=overall_win_prob,
        total_predicted_gbp=total,
        per_issue=per_issue,
    )


def _adapt_issue(ip: "OrchestratorIssuePrediction") -> IssuePrediction:
    confidence = (
        float(ip.calibrated_confidence)
        if ip.calibrated_confidence is not None
        else float(ip.raw_confidence)
    )
    win_prob = _confidence_to_p_landlord(ip.outcome.value, confidence)
    amount = (
        Decimal(str(ip.predicted_amount))
        if ip.predicted_amount is not None
        else Decimal("0")
    )
    return IssuePrediction(
        issue=_issue_type_to_str(ip.issue_type),
        predicted_winner=_outcome_to_winner(ip.outcome.value),
        win_probability=win_prob,
        predicted_amount_gbp=amount,
    )


def _outcome_to_winner(outcome_value: str) -> Winner:
    # OutcomeType / IssueOutcome both use the same string suffixes.
    if outcome_value in ("landlord_win", "landlord_wins"):
        return Winner.LANDLORD
    if outcome_value in ("tenant_win", "tenant_wins"):
        return Winner.TENANT
    if outcome_value in ("split", "uncertain"):
        # uncertain → split (no eval-schema "uncertain")
        return Winner.SPLIT
    raise ValueError(f"_outcome_to_winner received unknown outcome {outcome_value!r}")


def _confidence_to_p_landlord(outcome_value: str, confidence: float) -> float:
    if outcome_value in ("landlord_win", "landlord_wins"):
        return confidence
    if outcome_value in ("tenant_win", "tenant_wins"):
        return 1.0 - confidence
    if outcome_value in ("split", "uncertain"):
        # split, uncertain → 0.5 (max uncertainty for binary calibration)
        return 0.5
    raise ValueError(
        f"_confidence_to_p_landlord received unknown outcome {outcome_value!r}"
    )


def _issue_type_to_str(value) -> str:
    """`IssueType` is a Pydantic str-Enum; `.value` gives the canonical key
    that gold cases use. Strings pass through unchanged."""
    return getattr(value, "value", value)
