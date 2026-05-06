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


def _iter_prediction_pairs(gold: list, predictions: list):
    """Yield `(gold_winner, predicted_winner, abstained)` comparisons.

    This mirrors `_iter_pairs` but carries the raw-abstention signal preserved
    by `scripts/eval/predict_all.py`. Missing per-issue predictions are treated
    as abstentions because the model emitted no covered answer for that issue.
    """
    for g, p in zip(gold, predictions):
        gt = g.ground_truth_outcome
        if not gt.per_issue:
            yield (
                gt.overall_winner,
                p.overall_winner,
                bool(getattr(p, "abstained", False)),
            )
            continue

        pred_by_issue = {ip.issue: ip for ip in p.per_issue}
        for io in gt.per_issue:
            ip = pred_by_issue.get(io.issue)
            if ip is None:
                yield io.winner, None, True
                continue
            yield io.winner, ip.predicted_winner, bool(getattr(ip, "abstained", False))


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


def balanced_accuracy(gold: list, predictions: list) -> float:
    """Macro-average recall over labels present in the gold set.

    This exposes class-imbalance failures hidden by headline accuracy. For a
    49/1 tenant-heavy set, a model must still recover the minority landlord
    row to score well here.
    """
    _validate_pairing(gold, predictions)
    pairs = list(_iter_prediction_pairs(gold, predictions))
    labels = sorted({actual for actual, _, _ in pairs}, key=lambda w: w.value)
    if not labels:
        return 0.0

    recalls: list[float] = []
    for label in labels:
        actual_count = sum(1 for actual, _, _ in pairs if actual == label)
        if actual_count == 0:
            continue
        true_positive = sum(
            1 for actual, predicted, _ in pairs if actual == label and predicted == label
        )
        recalls.append(true_positive / actual_count)
    return sum(recalls) / len(recalls) if recalls else 0.0


def macro_f1(gold: list, predictions: list) -> float:
    """Macro-F1 over labels present in either gold or predictions.

    Labels that are absent from both gold and predictions are ignored. Labels
    predicted spuriously, such as many `split` calls on a no-split gold set,
    contribute an F1 of 0 and remain visible.
    """
    _validate_pairing(gold, predictions)
    pairs = list(_iter_prediction_pairs(gold, predictions))
    labels = sorted(
        {
            label
            for actual, predicted, _ in pairs
            for label in (actual, predicted)
            if label is not None
        },
        key=lambda w: w.value,
    )
    if not labels:
        return 0.0

    f1s: list[float] = []
    for label in labels:
        tp = sum(
            1 for actual, predicted, _ in pairs if actual == label and predicted == label
        )
        fp = sum(
            1 for actual, predicted, _ in pairs if actual != label and predicted == label
        )
        fn = sum(
            1 for actual, predicted, _ in pairs if actual == label and predicted != label
        )
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        if precision + recall == 0:
            f1s.append(0.0)
        else:
            f1s.append(2 * precision * recall / (precision + recall))
    return sum(f1s) / len(f1s)


def abstention_rate(gold: list, predictions: list) -> float:
    """Fraction of issue/case comparisons that were raw abstentions."""
    _validate_pairing(gold, predictions)
    pairs = list(_iter_prediction_pairs(gold, predictions))
    if not pairs:
        return 0.0
    return sum(1 for _, _, abstained in pairs if abstained) / len(pairs)


def covered_accuracy(gold: list, predictions: list) -> float:
    """Accuracy over non-abstained comparisons only.

    Use this beside `abstention_rate`; a high covered accuracy with low
    coverage means the model is precise when it answers but too quiet.
    """
    _validate_pairing(gold, predictions)
    covered = [
        (actual, predicted)
        for actual, predicted, abstained in _iter_prediction_pairs(gold, predictions)
        if not abstained
    ]
    if not covered:
        return 0.0
    return sum(1 for actual, predicted in covered if actual == predicted) / len(covered)


def coverage_adjusted_accuracy(gold: list, predictions: list) -> float:
    """Correct non-abstained answers divided by all comparisons.

    This treats abstentions as uncovered rather than as the eval-schema
    `split` fallback, so it is robust even when a real gold row is split.
    """
    _validate_pairing(gold, predictions)
    pairs = list(_iter_prediction_pairs(gold, predictions))
    if not pairs:
        return 0.0
    correct_covered = sum(
        1
        for actual, predicted, abstained in pairs
        if not abstained and actual == predicted
    )
    return correct_covered / len(pairs)


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
    threshold = Decimal(str(threshold_gbp))
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
