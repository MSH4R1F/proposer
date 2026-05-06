"""Issue-level winner classification accuracy + amount metrics.

Classification and threshold metrics return scalars in [0, 1]. Amount error
metrics return GBP-denominated floats. Wrap scalar metrics in `bootstrap_ci()`
for the CI band per SHA-97. Apportioned cases are scored per-issue;
unapportioned cases (per_issue empty in the gold case) collapse to one
comparison via overall_winner — see `_iter_pairs` for the rule.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any


_ZERO = Decimal("0")


def _validate_pairing(gold: list, predictions: list) -> None:
    if len(gold) != len(predictions):
        raise ValueError(
            f"length mismatch: len(gold)={len(gold)} != len(predictions)={len(predictions)}"
        )
    for g, p in zip(gold, predictions):
        if g.case_id != p.case_id:
            raise ValueError(
                f"case_id mismatch: gold={g.case_id!r} prediction={p.case_id!r}"
            )


def _iter_pairs(gold: list, predictions: list):
    """Yield `(gold_winner, predicted_winner)` per issue, or once per case
    using `overall_winner` for unapportioned cases.

    Apportioned (gold.ground_truth_outcome.per_issue non-empty): one yield
    per matched issue label. Predictions whose `per_issue` lacks a gold
    issue's label count as a missing prediction (treated as a wrong answer
    via `None` placeholder so the caller can decide).
    """
    for g, p in zip(gold, predictions):
        gt = g.ground_truth_outcome
        if not gt.per_issue:  # unapportioned: one comparison per case
            yield gt.overall_winner, p.overall_winner
            continue
        # apportioned: one comparison per gold issue label
        pred_by_issue = {ip.issue: ip.predicted_winner for ip in p.per_issue}
        for io in gt.per_issue:
            yield io.winner, pred_by_issue.get(io.issue)


def issue_winner_accuracy(gold: list, predictions: list) -> float:
    """Fraction of predicted per-issue winners matching ground truth.

    Apportioned: scored per per_issue label. Unapportioned: scored per
    case via overall_winner. Missing predictions (no IssuePrediction
    matching the gold issue label) count as wrong answers.
    """
    _validate_pairing(gold, predictions)
    total = 0
    correct = 0
    for actual, predicted in _iter_pairs(gold, predictions):
        total += 1
        if predicted is not None and actual == predicted:
            correct += 1
    if total == 0:
        return 0.0
    return correct / total


def _coerce_optional_amount(value: Any) -> Decimal | None:
    """Return a finite non-negative Decimal amount, or None when unavailable."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < _ZERO:
        return None
    return amount


def _amount_pairs_and_coverage(
    gold: list, predictions: list
) -> tuple[list[tuple[Decimal, Decimal]], dict[str, int]]:
    """Return evaluable `(actual, predicted)` amount pairs plus coverage.

    Missing gold amounts make a case unsupported for amount scoring. Missing
    predicted amounts are reported explicitly; threshold metrics count them as
    misses, while error metrics compute over pairs where both values exist.
    """
    _validate_pairing(gold, predictions)
    pairs: list[tuple[Decimal, Decimal]] = []
    missing_gold = 0
    missing_predicted = 0
    gold_available = 0
    predicted_available = 0

    for g, p in zip(gold, predictions):
        gt = getattr(g, "ground_truth_outcome", None)
        actual = _coerce_optional_amount(getattr(gt, "total_awarded_gbp", None))
        predicted = _coerce_optional_amount(getattr(p, "total_predicted_gbp", None))

        if actual is None:
            missing_gold += 1
        else:
            gold_available += 1

        if predicted is None:
            missing_predicted += 1
        else:
            predicted_available += 1

        if actual is not None and predicted is not None:
            pairs.append((actual, predicted))

    return pairs, {
        "n_cases": len(gold),
        "n_gold_amount_available": gold_available,
        "n_predicted_amount_available": predicted_available,
        "n_evaluable": len(pairs),
        "missing_gold_amount": missing_gold,
        "missing_predicted_amount": missing_predicted,
    }


