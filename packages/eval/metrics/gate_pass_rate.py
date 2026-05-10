"""Gate pass rate — share of predictions where kg_used_for_prediction=True.

Per spec §17.6 first-class metric. Uses bootstrap_ci so the lower CI bound
is reportable.
"""

from __future__ import annotations

from typing import Any, Dict, List

from eval.metrics.types import MetricResult
from eval.metrics.uncertainty import bootstrap_ci


def gate_pass_rate(predictions: List[Dict[str, Any]]) -> MetricResult:
    """Share of predictions where pipeline_metadata.kg_used_for_prediction == True.

    Each prediction is a dict-like artifact row; the function reads
    pred["pipeline_metadata"]["kg_used_for_prediction"] (or pred["kg_used_for_prediction"]
    for already-flattened rows).

    Returns a MetricResult with bootstrap CI; raises ValueError on empty input.
    """
    if not predictions:
        raise ValueError("gate_pass_rate requires at least one prediction")

    def _metric(gold: list, preds: list) -> float:
        passed = sum(1 for p in preds if _kg_used(p) is True)
        return passed / len(preds)

    return bootstrap_ci(
        _metric,
        gold=[None] * len(predictions),
        predictions=list(predictions),
    )


def fallback_mode_distribution(predictions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Histogram of pipeline_metadata.kg_fallback_mode values across predictions.

    None / missing values count under the key "none". Use this to debug
    what's tripping the gate in a batch run.
    """
    counts: Dict[str, int] = {}
    for p in predictions:
        mode = _fallback_mode(p)
        key = mode if mode is not None else "none"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _kg_used(p: Dict[str, Any]) -> Any:
    meta = p.get("pipeline_metadata") if isinstance(p.get("pipeline_metadata"), dict) else p
    return meta.get("kg_used_for_prediction") if isinstance(meta, dict) else None


def _fallback_mode(p: Dict[str, Any]) -> Any:
    meta = p.get("pipeline_metadata") if isinstance(p.get("pipeline_metadata"), dict) else p
    return meta.get("kg_fallback_mode") if isinstance(meta, dict) else None
