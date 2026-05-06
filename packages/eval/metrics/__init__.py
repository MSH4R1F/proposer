"""Evaluation metrics: accuracy, calibration, uncertainty (bootstrap CIs)."""
from eval.metrics.accuracy import (
    abstention_rate,
    amount_coverage,
    amount_mae_gbp,
    amount_mean_signed_error_gbp,
    amount_median_absolute_error_gbp,
    amount_within_absolute_threshold,
    amount_within_threshold,
    balanced_accuracy,
    coverage_adjusted_accuracy,
    covered_accuracy,
    issue_winner_accuracy,
    macro_f1,
)
from eval.metrics.calibration import (
    brier_score,
    expected_calibration_error,
    reliability_diagram,
)
from eval.metrics.types import IssuePrediction, MetricResult, Prediction
from eval.metrics.uncertainty import bootstrap_ci

__all__ = [
    "IssuePrediction",
    "MetricResult",
    "Prediction",
    "abstention_rate",
    "amount_coverage",
    "amount_mae_gbp",
    "amount_mean_signed_error_gbp",
    "amount_median_absolute_error_gbp",
    "amount_within_absolute_threshold",
    "amount_within_threshold",
    "balanced_accuracy",
    "bootstrap_ci",
    "brier_score",
    "coverage_adjusted_accuracy",
    "covered_accuracy",
    "expected_calibration_error",
    "issue_winner_accuracy",
    "macro_f1",
    "reliability_diagram",
]