def amount_coverage(gold: list, predictions: list) -> dict[str, int]:
    """Coverage counters for amount metrics.

    Use this beside scalar amount metrics so a clean-looking score cannot hide
    missing predicted or gold amounts.
    """
    _, coverage = _amount_pairs_and_coverage(gold, predictions)
    return coverage


def amount_within_threshold(
    gold: list, predictions: list, threshold_pct: float = 0.20
) -> float:
    """Fraction of cases where predicted total is within `threshold_pct`
    of the actual award.

    Threshold is fractional (0.20 = 20%). When the actual is 0, predicted
    must equal 0 to count. When the actual is non-zero, the relative
    error `|predicted - actual| / actual` must be <= threshold_pct.

    Denominator is cases with an available gold amount. Missing predictions
    count as not-within-threshold so amount silence remains visible.
    """
    if threshold_pct < 0:
        raise ValueError("threshold_pct must be >= 0")
    _validate_pairing(gold, predictions)
    if not gold:
        return 0.0

    denominator = 0
    within = 0
    for g, p in zip(gold, predictions):
        gt = getattr(g, "ground_truth_outcome", None)
        actual = _coerce_optional_amount(getattr(gt, "total_awarded_gbp", None))
        predicted = _coerce_optional_amount(getattr(p, "total_predicted_gbp", None))
        if actual is None:
            continue
        denominator += 1
        if predicted is None:
            continue
        if actual == _ZERO:
            if predicted == _ZERO:
                within += 1
            continue
        relative_error = abs(predicted - actual) / actual
        if float(relative_error) <= threshold_pct:
            within += 1
    if denominator == 0:
        return 0.0
    return within / denominator


def amount_within_absolute_threshold(
    gold: list,
    predictions: list,
    threshold_gbp: Decimal | int | float | str = Decimal("100"),
) -> float:
    """Fraction of cases where predicted total is within an absolute GBP band.

    `threshold_gbp=100` is the thesis-friendly "amount@GBP100" metric.
    Denominator and missing-prediction handling match `amount_within_threshold`.
    """
    try:
        threshold = Decimal(str(threshold_gbp))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("threshold_gbp must be finite and >= 0") from None
    if not threshold.is_finite() or threshold < _ZERO:
        raise ValueError("threshold_gbp must be finite and >= 0")
    _validate_pairing(gold, predictions)
    if not gold:
        return 0.0

    denominator = 0
    within = 0
    for g, p in zip(gold, predictions):
        gt = getattr(g, "ground_truth_outcome", None)
        actual = _coerce_optional_amount(getattr(gt, "total_awarded_gbp", None))
        predicted = _coerce_optional_amount(getattr(p, "total_predicted_gbp", None))
        if actual is None:
            continue
        denominator += 1
        if predicted is None:
            continue
        if abs(predicted - actual) <= threshold:
            within += 1
    if denominator == 0:
        return 0.0
    return within / denominator


def amount_mae_gbp(gold: list, predictions: list) -> float:
    """Mean absolute error in GBP over evaluable amount pairs."""
    pairs, _ = _amount_pairs_and_coverage(gold, predictions)
    if not pairs:
        return 0.0
    return float(
        sum((abs(predicted - actual) for actual, predicted in pairs), _ZERO)
        / len(pairs)
    )


def amount_median_absolute_error_gbp(gold: list, predictions: list) -> float:
    """Median absolute error in GBP over evaluable amount pairs."""
    pairs, _ = _amount_pairs_and_coverage(gold, predictions)
    if not pairs:
        return 0.0
    return float(median([abs(predicted - actual) for actual, predicted in pairs]))


def amount_mean_signed_error_gbp(gold: list, predictions: list) -> float:
    """Mean signed error in GBP: positive means over-prediction."""
    pairs, _ = _amount_pairs_and_coverage(gold, predictions)
    if not pairs:
        return 0.0
    return float(
        sum((predicted - actual for actual, predicted in pairs), _ZERO) / len(pairs)
    )
