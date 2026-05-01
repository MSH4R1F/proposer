"""Tests for packages/eval/metrics/uncertainty.py (SHA-97)."""
from __future__ import annotations

import pytest


class TestBootstrapCi:
    def test_empty_gold_raises(self):
        from eval.metrics import bootstrap_ci
        with pytest.raises(ValueError):
            bootstrap_ci(lambda g, p: 1.0, [], [])

    def test_length_mismatch_raises(self):
        from eval.metrics import bootstrap_ci
        with pytest.raises(ValueError, match="length mismatch"):
            bootstrap_ci(lambda g, p: 1.0, [1, 2, 3], [1, 2])

    def test_singleton_input_returns_degenerate_ci(self):
        from eval.metrics import bootstrap_ci
        result = bootstrap_ci(lambda g, p: 0.42, ["a"], ["b"])
        assert result.n == 1
        assert result.point == 0.42
        assert result.lower_95 == 0.42
        assert result.upper_95 == 0.42

    def test_constant_metric_collapses_ci(self):
        from eval.metrics import bootstrap_ci
        result = bootstrap_ci(
            lambda g, p: 0.5,
            list(range(50)),
            list(range(50)),
            n_resamples=1000,
        )
        assert result.point == 0.5
        assert result.lower_95 == 0.5
        assert result.upper_95 == 0.5
        assert result.n == 50
        assert result.n_resamples == 1000

    def test_deterministic_seed(self):
        from eval.metrics import bootstrap_ci
        # A varying metric — sample mean
        gold = list(range(50))
        preds = list(range(50))

        def mean_metric(g, p):
            return sum(p) / len(p)

        a = bootstrap_ci(mean_metric, gold, preds, n_resamples=500, seed=123)
        b = bootstrap_ci(mean_metric, gold, preds, n_resamples=500, seed=123)
        assert a == b

    def test_monotonicity_lower_le_point_le_upper(self):
        from eval.metrics import bootstrap_ci
        gold = list(range(50))
        preds = list(range(50))

        def mean_metric(g, p):
            return sum(p) / len(p)

        result = bootstrap_ci(mean_metric, gold, preds, n_resamples=1000)
        assert result.lower_95 <= result.point <= result.upper_95

    def test_variability_for_noisy_metric(self):
        # Mean over a noisy distribution should give a non-degenerate CI
        from eval.metrics import bootstrap_ci
        import random as _rng
        _rng.seed(0)
        preds = [_rng.uniform(0, 1) for _ in range(100)]
        gold = preds  # not used by mean_metric

        def mean_metric(g, p):
            return sum(p) / len(p)

        result = bootstrap_ci(mean_metric, gold, preds, n_resamples=1000, seed=42)
        assert result.lower_95 < result.point < result.upper_95
        assert result.upper_95 - result.lower_95 > 0.01  # non-trivial spread

    def test_n_resamples_zero_returns_point_only(self):
        from eval.metrics import bootstrap_ci
        result = bootstrap_ci(
            lambda g, p: 0.7,
            [1, 2, 3],
            [1, 2, 3],
            n_resamples=0,
        )
        assert result.point == 0.7
        assert result.lower_95 == 0.7
        assert result.upper_95 == 0.7
        assert result.n_resamples == 0

    def test_metric_result_shape(self):
        from eval.metrics import MetricResult
        r = MetricResult(point=0.7, lower_95=0.65, upper_95=0.75, n=50, n_resamples=1000)
        assert r.point == 0.7 and r.lower_95 == 0.65 and r.upper_95 == 0.75
        assert r.n == 50 and r.n_resamples == 1000


class TestPredictionTypes:
    def test_prediction_dataclass(self):
        from decimal import Decimal
        from eval.metrics import Prediction, IssuePrediction
        from eval.schema import Winner
        ip = IssuePrediction(
            issue="cleaning",
            predicted_winner=Winner.TENANT,
            win_probability=0.3,
            predicted_amount_gbp=Decimal("100.00"),
        )
        p = Prediction(
            case_id="X",
            overall_winner=Winner.TENANT,
            overall_win_probability=0.3,
            total_predicted_gbp=Decimal("100.00"),
            per_issue=[ip],
        )
        assert p.case_id == "X"
        assert p.per_issue[0].issue == "cleaning"

    def test_issue_prediction_rejects_probability_outside_unit_interval(self):
        from decimal import Decimal
        from eval.metrics import IssuePrediction
        from eval.schema import Winner
        with pytest.raises(ValueError, match="win_probability"):
            IssuePrediction(
                issue="cleaning",
                predicted_winner=Winner.TENANT,
                win_probability=2.0,
                predicted_amount_gbp=Decimal("100.00"),
            )

    def test_prediction_rejects_probability_outside_unit_interval(self):
        from decimal import Decimal
        from eval.metrics import Prediction
        from eval.schema import Winner
        with pytest.raises(ValueError, match="overall_win_probability"):
            Prediction(
                case_id="X",
                overall_winner=Winner.TENANT,
                overall_win_probability=-0.1,
                total_predicted_gbp=Decimal("100.00"),
                per_issue=[],
            )
