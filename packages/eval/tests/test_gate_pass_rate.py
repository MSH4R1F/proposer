"""Tests for packages/eval/metrics/gate_pass_rate.py (Stream C §17.6)."""
from __future__ import annotations

import pytest

from eval.metrics.gate_pass_rate import gate_pass_rate, fallback_mode_distribution


def _pred(used: bool | None, mode: str | None = None) -> dict:
    return {"pipeline_metadata": {"kg_used_for_prediction": used, "kg_fallback_mode": mode}}


def test_gate_pass_rate_all_passed():
    res = gate_pass_rate([_pred(True), _pred(True)])
    assert res.point == 1.0
    assert res.lower_95 <= 1.0 <= res.upper_95


def test_gate_pass_rate_all_failed():
    res = gate_pass_rate([_pred(False), _pred(False)])
    assert res.point == 0.0


def test_gate_pass_rate_mixed():
    res = gate_pass_rate([_pred(True), _pred(False), _pred(True), _pred(False)])
    assert res.point == 0.5


def test_gate_pass_rate_none_treated_as_not_passed():
    res = gate_pass_rate([_pred(None), _pred(True)])
    assert res.point == 0.5


def test_gate_pass_rate_empty_raises():
    with pytest.raises(ValueError):
        gate_pass_rate([])


def test_gate_pass_rate_flattened_rows():
    """Rows can be flattened (no nested pipeline_metadata)."""
    res = gate_pass_rate([
        {"kg_used_for_prediction": True},
        {"kg_used_for_prediction": False},
    ])
    assert res.point == 0.5


def test_gate_pass_rate_returns_metric_result_with_n():
    res = gate_pass_rate([_pred(True)] * 5)
    assert res.n == 5


def test_fallback_mode_distribution_counts():
    dist = fallback_mode_distribution([
        _pred(False, "rag_only"), _pred(False, "rag_only"),
        _pred(False, "legacy_no_domain_id"), _pred(True, None),
    ])
    assert dist == {"rag_only": 2, "legacy_no_domain_id": 1, "none": 1}


def test_fallback_mode_distribution_empty():
    assert fallback_mode_distribution([]) == {}


def test_fallback_mode_distribution_flattened():
    dist = fallback_mode_distribution([{"kg_fallback_mode": "rag_only"}])
    assert dist == {"rag_only": 1}
