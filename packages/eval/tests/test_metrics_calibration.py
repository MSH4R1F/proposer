"""Tests for packages/eval/metrics/calibration.py (SHA-30)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from eval.tests.conftest import gold_case_dict  # type: ignore[import-not-found]


def _make(case_id: str, *, issue_winner: str, predicted_p: float):
    """Build aligned gold/prediction with one issue."""
    from eval.schema import GoldCase, Winner
    from eval.metrics import IssuePrediction, Prediction
    case = gold_case_dict(case_id=case_id)
    case["claimed_amounts"] = [
        {"issue": "x", "amount_gbp": "100.00", "by_party": "landlord"}
    ]
    case["disputed_amount_gbp"] = "100.00"
    case["case_size"] = "small"
    case["ground_truth_outcome"] = {
        "overall_winner": issue_winner,
        "total_awarded_gbp": "100.00",
        "per_issue": [
            {"issue": "x", "winner": issue_winner, "awarded_gbp": "100.00"},
        ],
    }
    g = GoldCase.model_validate(case)
    p = Prediction(
        case_id=case_id,
        overall_winner=Winner(issue_winner),
        overall_win_probability=predicted_p,
        total_predicted_gbp=Decimal("100.00"),
        per_issue=[
            IssuePrediction(
                issue="x",
                predicted_winner=Winner(issue_winner),
                win_probability=predicted_p,
                predicted_amount_gbp=Decimal("100.00"),
            )
        ],
    )
    return g, p


class TestBrierScore:
    def test_perfect_predictions_zero(self):
        from eval.metrics import brier_score
        g1, p1 = _make("A", issue_winner="landlord", predicted_p=1.0)
        g2, p2 = _make("B", issue_winner="tenant", predicted_p=0.0)
        assert brier_score([g1, g2], [p1, p2]) == 0.0

    def test_coin_flip_quarter(self):
        from eval.metrics import brier_score
        g1, p1 = _make("A", issue_winner="landlord", predicted_p=0.5)
        g2, p2 = _make("B", issue_winner="tenant", predicted_p=0.5)
        # (0.5 - 1)^2 = 0.25; (0.5 - 0)^2 = 0.25; mean = 0.25
        assert brier_score([g1, g2], [p1, p2]) == 0.25

    def test_hand_computed(self):
        from eval.metrics import brier_score
        # 3 issues with (P, actual) = [(0.8, 1), (0.2, 0), (0.5, 1)]
        # squared errors: 0.04, 0.04, 0.25; mean = 0.11
        g1, p1 = _make("A", issue_winner="landlord", predicted_p=0.8)
        g2, p2 = _make("B", issue_winner="tenant", predicted_p=0.2)
        g3, p3 = _make("C", issue_winner="landlord", predicted_p=0.5)
        assert abs(brier_score([g1, g2, g3], [p1, p2, p3]) - 0.11) < 1e-9

    def test_empty_input_raises(self):
        from eval.metrics import brier_score
        with pytest.raises(ValueError):
            brier_score([], [])

    def test_length_mismatch_raises(self):
        from eval.metrics import brier_score
        g, p = _make("A", issue_winner="landlord", predicted_p=0.5)
        with pytest.raises(ValueError, match="length mismatch"):
            brier_score([g, g], [p])


class TestExpectedCalibrationError:
    def test_well_calibrated_low_ece(self):
        from eval.metrics import expected_calibration_error
        # 100 cases at P=0.5; half landlord, half tenant -> bin_accuracy 0.5
        # matches bin_confidence 0.5 -> ECE = 0
        gs, ps = [], []
        for i in range(50):
            g, p = _make(f"L{i}", issue_winner="landlord", predicted_p=0.5)
            gs.append(g); ps.append(p)
        for i in range(50):
            g, p = _make(f"T{i}", issue_winner="tenant", predicted_p=0.5)
            gs.append(g); ps.append(p)
        assert expected_calibration_error(gs, ps) == 0.0

    def test_systematic_over_confidence_positive_ece(self):
        from eval.metrics import expected_calibration_error
        # 10 cases with P=0.95 but only half are actually landlord wins
        # -> bin accuracy 0.5, bin confidence 0.95 -> ECE ~ 0.45
        gs, ps = [], []
        for i in range(5):
            g, p = _make(f"L{i}", issue_winner="landlord", predicted_p=0.95)
            gs.append(g); ps.append(p)
        for i in range(5):
            g, p = _make(f"T{i}", issue_winner="tenant", predicted_p=0.95)
            gs.append(g); ps.append(p)
        ece = expected_calibration_error(gs, ps)
        assert ece > 0.4

    def test_n_bins_one_collapses(self):
        from eval.metrics import expected_calibration_error
        gs, ps = [], []
        for i in range(10):
            g, p = _make(f"x{i}", issue_winner="landlord", predicted_p=0.7)
            gs.append(g); ps.append(p)
        # 10 cases, all landlord, all P=0.7 -> single bin accuracy 1.0,
        # confidence 0.7 -> ECE = 0.3
        ece_1bin = expected_calibration_error(gs, ps, n_bins=1)
        assert abs(ece_1bin - 0.3) < 1e-9

    def test_invalid_n_bins_raises(self):
        from eval.metrics import expected_calibration_error
        g, p = _make("A", issue_winner="landlord", predicted_p=0.5)
        with pytest.raises(ValueError):
            expected_calibration_error([g], [p], n_bins=0)


class TestReliabilityDiagram:
    def test_writes_png(self, tmp_path):
        from eval.metrics import reliability_diagram
        gs, ps = [], []
        for i in range(20):
            g, p = _make(f"x{i}", issue_winner="landlord", predicted_p=0.7)
            gs.append(g); ps.append(p)
        out = tmp_path / "reliability.png"
        result = reliability_diagram(gs, ps, out)
        assert result == out
        assert out.exists()
        # PNG signature: \x89PNG\r\n\x1a\n
        with out.open("rb") as f:
            head = f.read(8)
        assert head[:8] == b"\x89PNG\r\n\x1a\n"

    def test_creates_parent_dir(self, tmp_path):
        from eval.metrics import reliability_diagram
        g, p = _make("A", issue_winner="landlord", predicted_p=0.7)
        out = tmp_path / "nested" / "deep" / "reliability.png"
        reliability_diagram([g], [p], out)
        assert out.exists()


class TestCalibrationOnSyntheticCorpus:
    """End-to-end: load the synthetic 10-case fixture, build a perfectly-
    aligned set of predictions (P=1 when actual is landlord win, 0
    otherwise), confirm Brier=0 and ECE=0."""

    def test_perfect_predictions_on_synthetic_corpus(self):
        from eval.dataset import load
        from eval.metrics import (
            IssuePrediction,
            Prediction,
            brier_score,
            expected_calibration_error,
        )
        from eval.schema import Winner

        result = load(
            "synthetic_corpus_10",
            base_dir=Path(__file__).parent / "fixtures",
        )
        gold = result.cases
        predictions: list = []
        for g in gold:
            gt = g.ground_truth_outcome
            per_issue_preds = [
                IssuePrediction(
                    issue=io.issue,
                    predicted_winner=io.winner,
                    win_probability=1.0 if io.winner == Winner.LANDLORD else 0.0,
                    predicted_amount_gbp=io.awarded_gbp,
                )
                for io in gt.per_issue
            ]
            predictions.append(Prediction(
                case_id=g.case_id,
                overall_winner=gt.overall_winner,
                overall_win_probability=(
                    1.0 if gt.overall_winner == Winner.LANDLORD else 0.0
                ),
                total_predicted_gbp=gt.total_awarded_gbp,
                per_issue=per_issue_preds,
            ))

        assert brier_score(gold, predictions) == 0.0
        assert expected_calibration_error(gold, predictions) == 0.0
