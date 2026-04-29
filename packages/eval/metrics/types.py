"""Adapter dataclasses for evaluation metrics.

`Prediction` is intentionally a thin shape rather than a re-export of the
orchestrator's `PredictionResult` — keeps `packages/eval/` decoupled from
`packages/llm_orchestrator/`. The Phase 5 ablation runner is responsible
for adapting orchestrator outputs into this shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from eval.schema import Winner


@dataclass
class IssuePrediction:
    issue: str
    predicted_winner: Winner
    win_probability: float  # P(landlord wins this issue), [0, 1]
    predicted_amount_gbp: Decimal


@dataclass
class Prediction:
    case_id: str
    overall_winner: Winner
    overall_win_probability: float  # P(landlord wins overall), [0, 1]
    total_predicted_gbp: Decimal
    per_issue: list


@dataclass
class MetricResult:
    point: float
    lower_95: float
    upper_95: float
    n: int
    n_resamples: int = 0
