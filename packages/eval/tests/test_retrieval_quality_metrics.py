"""Tests for retrieval quality metrics (Stream C PR 5 — Task 5.7).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §17.2.

All three metrics are pure functions returning floats in [0, 1].
NaN-safe (0.0 fallback when sets are empty).
"""

from __future__ import annotations

import pytest

from eval.metrics.retrieval_quality import (
    citation_validity,
    retrieval_context_precision_at_k,
    retrieval_context_recall_at_k,
)


# ---------------------------------------------------------------------------
# precision@k
# ---------------------------------------------------------------------------


def test_precision_at_k_perfect():
    assert (
        retrieval_context_precision_at_k(["a", "b", "c"], {"a", "b", "c"}, 3) == 1.0
    )


def test_precision_at_k_partial():
    assert (
        retrieval_context_precision_at_k(["a", "b", "c", "d"], {"a", "c"}, 4) == 0.5
    )


def test_precision_at_k_top1_miss():
    assert retrieval_context_precision_at_k(["x", "a"], {"a"}, 1) == 0.0


def test_precision_at_k_top1_hit():
    assert retrieval_context_precision_at_k(["a", "x"], {"a"}, 1) == 1.0


def test_precision_at_k_zero_k():
    assert retrieval_context_precision_at_k(["a"], {"a"}, 0) == 0.0


def test_precision_at_k_empty_retrieved():
    assert retrieval_context_precision_at_k([], {"a"}, 5) == 0.0


def test_precision_at_k_short_retrieved():
    """When |retrieved| < k, denominator is len(retrieved), not k."""
    assert retrieval_context_precision_at_k(["a"], {"a"}, 5) == 1.0


# ---------------------------------------------------------------------------
# recall@k
# ---------------------------------------------------------------------------


def test_recall_at_k_perfect():
    assert retrieval_context_recall_at_k(["a", "b", "c"], {"a", "b"}, 3) == 1.0


def test_recall_at_k_partial():
    assert retrieval_context_recall_at_k(
        ["a", "x", "y"], {"a", "b", "c"}, 3
    ) == pytest.approx(1 / 3)


def test_recall_at_k_zero_relevant():
    assert retrieval_context_recall_at_k(["a"], set(), 1) == 0.0


def test_recall_at_k_zero_k():
    assert retrieval_context_recall_at_k(["a"], {"a"}, 0) == 0.0


# ---------------------------------------------------------------------------
# citation_validity
# ---------------------------------------------------------------------------


def test_citation_validity_perfect():
    preds = [{"prediction_id": "p1", "cited": {"c1", "c2"}}]
    gold = {"p1": {"c1", "c2"}}
    assert citation_validity(preds, gold) == 1.0


def test_citation_validity_partial():
    preds = [{"prediction_id": "p1", "cited": {"c1", "c2", "c3"}}]
    gold = {"p1": {"c1"}}
    assert citation_validity(preds, gold) == pytest.approx(1 / 3)


def test_citation_validity_macro_average():
    preds = [
        {"prediction_id": "p1", "cited": {"c1"}},
        {"prediction_id": "p2", "cited": {"x"}},
    ]
    gold = {"p1": {"c1"}, "p2": {"y"}}
    # p1: 1.0, p2: 0.0 → macro 0.5
    assert citation_validity(preds, gold) == pytest.approx(0.5)


def test_citation_validity_empty_predictions():
    assert citation_validity([], {}) == 0.0


def test_citation_validity_no_cites_in_prediction():
    """An empty `cited` set scores 0.0 (not NaN, not skipped)."""
    preds = [{"prediction_id": "p1", "cited": set()}]
    gold = {"p1": {"c1"}}
    assert citation_validity(preds, gold) == 0.0


def test_citation_validity_unknown_prediction_id():
    """Predictions whose pid isn't in gold get score 0.0."""
    preds = [{"prediction_id": "p_unknown", "cited": {"c1"}}]
    gold = {"p1": {"c1"}}
    assert citation_validity(preds, gold) == 0.0


# ---------------------------------------------------------------------------
# bootstrap CI compatibility
# ---------------------------------------------------------------------------


def test_metrics_compose_with_bootstrap_ci():
    """Confirm precision@k can be wrapped in a bootstrap_ci-compatible
    metric_fn(gold, predictions) -> float without erroring."""
    try:
        from eval.metrics.uncertainty import bootstrap_ci
    except ImportError:
        pytest.skip("bootstrap_ci not available")

    # bootstrap_ci signature: metric_fn(gold, predictions) -> float.
    # Set up a per-row evaluation: each "gold" entry is a relevant set,
    # each "prediction" is a retrieved list. Macro-average precision@2.
    gold = [{"a"}, {"b"}, {"a", "c"}, {"d"}, {"e"}]
    predictions = [
        ["a", "x"],
        ["b", "y"],
        ["a", "c"],
        ["x", "y"],
        ["e", "z"],
    ]

    def macro_precision_at_2(g_list, p_list):
        scores = [
            retrieval_context_precision_at_k(p, g, 2)
            for g, p in zip(g_list, p_list)
        ]
        return sum(scores) / len(scores) if scores else 0.0

    result = bootstrap_ci(
        macro_precision_at_2, gold, predictions, n_resamples=10, seed=0
    )
    # bootstrap_ci returns a MetricResult with .point in [0, 1].
    assert result is not None
    assert 0.0 <= result.point <= 1.0
