"""Regression test for the synthetic per-mode prediction fixtures.

Locks the ranking that `_build_ablation_predictions.py` is expected to
produce against the 10-case synthetic corpus. If the builder or the
underlying corpus changes and the rankings flip, this test catches it
before the fixtures are committed in a misleading state.

The numbers below are the no-bootstrap point estimates. They are
deterministic: same corpus + same builder → same predictions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from eval.compare import build_comparison_report
from eval.dataset import load
from eval.run import _load_predictions

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def report():
    gold = load("synthetic_corpus_10", base_dir=FIXTURES, strict=True).cases
    predictions_by_mode = {
        "hybrid": _load_predictions(FIXTURES / "predictions_synthetic_hybrid.jsonl"),
        "rag_only": _load_predictions(FIXTURES / "predictions_synthetic_rag_only.jsonl"),
        "kg_only": _load_predictions(FIXTURES / "predictions_synthetic_kg_only.jsonl"),
        "llm_only": _load_predictions(FIXTURES / "predictions_synthetic_llm_only.jsonl"),
    }
    return build_comparison_report(gold, predictions_by_mode, n_resamples=0)


def test_accuracy_ranks_hybrid_first(report):
    ranked = report.ranked_by("accuracy")
    assert [m.mode for m in ranked] == ["hybrid", "rag_only", "kg_only", "llm_only"]


def test_brier_ranks_hybrid_first(report):
    """Hybrid is best on Brier. Note kg_only is *worse* than llm_only on
    Brier because confidently-wrong (kg_only at 0.7) penalises more than
    coinflip uncertainty (llm_only at 0.5). This is a real methodological
    feature documented in docs/eval/ablation.md."""
    ranked = report.ranked_by("brier")
    assert ranked[0].mode == "hybrid"
    # Don't lock the back of the ranking — kg_only vs llm_only is
    # confidence-vs-coinflip and might shift if confidence levels change.


def test_hybrid_dominates_llm_only_on_accuracy(report):
    by_mode = {m.mode: m for m in report.modes}
    assert by_mode["hybrid"].accuracy.point > by_mode["llm_only"].accuracy.point


def test_each_mode_loaded_for_all_ten_cases(report):
    for m in report.modes:
        assert m.accuracy.n == 10
