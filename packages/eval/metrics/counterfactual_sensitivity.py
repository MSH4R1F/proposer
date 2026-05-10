"""Counterfactual factor sensitivity harness — does the prediction change
when each factor is flipped?

Per spec §17.7. The harness exists but is NOT run in CI (compute cost is
high — factors x cases x LLM calls). Production callers wire this to a
real predict_fn for offline analysis.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


async def counterfactual_factor_sensitivity(
    case: Any,
    factor_ids: List[str],
    predict_fn: Callable[[Any], Awaitable[Any]],
    *,
    flip_factor: Optional[Callable[[Any, str], Any]] = None,
    extract_outcome: Optional[Callable[[Any], str]] = None,
) -> Dict[str, bool]:
    """For each factor in factor_ids, flip its value and check if prediction changes.

    Args:
        case: opaque case object (caller-defined shape).
        factor_ids: factor IDs to test.
        predict_fn: async function returning a prediction object.
        flip_factor: function (case, factor_id) -> new_case with that factor flipped.
            If None, defaults to a noop (caller MUST supply a real implementation
            for meaningful results — included as None default for harness ergonomics
            during scaffolding).
        extract_outcome: function prediction -> str representing the outcome label.
            If None, defaults to str(prediction).

    Returns dict {factor_id: True (prediction changed) or False (unchanged)}.
    """
    if flip_factor is None:
        def flip_factor(c: Any, fid: str) -> Any:
            return c
    if extract_outcome is None:
        extract_outcome = str

    base_pred = await predict_fn(case)
    base_outcome = extract_outcome(base_pred)

    sensitivity: Dict[str, bool] = {}
    for fid in factor_ids:
        flipped_case = flip_factor(case, fid)
        flipped_pred = await predict_fn(flipped_case)
        flipped_outcome = extract_outcome(flipped_pred)
        sensitivity[fid] = (base_outcome != flipped_outcome)
    return sensitivity


def sensitivity_score(sensitivity: Dict[str, bool]) -> float:
    """Share of factors whose flip changed the outcome.

    Returns 0.0 for empty input (no factors tested - no signal).
    """
    if not sensitivity:
        return 0.0
    return sum(1 for v in sensitivity.values() if v) / len(sensitivity)
