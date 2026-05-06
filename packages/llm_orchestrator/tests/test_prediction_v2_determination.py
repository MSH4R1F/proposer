"""Tests for the orchestrator-side Determination + amount_construct fields."""
import pytest

from llm_orchestrator.models.prediction_v2 import (
    Determination,
    IssueOutcome,
    IssuePrediction,
    IssueType,
    OutcomeType,
    PredictionResult,
)


def test_determination_enum_values():
    assert {d.value for d in Determination} == {
        "maladministration",
        "severe_maladministration",
        "service_failure",
        "reasonable_redress",
        "no_maladministration",
        "resolved_with_intervention",
        "outside_jurisdiction",
    }


def test_issue_prediction_carries_amount_construct():
    ip = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
        predicted_amount=500.0,
        amount_construct="ordered_now",
    )
    assert ip.amount_construct == "ordered_now"


def test_issue_prediction_default_amount_construct_is_none():
    ip = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
    )
    assert ip.amount_construct is None


def test_issue_prediction_invalid_amount_construct_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        IssuePrediction(
            issue_type=IssueType.REPAIRS_DISREPAIR,
            outcome=IssueOutcome.TENANT_WINS,
            raw_confidence=0.7,
            amount_construct="bogus_value",
        )


def test_issue_prediction_carries_predicted_determination():
    ip = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
        predicted_determination=Determination.MALADMINISTRATION,
    )
    assert ip.predicted_determination == Determination.MALADMINISTRATION


def test_prediction_result_carries_predicted_determination():
    pr = PredictionResult(
        case_id="x",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=0.7,
        issue_predictions=[],
        predicted_determination=Determination.MALADMINISTRATION,
    )
    assert pr.predicted_determination == Determination.MALADMINISTRATION


def test_prediction_result_default_predicted_determination_is_none():
    pr = PredictionResult(
        case_id="x",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=0.7,
        issue_predictions=[],
    )
    assert pr.predicted_determination is None
