"""Two-slice metric reporting per spec §17.6 / §8.3.

Splits any (gold, predictions) metric into:
- full_corpus: the whole gold set
- gate_passing_subset: only predictions where kg_used_for_prediction=True

Critical for Stream C: numbers reported on the gate-passing subset are
the headline thesis claim; full-corpus numbers contextualize how often
the gate fires.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from eval.metrics.types import MetricResult
from eval.metrics.uncertainty import bootstrap_ci


def two_slice_report(
    metric_fn: Callable[[list, list], float],
    gold: List[Any],
    predictions: List[Any],
) -> Dict[str, MetricResult]:
    """Run metric_fn on full corpus + gate-passing subset.

    Returns dict with keys "full_corpus" and "gate_passing_subset".

    When no predictions pass the gate, gate_passing_subset returns a
    NaN-valued MetricResult with n=0 (caller decides how to display).
    """
    if len(gold) != len(predictions):
        raise ValueError(
            f"length mismatch: gold={len(gold)} predictions={len(predictions)}"
        )
    if not predictions:
        raise ValueError("two_slice_report requires at least one prediction")

    full = bootstrap_ci(metric_fn, gold, predictions)

    gate_passing_ix = [i for i, p in enumerate(predictions) if _kg_used(p) is True]
    if not gate_passing_ix:
        gate = MetricResult(
            point=float("nan"),
            lower_95=float("nan"),
            upper_95=float("nan"),
            n=0,
            n_resamples=0,
        )
    elif len(gate_passing_ix) == 1:
        gold_one = [gold[gate_passing_ix[0]]]
        pred_one = [predictions[gate_passing_ix[0]]]
        gate = bootstrap_ci(metric_fn, gold_one, pred_one)
    else:
        g_subset = [gold[i] for i in gate_passing_ix]
        p_subset = [predictions[i] for i in gate_passing_ix]
        gate = bootstrap_ci(metric_fn, g_subset, p_subset)

    return {"full_corpus": full, "gate_passing_subset": gate}


def _kg_used(p: Any) -> Any:
    if isinstance(p, dict):
        meta = p.get("pipeline_metadata", p)
        if isinstance(meta, dict):
            return meta.get("kg_used_for_prediction")
        return None
    # Object access fallback
    meta = getattr(p, "pipeline_metadata", None)
    if meta is not None:
        return getattr(meta, "kg_used_for_prediction", None)
    return getattr(p, "kg_used_for_prediction", None)
