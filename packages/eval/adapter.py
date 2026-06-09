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
- total_predicted_gbp = null when neither top-level recovery field is set;
  otherwise `(tenant_recovery or 0) + (landlord_recovery or 0)`
- per-issue calibrated_confidence wins over raw_confidence when set
- per-issue predicted_amount=None remains null so amount coverage can
  distinguish "model predicted £0" from "model omitted an amount"
- per-issue issue labels are normalised from orchestrator `DisputeIssue`
  values into eval `ClaimType` values where a clean mapping exists

This module imports orchestrator types only for adaptation; it does not call
the prediction pipeline.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from eval.issue_alignment import UnmappableIssue, orchestrator_to_eval
from eval.metrics.types import IssuePrediction, Prediction
from eval.schema import Winner

if TYPE_CHECKING:
    from llm_orchestrator.models.prediction_v2 import (
        IssuePrediction as OrchestratorIssuePrediction,
        PredictionResult,
    )


def _adapt_determination(orch_det):
    """Convert orchestrator-side Determination to eval-side Determination.

    The two enums are intentional duplicates (different packages, same string
    values) so packages/eval/ does not import from packages/llm_orchestrator/.
    String-value bridging keeps both sides independent.
    """
    if orch_det is None:
        return None
    from eval.schema import Determination as EvalDetermination
    return EvalDetermination(orch_det.value)


def from_prediction_result(result: "PredictionResult") -> Prediction:
    """Adapt orchestrator output for evaluation metrics."""
    overall_winner = _outcome_to_winner(result.overall_outcome.value)
    overall_win_prob = _confidence_to_p_landlord(
        result.overall_outcome.value, float(result.overall_confidence)
    )
    per_issue = [_adapt_issue(ip) for ip in result.issue_predictions]
    has_top_level_amount = (
        result.tenant_recovery_amount is not None
        or result.landlord_recovery_amount is not None
    )
    total = (
        Decimal(str(result.tenant_recovery_amount or 0))
        + Decimal(str(result.landlord_recovery_amount or 0))
        if has_top_level_amount
        else None
    )
    return Prediction(
        case_id=result.case_id,
        overall_winner=overall_winner,
        overall_win_probability=overall_win_prob,
        total_predicted_gbp=total,
        per_issue=per_issue,
        abstained=result.overall_outcome.value == "uncertain",
        predicted_determination=_adapt_determination(
            getattr(result, "predicted_determination", None)
        ),
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
        else None
    )
    return IssuePrediction(
        issue=_issue_type_to_str(ip.issue_type),
        predicted_winner=_outcome_to_winner(ip.outcome.value),
        win_probability=win_prob,
        predicted_amount_gbp=amount,
        abstained=ip.outcome.value == "uncertain",
        amount_construct=getattr(ip, "amount_construct", None),
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
        # Confidence below 0.5 means "weakly landlord", not "actually tenant":
        # the probability must not cross to the other side of the class label.
        return max(confidence, 0.5)
    if outcome_value in ("tenant_win", "tenant_wins"):
        return min(1.0 - confidence, 0.5)
    if outcome_value in ("split", "uncertain"):
        # split, uncertain → 0.5 (max uncertainty for binary calibration)
        return 0.5
    raise ValueError(
        f"_confidence_to_p_landlord received unknown outcome {outcome_value!r}"
    )


def _issue_type_to_str(value) -> str:
    """Return the eval/gold issue key when the orchestrator issue maps cleanly.

    `PredictionResult` uses orchestrator `DisputeIssue` labels (`damage`,
    `deposit_protection`). Gold cases use eval `ClaimType` labels (`damages`,
    `deposit_non_protection`). Normalising here prevents mapped predictions
    from being counted as missing by issue-level metrics. Orchestrator-only
    values pass through and will be scored as missing when no gold label exists.
    """
    raw = getattr(value, "value", value)
    try:
        return orchestrator_to_eval(raw).value
    except UnmappableIssue:
        return str(raw)
