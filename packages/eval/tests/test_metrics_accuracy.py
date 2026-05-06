"""Tests for packages/eval/metrics/accuracy.py."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from eval.tests.conftest import gold_case_dict  # type: ignore[import-not-found]


def _gold_with_outcome(case_id: str, *, per_issue: list, total: str = "100.00",
                       overall: str = "tenant", apportioned: bool = True):
    """Build a GoldCase with a custom ground_truth_outcome."""
    from eval.schema import GoldCase
    case = gold_case_dict(case_id=case_id)
    case["claimed_amounts"] = [
        {"issue": pi["issue"], "amount_gbp": "100.00", "by_party": "landlord"}
        for pi in per_issue
    ] or [{"issue": "primary", "amount_gbp": "100.00", "by_party": "landlord"}]
    case["disputed_amount_gbp"] = "100.00"
    case["case_size"] = "small"
    if apportioned:
        case["ground_truth_outcome"] = {
            "overall_winner": overall,
            "total_awarded_gbp": total,
            "per_issue": per_issue,
        }
    else:
        case["ground_truth_outcome"] = {
            "overall_winner": overall,
            "total_awarded_gbp": total,
            "per_issue": [],
            "unapportioned_reason": "Tribunal gave a global figure.",
        }
    return GoldCase.model_validate(case)


def _pred(case_id: str, *, per_issue: list, total: str = "100.00",
          overall: str = "tenant"):
    from eval.metrics import IssuePrediction, Prediction
    from eval.schema import Winner
    return Prediction(
        case_id=case_id,
        overall_winner=Winner(overall),
        overall_win_probability=0.5,
        total_predicted_gbp=Decimal(total),
        per_issue=[
            IssuePrediction(
                issue=pi["issue"],
                predicted_winner=Winner(pi["winner"]),
                win_probability=pi.get("p", 0.5),
                predicted_amount_gbp=Decimal(pi.get("amount_gbp", "100.00")),
            )
            for pi in per_issue
        ],
    )


class TestIssueWinnerAccuracy:
    def test_perfect_predictions_score_one(self):
        from eval.metrics import issue_winner_accuracy
        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "50.00"},
                {"issue": "y", "winner": "tenant", "awarded_gbp": "50.00"},
            ]),
        ]
        preds = [
            _pred("A", per_issue=[
                {"issue": "x", "winner": "tenant"},
                {"issue": "y", "winner": "tenant"},
            ]),
        ]
        assert issue_winner_accuracy(gold, preds) == 1.0

    def test_all_wrong_score_zero(self):
        from eval.metrics import issue_winner_accuracy
        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
            ]),
        ]
        preds = [
            _pred("A", per_issue=[
                {"issue": "x", "winner": "landlord"},
            ], overall="landlord"),
        ]
        assert issue_winner_accuracy(gold, preds) == 0.0

    def test_partial_score(self):
        from eval.metrics import issue_winner_accuracy
        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "50.00"},
                {"issue": "y", "winner": "landlord", "awarded_gbp": "50.00"},
            ], overall="split"),
        ]
        preds = [
            _pred("A", per_issue=[
                {"issue": "x", "winner": "tenant"},
                {"issue": "y", "winner": "tenant"},  # wrong
            ], overall="split"),
        ]
        assert issue_winner_accuracy(gold, preds) == 0.5

    def test_missing_per_issue_prediction_counts_wrong(self):
        from eval.metrics import issue_winner_accuracy
        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "50.00"},
                {"issue": "y", "winner": "tenant", "awarded_gbp": "50.00"},
            ]),
        ]
        preds = [
            _pred("A", per_issue=[
                {"issue": "x", "winner": "tenant"},
                # missing y
            ]),
        ]
        # 1 of 2 issues correctly predicted (the missing one counts as wrong)
        assert issue_winner_accuracy(gold, preds) == 0.5

    def test_unapportioned_uses_overall_winner(self):
        from eval.metrics import issue_winner_accuracy
        gold = [
            _gold_with_outcome("A", per_issue=[], total="100.00",
                               overall="split", apportioned=False),
        ]
        preds_match = [_pred("A", per_issue=[], overall="split")]
        preds_miss = [_pred("A", per_issue=[], overall="tenant")]
        assert issue_winner_accuracy(gold, preds_match) == 1.0
        assert issue_winner_accuracy(gold, preds_miss) == 0.0

    def test_length_mismatch_raises(self):
        from eval.metrics import issue_winner_accuracy
        with pytest.raises(ValueError, match="length mismatch"):
            issue_winner_accuracy(
                [_gold_with_outcome("A", per_issue=[
                    {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
                ])],
                [],
            )

    def test_case_id_mismatch_raises(self):
        from eval.metrics import issue_winner_accuracy
        gold = [_gold_with_outcome("A", per_issue=[
            {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
        ])]
        preds = [_pred("B", per_issue=[{"issue": "x", "winner": "tenant"}])]
        with pytest.raises(ValueError, match="case_id mismatch"):
            issue_winner_accuracy(gold, preds)


class TestAmountWithinThreshold:
    def test_within_default_threshold(self):
        from eval.metrics import amount_within_threshold
        gold = [_gold_with_outcome("A", per_issue=[
            {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
        ], total="100.00")]
        # Predicted £110 vs actual £100 -> 10% off -> within 20% default
        preds = [_pred("A", per_issue=[{"issue": "x", "winner": "tenant"}],
                       total="110.00")]
        assert amount_within_threshold(gold, preds) == 1.0

    def test_outside_threshold(self):
        from eval.metrics import amount_within_threshold
        gold = [_gold_with_outcome("A", per_issue=[
            {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
        ], total="100.00")]
        # Predicted £150 vs actual £100 -> 50% off -> outside 20%
        preds = [_pred("A", per_issue=[{"issue": "x", "winner": "tenant"}],
                       total="150.00")]
        assert amount_within_threshold(gold, preds) == 0.0

    def test_zero_actual_zero_predicted(self):
        from eval.metrics import amount_within_threshold
        gold = [_gold_with_outcome("A", per_issue=[
            {"issue": "x", "winner": "tenant", "awarded_gbp": "0.00"},
        ], total="0.00")]
        preds_match = [_pred("A", per_issue=[{"issue": "x", "winner": "tenant"}],
                             total="0.00")]
        preds_miss = [_pred("A", per_issue=[{"issue": "x", "winner": "tenant"}],
                            total="50.00")]
        assert amount_within_threshold(gold, preds_match) == 1.0
        assert amount_within_threshold(gold, preds_miss) == 0.0

    def test_partial(self):
        from eval.metrics import amount_within_threshold
        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
            ], total="100.00"),
            _gold_with_outcome("B", per_issue=[
                {"issue": "y", "winner": "tenant", "awarded_gbp": "200.00"},
            ], total="200.00"),
        ]
        preds = [
            _pred("A", per_issue=[{"issue": "x", "winner": "tenant"}], total="100.00"),  # exact
            _pred("B", per_issue=[{"issue": "y", "winner": "tenant"}], total="350.00"),  # 75% off
        ]
        assert amount_within_threshold(gold, preds) == 0.5

    def test_custom_threshold(self):
        from eval.metrics import amount_within_threshold
        gold = [_gold_with_outcome("A", per_issue=[
            {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
        ], total="100.00")]
        preds = [_pred("A", per_issue=[{"issue": "x", "winner": "tenant"}],
                       total="140.00")]
        # 40% error: outside 20% default, inside 50% custom
        assert amount_within_threshold(gold, preds, threshold_pct=0.20) == 0.0
        assert amount_within_threshold(gold, preds, threshold_pct=0.50) == 1.0

    def test_negative_threshold_raises(self):
        from eval.metrics import amount_within_threshold
        gold = [_gold_with_outcome("A", per_issue=[
            {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
        ], total="100.00")]
        preds = [_pred("A", per_issue=[{"issue": "x", "winner": "tenant"}], total="100.00")]
        with pytest.raises(ValueError):
            amount_within_threshold(gold, preds, threshold_pct=-0.1)

    def test_empty_input_returns_zero(self):
        from eval.metrics import amount_within_threshold
        assert amount_within_threshold([], []) == 0.0


class TestRicherAmountMetrics:
    def test_amount_error_metrics_expose_scale_and_bias(self):
        from eval.metrics import (
            amount_mae_gbp,
            amount_mean_signed_error_gbp,
            amount_median_absolute_error_gbp,
            amount_within_absolute_threshold,
            amount_within_threshold,
        )

        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
            ], total="100.00"),
            _gold_with_outcome("B", per_issue=[
                {"issue": "y", "winner": "tenant", "awarded_gbp": "200.00"},
            ], total="200.00"),
            _gold_with_outcome("C", per_issue=[
                {"issue": "z", "winner": "tenant", "awarded_gbp": "0.00"},
            ], total="0.00"),
        ]
        preds = [
            _pred("A", per_issue=[{"issue": "x", "winner": "tenant"}], total="110.00"),
            _pred("B", per_issue=[{"issue": "y", "winner": "tenant"}], total="150.00"),
            _pred("C", per_issue=[{"issue": "z", "winner": "tenant"}], total="0.00"),
        ]

        assert amount_mae_gbp(gold, preds) == pytest.approx(20.0)
        assert amount_median_absolute_error_gbp(gold, preds) == pytest.approx(10.0)
        assert amount_mean_signed_error_gbp(gold, preds) == pytest.approx(-40 / 3)
        assert amount_within_absolute_threshold(gold, preds, threshold_gbp=100) == 1.0
        assert amount_within_threshold(gold, preds, threshold_pct=0.20) == pytest.approx(2 / 3)

    def test_missing_predicted_amount_is_explicitly_counted(self):
        from eval.metrics import (
            amount_coverage,
            amount_mae_gbp,
            amount_within_absolute_threshold,
        )

        gold = [
            _gold_with_outcome("A", per_issue=[
                {"issue": "x", "winner": "tenant", "awarded_gbp": "100.00"},
            ], total="100.00"),
            _gold_with_outcome("B", per_issue=[
                {"issue": "y", "winner": "tenant", "awarded_gbp": "200.00"},
            ], total="200.00"),
        ]
        preds = [
            SimpleNamespace(case_id="A", total_predicted_gbp=None),
            SimpleNamespace(case_id="B", total_predicted_gbp=Decimal("220.00")),
        ]

        assert amount_coverage(gold, preds) == {
            "n_cases": 2,
            "n_gold_amount_available": 2,
            "n_predicted_amount_available": 1,
            "n_evaluable": 1,
            "missing_gold_amount": 0,
            "missing_predicted_amount": 1,
        }
        assert amount_mae_gbp(gold, preds) == pytest.approx(20.0)
        assert amount_within_absolute_threshold(gold, preds, threshold_gbp=100) == 0.5

    @pytest.mark.parametrize("threshold", ["£100", None])
    def test_absolute_threshold_invalid_input_raises_value_error(self, threshold):
        from eval.metrics import amount_within_absolute_threshold

        with pytest.raises(ValueError, match="threshold_gbp"):
            amount_within_absolute_threshold([], [], threshold_gbp=threshold)
