"""Multi-mode comparison report — the RQ1 ablation artifact.

Given a gold corpus and predictions emitted by each `PredictionMode` (HYBRID,
RAG_ONLY, KG_ONLY, LLM_ONLY), `build_comparison_report` computes accuracy,
amount-within-threshold, Brier, and ECE for each mode (with bootstrap CIs)
and produces a single `ComparisonReport` that the thesis can table or chart.

`summarise_dominance` answers the harder question: did one mode beat
another *significantly*, or is the gap inside the resampling noise?

The functions are pure (no I/O). The CLI wrapper lives at `eval.ablate`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List

from eval.metrics import (
    bootstrap_ci,
    brier_score,
    expected_calibration_error,
    issue_winner_accuracy,
)
from eval.metrics.accuracy import amount_within_threshold
from eval.metrics.types import MetricResult


# Lower-is-better metrics need flipped dominance logic.
_LOWER_IS_BETTER = {"brier", "ece"}


@dataclass
class ModeMetrics:
    mode: str
    accuracy: MetricResult
    amount_threshold: MetricResult
    brier: MetricResult
    ece: MetricResult

    def metric_by_alias(self, alias: str) -> MetricResult:
        """Return the metric stored under the public alias used by the CLI."""
        mapping = {
            "accuracy": self.accuracy,
            "amount_threshold": self.amount_threshold,
            "brier": self.brier,
            "ece": self.ece,
        }
        if alias not in mapping:
            raise KeyError(
                f"unknown metric alias {alias!r}; expected one of {sorted(mapping)}"
            )
        return mapping[alias]


@dataclass
class ComparisonReport:
    n_cases: int
    seed: int
    n_resamples: int
    modes: List[ModeMetrics] = field(default_factory=list)

    def ranked_by(self, alias: str, *, ascending: bool | None = None) -> List[ModeMetrics]:
        """Return modes sorted best→worst by the given metric.

        Default direction is metric-aware: lower-is-better metrics ascend,
        higher-is-better metrics descend. Pass `ascending=` to override.
        """
        if ascending is None:
            ascending = alias in _LOWER_IS_BETTER
        return sorted(
            self.modes,
            key=lambda m: m.metric_by_alias(alias).point,
            reverse=not ascending,
        )


def build_comparison_report(
    gold: list,
    predictions_by_mode: Dict[str, list],
    *,
    n_resamples: int = 1000,
    seed: int = 42,
    amount_threshold_pct: float = 0.20,
) -> ComparisonReport:
    if not gold:
        raise ValueError("gold corpus is empty")
    if not predictions_by_mode:
        raise ValueError("predictions_by_mode must contain at least one mode")

    def _amount_threshold(g: list, p: list) -> float:
        # Closure to match bootstrap_ci's two-arg metric_fn signature.
        return amount_within_threshold(g, p, threshold_pct=amount_threshold_pct)

    metric_fns: Dict[str, Callable[[list, list], float]] = {
        "accuracy": issue_winner_accuracy,
        "amount_threshold": _amount_threshold,
        "brier": brier_score,
        "ece": expected_calibration_error,
    }

    modes_metrics: List[ModeMetrics] = []
    for mode, preds in predictions_by_mode.items():
        results = {
            alias: bootstrap_ci(
                fn, gold, preds, n_resamples=n_resamples, seed=seed
            )
            for alias, fn in metric_fns.items()
        }
        modes_metrics.append(
            ModeMetrics(
                mode=mode,
                accuracy=results["accuracy"],
                amount_threshold=results["amount_threshold"],
                brier=results["brier"],
                ece=results["ece"],
            )
        )

    return ComparisonReport(
        n_cases=len(gold),
        seed=seed,
        n_resamples=n_resamples,
        modes=modes_metrics,
    )


def summarise_dominance(a: ModeMetrics, b: ModeMetrics) -> Dict[str, str]:
    """Per-metric dominance check between two modes.

    Returns one of:
      - "a_dominates" — `a` is significantly better than `b`
      - "b_dominates" — vice versa
      - "no_dominance" — CIs overlap; gap could be noise

    "Significantly" = no overlap between the two CIs in the direction the
    metric prefers. For higher-is-better metrics: a's lower_95 > b's
    upper_95 means a dominates. For lower-is-better metrics: a's upper_95
    < b's lower_95 means a dominates. Mirror image for b dominating.
    """
    out: Dict[str, str] = {}
    for alias in ("accuracy", "amount_threshold", "brier", "ece"):
        ma = a.metric_by_alias(alias)
        mb = b.metric_by_alias(alias)
        lower_better = alias in _LOWER_IS_BETTER
        if lower_better:
            if ma.upper_95 < mb.lower_95:
                out[alias] = "a_dominates"
            elif mb.upper_95 < ma.lower_95:
                out[alias] = "b_dominates"
            else:
                out[alias] = "no_dominance"
        else:
            if ma.lower_95 > mb.upper_95:
                out[alias] = "a_dominates"
            elif mb.lower_95 > ma.upper_95:
                out[alias] = "b_dominates"
            else:
                out[alias] = "no_dominance"
    return out


def report_to_dict(report: ComparisonReport) -> dict:
    """Render a `ComparisonReport` as a JSON-friendly dict for CLI output."""
    return {
        "n_cases": report.n_cases,
        "seed": report.seed,
        "n_resamples": report.n_resamples,
        "modes": [
            {
                "mode": m.mode,
                "accuracy": _metric_to_dict(m.accuracy),
                "amount_threshold": _metric_to_dict(m.amount_threshold),
                "brier": _metric_to_dict(m.brier),
                "ece": _metric_to_dict(m.ece),
            }
            for m in report.modes
        ],
    }


def _metric_to_dict(m: MetricResult) -> dict:
    return {
        "point": m.point,
        "lower_95": m.lower_95,
        "upper_95": m.upper_95,
        "n": m.n,
        "n_resamples": m.n_resamples,
    }
