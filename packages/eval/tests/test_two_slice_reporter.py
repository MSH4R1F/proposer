"""Tests for packages/eval/metrics/two_slice_reporter.py (Stream C §17.6 / §8.3)."""
from __future__ import annotations

import math

import pytest

from eval.metrics.two_slice_reporter import two_slice_report


def _pred(used: bool, score: float = 1.0) -> dict:
    return {"pipeline_metadata": {"kg_used_for_prediction": used}, "score": score}


def _accuracy(gold: list, preds: list) -> float:
    return sum(1.0 for g, p in zip(gold, preds) if g == p["score"]) / len(gold)


def test_two_slice_report_returns_both_slices():
    gold = [1.0, 1.0, 1.0, 1.0]
    preds = [_pred(True, 1.0), _pred(True, 0.0), _pred(False, 1.0), _pred(False, 1.0)]
    out = two_slice_report(_accuracy, gold, preds)
    assert "full_corpus" in out
    assert "gate_passing_subset" in out


def test_two_slice_report_no_gate_passing_returns_nan():
    gold = [1.0, 1.0]
    preds = [_pred(False, 1.0), _pred(False, 1.0)]
    out = two_slice_report(_accuracy, gold, preds)
    assert math.isnan(out["gate_passing_subset"].point)
    assert out["gate_passing_subset"].n == 0


def test_two_slice_report_all_gate_passing_matches_full():
    gold = [1.0, 0.0]
    preds = [_pred(True, 1.0), _pred(True, 0.0)]
    out = two_slice_report(_accuracy, gold, preds)
    assert out["full_corpus"].point == out["gate_passing_subset"].point


def test_two_slice_report_subset_metric_differs():
    """Gate-passing subset can show a different metric value."""
    gold = [1.0, 0.0, 1.0, 0.0]
    preds = [_pred(True, 1.0), _pred(True, 1.0), _pred(False, 0.0), _pred(False, 1.0)]
    # Full: matches at i=0 only -> 1/4 = 0.25
    # Gate subset (i=0, i=1): match at i=0 only -> 1/2 = 0.5
    out = two_slice_report(_accuracy, gold, preds)
    assert out["full_corpus"].point == 0.25
    assert out["gate_passing_subset"].point == 0.5


def test_two_slice_length_mismatch_raises():
    with pytest.raises(ValueError):
        two_slice_report(_accuracy, [1.0], [_pred(True), _pred(True)])


def test_two_slice_empty_raises():
    with pytest.raises(ValueError):
        two_slice_report(_accuracy, [], [])


def test_two_slice_n_field_correct():
    gold = [1.0, 1.0, 1.0]
    preds = [_pred(True, 1.0), _pred(True, 1.0), _pred(False, 1.0)]
    out = two_slice_report(_accuracy, gold, preds)
    assert out["full_corpus"].n == 3
    assert out["gate_passing_subset"].n == 2


def test_two_slice_flattened_predictions():
    """Predictions can have kg_used_for_prediction at top level."""
    gold = [1.0, 1.0]
    preds = [
        {"kg_used_for_prediction": True, "score": 1.0},
        {"kg_used_for_prediction": False, "score": 1.0},
    ]
    out = two_slice_report(_accuracy, gold, preds)
    assert out["gate_passing_subset"].n == 1
