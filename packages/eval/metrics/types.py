"""Adapter dataclasses for evaluation metrics.

`Prediction` is intentionally a thin shape rather than a re-export of the
orchestrator's `PredictionResult` — keeps `packages/eval/` decoupled from
`packages/llm_orchestrator/`. The Phase 5 ablation runner is responsible
for adapting orchestrator outputs into this shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math

from eval.schema import Winner


def _validate_probability(name: str, value: float) -> float:
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError(f"{name} must be a finite float in [0, 1]; got {value!r}")
    return probability


@dataclass
class IssuePrediction:
    issue: str
    predicted_winner: Winner
    win_probability: float  # P(landlord wins this issue), [0, 1]
    predicted_amount_gbp: Decimal

    def __post_init__(self) -> None:
        self.win_probability = _validate_probability(
            "win_probability", self.win_probability
        )
        self.predicted_amount_gbp = Decimal(str(self.predicted_amount_gbp))
        if (
            not self.predicted_amount_gbp.is_finite()
            or self.predicted_amount_gbp < Decimal("0")
        ):
            raise ValueError("predicted_amount_gbp must be finite and >= 0")


@dataclass
class Prediction:
    case_id: str
    overall_winner: Winner
    overall_win_probability: float  # P(landlord wins overall), [0, 1]
    total_predicted_gbp: Decimal
    per_issue: list

    def __post_init__(self) -> None:
        self.overall_win_probability = _validate_probability(
            "overall_win_probability", self.overall_win_probability
        )
        self.total_predicted_gbp = Decimal(str(self.total_predicted_gbp))
        if (
            not self.total_predicted_gbp.is_finite()
            or self.total_predicted_gbp < Decimal("0")
        ):
            raise ValueError("total_predicted_gbp must be finite and >= 0")


@dataclass
class MetricResult:
    point: float
    lower_95: float
    upper_95: float
    n: int
    n_resamples: int = 0
