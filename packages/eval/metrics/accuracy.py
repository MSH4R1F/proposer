"""Issue-level winner classification accuracy + £-amount within-threshold.

Both metrics return scalars in [0, 1]. Wrap in `bootstrap_ci()` for the CI
band per SHA-97. Apportioned cases are scored per-issue; unapportioned
cases (per_issue empty in the gold case) collapse to one comparison via
overall_winner — see `_iter_pairs` for the rule.
"""
from __future__ import annotations

from decimal import Decimal


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


def amount_within_threshold(
    gold: list, predictions: list, threshold_pct: float = 0.20
) -> float:
    """Fraction of cases where predicted total is within `threshold_pct`
    of the actual award.

    Threshold is fractional (0.20 = 20%). When the actual is 0, predicted
    must equal 0 to count. When the actual is non-zero, the relative
    error `|predicted - actual| / actual` must be <= threshold_pct.
    """
    _validate_pairing(gold, predictions)
    if not gold:
        return 0.0
    if threshold_pct < 0:
        raise ValueError("threshold_pct must be >= 0")
    within = 0
    for g, p in zip(gold, predictions):
        actual = g.ground_truth_outcome.total_awarded_gbp
        predicted = p.total_predicted_gbp
        if actual == Decimal("0"):
            if predicted == Decimal("0"):
                within += 1
            continue
        relative_error = abs(predicted - actual) / actual
        if float(relative_error) <= threshold_pct:
            within += 1
    return within / len(gold)
