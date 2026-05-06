"""Tests that the adapter forwards new determination fields when set."""
from decimal import Decimal

import pytest

from eval.adapter import from_prediction_result
from eval.schema import Determination as EvalDetermination
from llm_orchestrator.models.prediction_v2 import (
    Determination as OrchDetermination,
    IssueOutcome,
    IssuePrediction as OrchIssuePrediction,
    OutcomeType,
    PredictionResult,
)
# IssueType lives in prediction_v2 (alias for DisputeIssue).
from llm_orchestrator.models.prediction_v2 import IssueType


def _make_orch_pred(
    *,
    overall_det=None,
    issue_det=None,
    issue_construct=None,
):
    return PredictionResult(
        case_id="test-case",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=0.7,
        tenant_recovery_amount=500.0,
        landlord_recovery_amount=None,
        issue_predictions=[
            OrchIssuePrediction(
                issue_type=IssueType.REPAIRS_DISREPAIR,
                outcome=IssueOutcome.TENANT_WINS,
                raw_confidence=0.7,
                predicted_amount=500.0,
                amount_construct=issue_construct,
                predicted_determination=issue_det,
            )
        ],
        predicted_determination=overall_det,
    )


def test_adapter_passes_overall_determination_through():
    pr = _make_orch_pred(overall_det=OrchDetermination.MALADMINISTRATION)
    p = from_prediction_result(pr)
    assert p.predicted_determination == EvalDetermination.MALADMINISTRATION


def test_adapter_passes_amount_construct_through():
    pr = _make_orch_pred(issue_construct="ordered_now")
    p = from_prediction_result(pr)
    assert p.per_issue[0].amount_construct == "ordered_now"


def test_adapter_handles_missing_determination_cleanly():
    pr = _make_orch_pred()
    p = from_prediction_result(pr)
    assert p.predicted_determination is None
    assert p.per_issue[0].amount_construct is None


def test_adapter_converts_orch_determination_to_eval_determination():
    # Different enum classes; same string value semantics.
    pr = _make_orch_pred(overall_det=OrchDetermination.REASONABLE_REDRESS)
    p = from_prediction_result(pr)
    assert isinstance(p.predicted_determination, EvalDetermination)
    assert p.predicted_determination.value == "reasonable_redress"
