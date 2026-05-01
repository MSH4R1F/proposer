"""Bootstrap confidence intervals for any metric over (gold, predictions).

Implements SHA-97. The thesis claims survival rule: a claim only "lands"
if its lower CI bound clears the headline target — every metric runner
emits `(point, lower_95, upper_95, n)` rather than a bare scalar.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

import numpy as np

from eval.metrics.types import MetricResult


def bootstrap_ci(
    metric_fn: Callable,
    gold: list,
    predictions: list,
    *,
    n_resamples: int = 1000,
    seed: Optional[int] = 42,
    confidence: float = 0.95,
) -> MetricResult:
    """Resample (gold[i], predictions[i]) PAIRS with replacement; recompute
    `metric_fn(gold_sample, predictions_sample)` per resample; return the
    point estimate from the full sample plus the bootstrap CI bounds.

    `metric_fn` must accept `(gold: list, predictions: list)` and return a
    float scalar. Empty input raises `ValueError`. n=1 input returns a
    degenerate CI where `lower_95 == upper_95 == point`.
    """
    if not gold or not predictions:
        raise ValueError("bootstrap_ci requires non-empty gold and predictions")
    if len(gold) != len(predictions):
        raise ValueError(
            f"length mismatch: len(gold)={len(gold)} != len(predictions)={len(predictions)}"
        )

    n = len(gold)
    point = float(metric_fn(gold, predictions))

    if n == 1 or n_resamples <= 0:
        return MetricResult(
            point=point, lower_95=point, upper_95=point, n=n, n_resamples=0
        )

    rng = random.Random(seed)
    samples: list = []
    for _ in range(n_resamples):
        indices = [rng.randrange(n) for _ in range(n)]
        g_sample = [gold[i] for i in indices]
        p_sample = [predictions[i] for i in indices]
        samples.append(float(metric_fn(g_sample, p_sample)))

    lower_pct = (1.0 - confidence) / 2.0 * 100.0
    upper_pct = 100.0 - lower_pct
    lower = float(np.percentile(samples, lower_pct))
    upper = float(np.percentile(samples, upper_pct))
    return MetricResult(
        point=point,
        lower_95=lower,
        upper_95=upper,
        n=n,
        n_resamples=n_resamples,
    )
