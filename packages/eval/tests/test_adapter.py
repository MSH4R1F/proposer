"""Tests for eval.adapter — PredictionResult → eval.metrics.Prediction.

The adapter is the seam between `packages/llm_orchestrator/` (production) and
`packages/eval/` (evaluation). It must:

- map OutcomeType / IssueOutcome → eval.schema.Winner
- convert outcome-confidence to P(landlord wins) using outcome direction
- aggregate tenant + landlord recovery amounts into total_predicted_gbp
- preserve case_id and per-issue alignment

The mapping policy is asymmetric on purpose: prediction-engine confidence is
"how sure are we of the predicted outcome", not "what's P(landlord wins)".
The adapter does the conversion so calibration metrics see the right thing.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from eval.adapter import (
    _confidence_to_p_landlord,
    _outcome_to_winner,
    from_prediction_result,
)
from eval.schema import Winner


# Fixture builders — keep PredictionResult construction local so we don't drift
# if the orchestrator schema changes.
def _orchestrator_imports():
    from llm_orchestrator.models.prediction_v2 import (
        IssueOutcome,
        IssuePrediction,
        OutcomeType,
        PredictionResult,
    )

    return IssueOutcome, IssuePrediction, OutcomeType, PredictionResult


def _build_orchestrator_prediction(
    *,
    case_id: str = "case-001",
    overall_outcome=None,
    overall_confidence: float = 0.8,
    tenant_recovery: float | None = None,
    landlord_recovery: float | None = None,
    issue_predictions: list | None = None,
):
    _, _, OutcomeType, PredictionResult = _orchestrator_imports()
    if overall_outcome is None:
        overall_outcome = OutcomeType.LANDLORD_WIN
    return PredictionResult(
        case_id=case_id,
        overall_outcome=overall_outcome,
        overall_confidence=overall_confidence,
        tenant_recovery_amount=tenant_recovery,
        landlord_recovery_amount=landlord_recovery,
        issue_predictions=issue_predictions or [],
    )


def _build_orchestrator_issue(
    *,
    issue_type: str = "deposit_protection",
    outcome=None,
    confidence: float = 0.7,
    predicted_amount: float | None = None,
):
    IssueOutcome, IssuePrediction, _, _ = _orchestrator_imports()
    if outcome is None:
        outcome = IssueOutcome.LANDLORD_WINS
    return IssuePrediction(
        issue_type=issue_type,
        outcome=outcome,
        raw_confidence=confidence,
        predicted_amount=predicted_amount,
    )


class TestOverallOutcomeMapping:
    def test_landlord_win_maps_to_landlord_winner(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.LANDLORD_WIN, overall_confidence=0.8
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_winner is Winner.LANDLORD

    def test_tenant_win_maps_to_tenant_winner(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.TENANT_WIN, overall_confidence=0.8
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_winner is Winner.TENANT

    def test_split_maps_to_split_winner(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.SPLIT, overall_confidence=0.6
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_winner is Winner.SPLIT

    def test_uncertain_collapses_to_split(self):
        """UNCERTAIN has no eval-schema equivalent; SPLIT is the conservative
        ('no clear winner') mapping. Calibration metrics still treat the
        case as P(landlord)=0.5, i.e. maximum uncertainty."""
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.UNCERTAIN, overall_confidence=0.4
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_winner is Winner.SPLIT

    def test_unknown_outcome_raises_clear_error(self):
        with pytest.raises(ValueError, match="_outcome_to_winner.*mystery_outcome"):
            _outcome_to_winner("mystery_outcome")


class TestOverallConfidenceConversion:
    """`overall_confidence` is confidence in the *predicted outcome*. Convert
    to P(landlord wins) for calibration metrics."""

    def test_landlord_win_keeps_confidence_as_p_landlord(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.LANDLORD_WIN, overall_confidence=0.83
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_win_probability == pytest.approx(0.83)

    def test_tenant_win_inverts_confidence(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.TENANT_WIN, overall_confidence=0.83
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_win_probability == pytest.approx(1 - 0.83)

    def test_split_collapses_to_half(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.SPLIT, overall_confidence=0.7
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_win_probability == pytest.approx(0.5)

    def test_uncertain_collapses_to_half(self):
        _, _, OutcomeType, _ = _orchestrator_imports()
        result = _build_orchestrator_prediction(
            overall_outcome=OutcomeType.UNCERTAIN, overall_confidence=0.4
        )
        prediction = from_prediction_result(result)
        assert prediction.overall_win_probability == pytest.approx(0.5)

    def test_unknown_outcome_probability_raises_clear_error(self):
        with pytest.raises(
            ValueError, match="_confidence_to_p_landlord.*mystery_outcome"
        ):
            _confidence_to_p_landlord("mystery_outcome", 0.8)


class TestAmountAggregation:
    def test_sums_tenant_and_landlord_recovery(self):
        result = _build_orchestrator_prediction(
            tenant_recovery=400.0, landlord_recovery=600.0
        )
        prediction = from_prediction_result(result)
        assert prediction.total_predicted_gbp == Decimal("1000.00")

    def test_treats_none_as_zero(self):
        result = _build_orchestrator_prediction(
            tenant_recovery=None, landlord_recovery=600.0
        )
        prediction = from_prediction_result(result)
        assert prediction.total_predicted_gbp == Decimal("600.00")

    def test_both_none_yields_unknown_amount(self):
        result = _build_orchestrator_prediction(
            tenant_recovery=None, landlord_recovery=None
        )
        prediction = from_prediction_result(result)
        assert prediction.total_predicted_gbp is None


class TestPerIssueMapping:
    def test_per_issue_count_matches(self):
        IssueOutcome, _, _, _ = _orchestrator_imports()
        issues = [
            _build_orchestrator_issue(
                issue_type="cleaning",
                outcome=IssueOutcome.LANDLORD_WINS,
                confidence=0.7,
                predicted_amount=120.0,
            ),
            _build_orchestrator_issue(
                issue_type="damage",
                outcome=IssueOutcome.TENANT_WINS,
                confidence=0.6,
                predicted_amount=50.0,
            ),
        ]
        result = _build_orchestrator_prediction(issue_predictions=issues)
        prediction = from_prediction_result(result)
        assert len(prediction.per_issue) == 2

    def test_per_issue_winner_and_probability_per_outcome(self):
        IssueOutcome, _, _, _ = _orchestrator_imports()
        issues = [
            _build_orchestrator_issue(
                issue_type="cleaning",
                outcome=IssueOutcome.LANDLORD_WINS,
                confidence=0.9,
                predicted_amount=120.0,
            ),
            _build_orchestrator_issue(
                issue_type="damage",
                outcome=IssueOutcome.TENANT_WINS,
                confidence=0.9,
                predicted_amount=0.0,
            ),
            _build_orchestrator_issue(
                issue_type="rent_arrears",
                outcome=IssueOutcome.SPLIT,
                confidence=0.7,
                predicted_amount=50.0,
            ),
            _build_orchestrator_issue(
                issue_type="garden",
                outcome=IssueOutcome.UNCERTAIN,
                confidence=0.4,
                predicted_amount=None,
            ),
        ]
        result = _build_orchestrator_prediction(issue_predictions=issues)
        prediction = from_prediction_result(result)

        winners = {ip.issue: ip.predicted_winner for ip in prediction.per_issue}
        probs = {ip.issue: ip.win_probability for ip in prediction.per_issue}

        assert winners["cleaning"] is Winner.LANDLORD
        assert probs["cleaning"] == pytest.approx(0.9)
        assert winners["damages"] is Winner.TENANT
        assert probs["damages"] == pytest.approx(1 - 0.9)
        assert winners["rent_arrears"] is Winner.SPLIT
        assert probs["rent_arrears"] == pytest.approx(0.5)
        assert winners["garden"] is Winner.SPLIT
        assert probs["garden"] == pytest.approx(0.5)

    def test_per_issue_amount_none_stays_unknown(self):
        IssueOutcome, _, _, _ = _orchestrator_imports()
        issues = [
            _build_orchestrator_issue(
                issue_type="cleaning",
                outcome=IssueOutcome.LANDLORD_WINS,
                confidence=0.7,
                predicted_amount=None,
            ),
        ]
        result = _build_orchestrator_prediction(issue_predictions=issues)
        prediction = from_prediction_result(result)
        assert prediction.per_issue[0].predicted_amount_gbp is None

    def test_per_issue_normalises_orchestrator_issue_to_eval_claim_type(self):
        """The metrics join per-issue predictions to gold by eval ClaimType."""
        IssueOutcome, _, _, _ = _orchestrator_imports()
        issues = [
            _build_orchestrator_issue(
                issue_type="deposit_protection",
                outcome=IssueOutcome.LANDLORD_WINS,
                confidence=0.6,
                predicted_amount=0.0,
            ),
        ]
        result = _build_orchestrator_prediction(issue_predictions=issues)
        prediction = from_prediction_result(result)
        assert prediction.per_issue[0].issue == "deposit_non_protection"

    def test_unmappable_orchestrator_issue_passes_through(self):
        """Orchestrator-only values remain visible and score as missing."""
        IssueOutcome, _, _, _ = _orchestrator_imports()
        issues = [
            _build_orchestrator_issue(
                issue_type="garden",
                outcome=IssueOutcome.LANDLORD_WINS,
                confidence=0.6,
                predicted_amount=0.0,
            ),
        ]
        result = _build_orchestrator_prediction(issue_predictions=issues)
        prediction = from_prediction_result(result)
        assert prediction.per_issue[0].issue == "garden"


class TestCalibratedConfidencePreference:
    """When `calibrated_confidence` is set on a per-issue prediction it should
    win over `raw_confidence` (calibration is the whole point of having it)."""

    def test_calibrated_confidence_overrides_raw(self):
        IssueOutcome, IssuePrediction, _, _ = _orchestrator_imports()
        issue = IssuePrediction(
            issue_type="cleaning",
            outcome=IssueOutcome.LANDLORD_WINS,
            raw_confidence=0.9,
            calibrated_confidence=0.65,
            predicted_amount=100.0,
        )
        result = _build_orchestrator_prediction(issue_predictions=[issue])
        prediction = from_prediction_result(result)
        # Calibrated 0.65 wins → P(landlord) = 0.65, not 0.9
        assert prediction.per_issue[0].win_probability == pytest.approx(0.65)


class TestCaseIdPreserved:
    def test_case_id_round_trip(self):
        result = _build_orchestrator_prediction(case_id="HOU-2024-001")
        prediction = from_prediction_result(result)
        assert prediction.case_id == "HOU-2024-001"
