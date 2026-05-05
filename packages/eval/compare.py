"""Multi-mode comparison report — the RQ1 ablation artifact.

Given a gold corpus and predictions emitted by each `PredictionMode` (HYBRID,
RAG_ONLY, KG_ONLY, LLM_ONLY), `build_comparison_report` computes accuracy,
amount metrics, Brier, and ECE for each mode (with bootstrap CIs) and produces
a single `ComparisonReport` that the thesis can table or chart. The report
also includes deterministic baselines so majority-class or claim-copy shortcuts
are visible beside the model modes.

`summarise_dominance` answers the harder question: did one mode beat
another *significantly*, or is the gap inside the resampling noise?

The functions are pure (no I/O). The CLI wrapper lives at `eval.ablate`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, List

from eval.metrics import (
    amount_coverage,
    amount_mae_gbp,
    amount_mean_signed_error_gbp,
    amount_median_absolute_error_gbp,
    amount_within_absolute_threshold,
    amount_within_threshold,
    bootstrap_ci,
    brier_score,
    expected_calibration_error,
    issue_winner_accuracy,
)
from eval.case_file_adapter import (
    is_outcome_derived_ombudsman_claimed_amount,
    is_outcome_derived_ombudsman_disputed_amount,
)
from eval.metrics.types import MetricResult
from eval.schema import PartyRole, Winner


# Lower-is-better metrics need flipped dominance logic.
_LOWER_IS_BETTER = {
    "amount_mae_gbp",
    "amount_median_absolute_error_gbp",
    "brier",
    "ece",
}
_AMOUNT_ABSOLUTE_THRESHOLD_GBP = Decimal("100")


@dataclass
class ModeMetrics:
    mode: str
    accuracy: MetricResult
    amount_threshold: MetricResult
    brier: MetricResult
    ece: MetricResult
    amount_within_20pct: MetricResult | None = None
    amount_within_gbp100: MetricResult | None = None
    amount_mae_gbp: MetricResult | None = None
    amount_median_absolute_error_gbp: MetricResult | None = None
    amount_mean_signed_error_gbp: MetricResult | None = None
    amount_coverage: dict[str, int] = field(default_factory=dict)

    def metric_by_alias(self, alias: str) -> MetricResult:
        """Return the metric stored under the public alias used by the CLI."""
        mapping = {
            "accuracy": self.accuracy,
            "amount_threshold": self.amount_threshold,
            "amount_within_20pct": self.amount_within_20pct,
            "amount_within_gbp100": self.amount_within_gbp100,
            "amount_mae_gbp": self.amount_mae_gbp,
            "amount_median_absolute_error_gbp": self.amount_median_absolute_error_gbp,
            "amount_mean_signed_error_gbp": self.amount_mean_signed_error_gbp,
            "brier": self.brier,
            "ece": self.ece,
        }
        if alias not in mapping or mapping[alias] is None:
            raise KeyError(
                f"unknown metric alias {alias!r}; expected one of "
                f"{sorted(k for k, v in mapping.items() if v is not None)}"
            )
        return mapping[alias]


@dataclass
class DeterministicBaselineMetrics:
    baseline: str
    description: str
    winner_supported: bool
    amount_supported: bool
    metrics: ModeMetrics


@dataclass
class ComparisonReport:
    n_cases: int
    seed: int
    n_resamples: int
    amount_threshold_pct: float = 0.20
    amount_absolute_threshold_gbp: Decimal = _AMOUNT_ABSOLUTE_THRESHOLD_GBP
    modes: List[ModeMetrics] = field(default_factory=list)
    baselines: List[DeterministicBaselineMetrics] = field(default_factory=list)

    def ranked_by(
        self, alias: str, *, ascending: bool | None = None
    ) -> List[ModeMetrics]:
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


@dataclass(frozen=True)
class _BaselineIssuePrediction:
    issue: str
    predicted_winner: Winner
    win_probability: float
    predicted_amount_gbp: Decimal | None = None


@dataclass(frozen=True)
class _BaselinePrediction:
    case_id: str
    overall_winner: Winner
    overall_win_probability: float
    total_predicted_gbp: Decimal | None
    per_issue: list[_BaselineIssuePrediction]


@dataclass(frozen=True)
class _BaselineSpec:
    name: str
    description: str
    predictions: list[_BaselinePrediction]
    winner_supported: bool
    amount_supported: bool


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

    def _amount_threshold_20pct(g: list, p: list) -> float:
        return amount_within_threshold(g, p, threshold_pct=0.20)

    def _amount_threshold_custom(g: list, p: list) -> float:
        # Closure to match bootstrap_ci's two-arg metric_fn signature.
        return amount_within_threshold(g, p, threshold_pct=amount_threshold_pct)

    def _amount_threshold_gbp100(g: list, p: list) -> float:
        return amount_within_absolute_threshold(
            g, p, threshold_gbp=_AMOUNT_ABSOLUTE_THRESHOLD_GBP
        )

    metric_fns: Dict[str, Callable[[list, list], float]] = {
        "accuracy": issue_winner_accuracy,
        "amount_threshold": _amount_threshold_custom,
        "amount_within_20pct": _amount_threshold_20pct,
        "amount_within_gbp100": _amount_threshold_gbp100,
        "amount_mae_gbp": amount_mae_gbp,
        "amount_median_absolute_error_gbp": amount_median_absolute_error_gbp,
        "amount_mean_signed_error_gbp": amount_mean_signed_error_gbp,
        "brier": brier_score,
        "ece": expected_calibration_error,
    }

    modes_metrics: List[ModeMetrics] = []
    for mode, preds in predictions_by_mode.items():
        modes_metrics.append(
            _compute_mode_metrics(
                mode=mode,
                gold=gold,
                predictions=preds,
                metric_fns=metric_fns,
                n_resamples=n_resamples,
                seed=seed,
            )
        )

    baselines = [
        _compute_baseline_metrics(
            baseline,
            gold=gold,
            metric_fns=metric_fns,
            n_resamples=n_resamples,
            seed=seed,
        )
        for baseline in _build_deterministic_baselines(gold)
    ]

    return ComparisonReport(
        n_cases=len(gold),
        seed=seed,
        n_resamples=n_resamples,
        amount_threshold_pct=amount_threshold_pct,
        amount_absolute_threshold_gbp=_AMOUNT_ABSOLUTE_THRESHOLD_GBP,
        modes=modes_metrics,
        baselines=baselines,
    )


def _compute_mode_metrics(
    *,
    mode: str,
    gold: list,
    predictions: list,
    metric_fns: Dict[str, Callable[[list, list], float]],
    n_resamples: int,
    seed: int,
) -> ModeMetrics:
    results = {
        alias: bootstrap_ci(fn, gold, predictions, n_resamples=n_resamples, seed=seed)
        for alias, fn in metric_fns.items()
    }
    return ModeMetrics(
        mode=mode,
        accuracy=results["accuracy"],
        amount_threshold=results["amount_threshold"],
        amount_within_20pct=results["amount_within_20pct"],
        amount_within_gbp100=results["amount_within_gbp100"],
        amount_mae_gbp=results["amount_mae_gbp"],
        amount_median_absolute_error_gbp=results["amount_median_absolute_error_gbp"],
        amount_mean_signed_error_gbp=results["amount_mean_signed_error_gbp"],
        amount_coverage=amount_coverage(gold, predictions),
        brier=results["brier"],
        ece=results["ece"],
    )


def _compute_baseline_metrics(
    baseline: _BaselineSpec,
    *,
    gold: list,
    metric_fns: Dict[str, Callable[[list, list], float]],
    n_resamples: int,
    seed: int,
) -> DeterministicBaselineMetrics:
    metrics = _compute_mode_metrics(
        mode=baseline.name,
        gold=gold,
        predictions=baseline.predictions,
        metric_fns=metric_fns,
        n_resamples=n_resamples,
        seed=seed,
    )
    return DeterministicBaselineMetrics(
        baseline=baseline.name,
        description=baseline.description,
        winner_supported=baseline.winner_supported,
        amount_supported=baseline.amount_supported,
        metrics=metrics,
    )


def _build_deterministic_baselines(gold: list) -> list[_BaselineSpec]:
    claim_positive = _claim_positive_predictions(gold, copy_amount=False)
    claim_amount_copy = _claim_positive_predictions(gold, copy_amount=True)
    return [
        _BaselineSpec(
            name="always_tenant",
            description="Predict tenant wins every case/issue; no amount estimate.",
            predictions=_always_winner_predictions(gold, Winner.TENANT),
            winner_supported=True,
            amount_supported=False,
        ),
        _BaselineSpec(
            name="always_landlord",
            description="Predict landlord wins every case/issue; no amount estimate.",
            predictions=_always_winner_predictions(gold, Winner.LANDLORD),
            winner_supported=True,
            amount_supported=False,
        ),
        _BaselineSpec(
            name="claim_positive_winner",
            description=(
                "Predict the positive claimant wins; split when both tenant "
                "and landlord/agent have positive claims."
            ),
            predictions=claim_positive,
            winner_supported=_all_cases_have_claimed_amounts(gold),
            amount_supported=False,
        ),
        _BaselineSpec(
            name="claim_amount_copy",
            description=(
                "Use the claim-positive winner rule and copy the canonical "
                "disputed amount as the total predicted award."
            ),
            predictions=claim_amount_copy,
            winner_supported=_all_cases_have_claimed_amounts(gold),
            amount_supported=amount_coverage(gold, claim_amount_copy)["n_evaluable"]
            > 0,
        ),
    ]


def _always_winner_predictions(gold: list, winner: Winner) -> list[_BaselinePrediction]:
    probability = _probability_for_winner(winner)
    out: list[_BaselinePrediction] = []
    for g in gold:
        per_issue = [
            _BaselineIssuePrediction(
                issue=io.issue,
                predicted_winner=winner,
                win_probability=probability,
            )
            for io in getattr(g.ground_truth_outcome, "per_issue", [])
        ]
        out.append(
            _BaselinePrediction(
                case_id=g.case_id,
                overall_winner=winner,
                overall_win_probability=probability,
                total_predicted_gbp=None,
                per_issue=per_issue,
            )
        )
    return out


def _claim_positive_predictions(
    gold: list, *, copy_amount: bool
) -> list[_BaselinePrediction]:
    out: list[_BaselinePrediction] = []
    for g in gold:
        claimed_amounts = _pre_decision_claimed_amounts(g)
        overall_winner, overall_probability = _claim_winner_and_probability(
            claimed_amounts
        )
        per_issue = []
        for io in getattr(g.ground_truth_outcome, "per_issue", []):
            issue_claims = [ca for ca in claimed_amounts if ca.issue == io.issue]
            issue_winner, issue_probability = _claim_winner_and_probability(
                issue_claims
            )
            per_issue.append(
                _BaselineIssuePrediction(
                    issue=io.issue,
                    predicted_winner=issue_winner,
                    win_probability=issue_probability,
                    predicted_amount_gbp=(
                        _claim_amount_for_issue(issue_claims) if copy_amount else None
                    ),
                )
            )
        out.append(
            _BaselinePrediction(
                case_id=g.case_id,
                overall_winner=overall_winner,
                overall_win_probability=overall_probability,
                total_predicted_gbp=(
                    _claim_amount_for_case(g) if copy_amount else None
                ),
                per_issue=per_issue,
            )
        )
    return out


def _claim_winner_and_probability(claimed_amounts: list) -> tuple[Winner, float]:
    tenant_total = Decimal("0")
    landlord_total = Decimal("0")
    for claim in claimed_amounts:
        amount = _coerce_amount(getattr(claim, "amount_gbp", None))
        if amount is None or amount <= 0:
            continue
        party_raw = getattr(claim, "by_party", None)
        party = getattr(party_raw, "value", party_raw)
        if party == PartyRole.TENANT.value:
            tenant_total += amount
        elif party in {PartyRole.LANDLORD.value, PartyRole.AGENT.value}:
            landlord_total += amount

    if tenant_total > 0 and landlord_total > 0:
        return Winner.SPLIT, 0.5
    if landlord_total > 0:
        return Winner.LANDLORD, 1.0
    if tenant_total > 0:
        return Winner.TENANT, 0.0
    return Winner.SPLIT, 0.5


def _probability_for_winner(winner: Winner) -> float:
    if winner == Winner.LANDLORD:
        return 1.0
    if winner == Winner.TENANT:
        return 0.0
    return 0.5


def _claim_amount_for_case(gold_case) -> Decimal | None:
    disputed = None
    if not is_outcome_derived_ombudsman_disputed_amount(gold_case):
        disputed = _coerce_amount(getattr(gold_case, "disputed_amount_gbp", None))
    if disputed is not None:
        return disputed

    by_issue: dict[str, Decimal] = {}
    for claim in _pre_decision_claimed_amounts(gold_case):
        amount = _coerce_amount(getattr(claim, "amount_gbp", None))
        if amount is None:
            continue
        issue = getattr(claim, "issue", "")
        by_issue[issue] = max(by_issue.get(issue, Decimal("0")), amount)
    if not by_issue:
        return None
    return sum(by_issue.values(), Decimal("0"))


def _claim_amount_for_issue(claimed_amounts: list) -> Decimal | None:
    amounts = [
        amount
        for amount in (
            _coerce_amount(getattr(claim, "amount_gbp", None))
            for claim in claimed_amounts
        )
        if amount is not None
    ]
    if not amounts:
        return None
    return max(amounts)


def _coerce_amount(value) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def _all_cases_have_claimed_amounts(gold: list) -> bool:
    return all(bool(_pre_decision_claimed_amounts(g)) for g in gold)


def _pre_decision_claimed_amounts(gold_case) -> list:
    """Return claimed amounts that were available before the decision.

    Legacy Housing Ombudsman review artifacts can contain the final global
    compensation order copied into `claimed_amounts`. Baselines must not use
    that answer-field copy as though it were a real claimant demand.
    """
    return [
        claim
        for claim in getattr(gold_case, "claimed_amounts", []) or []
        if not is_outcome_derived_ombudsman_claimed_amount(gold_case, claim)
    ]


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
        "amount_threshold_pct": report.amount_threshold_pct,
        "amount_absolute_threshold_gbp": str(report.amount_absolute_threshold_gbp),
        "modes": [_mode_metrics_to_dict(m, label_key="mode") for m in report.modes],
        "baselines": [
            _baseline_metrics_to_dict(baseline) for baseline in report.baselines
        ],
    }


def _mode_metrics_to_dict(m: ModeMetrics, *, label_key: str) -> dict:
    return {
        label_key: m.mode,
        "accuracy": _metric_to_dict(m.accuracy),
        # Legacy key retained for existing callers: amount@20% by default.
        "amount_threshold": _metric_to_dict(m.amount_threshold),
        "amount": _amount_metrics_to_dict(m),
        "brier": _metric_to_dict(m.brier),
        "ece": _metric_to_dict(m.ece),
    }


def _baseline_metrics_to_dict(baseline: DeterministicBaselineMetrics) -> dict:
    out = _mode_metrics_to_dict(baseline.metrics, label_key="baseline")
    out["description"] = baseline.description
    out["supported"] = {
        "winner": baseline.winner_supported,
        "amount": baseline.amount_supported,
    }
    return out


def _amount_metrics_to_dict(m: ModeMetrics) -> dict:
    return {
        "within_20pct": _optional_metric_to_dict(m.amount_within_20pct),
        "within_gbp100": _optional_metric_to_dict(m.amount_within_gbp100),
        "mae_gbp": _optional_metric_to_dict(m.amount_mae_gbp),
        "median_absolute_error_gbp": _optional_metric_to_dict(
            m.amount_median_absolute_error_gbp
        ),
        "mean_signed_error_gbp": _optional_metric_to_dict(
            m.amount_mean_signed_error_gbp
        ),
        "coverage": dict(m.amount_coverage),
    }


def _optional_metric_to_dict(m: MetricResult | None) -> dict | None:
    if m is None:
        return None
    return _metric_to_dict(m)


def _metric_to_dict(m: MetricResult) -> dict:
    return {
        "point": m.point,
        "lower_95": m.lower_95,
        "upper_95": m.upper_95,
        "n": m.n,
        "n_resamples": m.n_resamples,
    }
