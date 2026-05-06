"""CLI orchestrator: load corpus + predictions, compute a metric with
bootstrap CI, emit JSON report.

Usage:
    PYTHONPATH=packages python -m eval.run --metric accuracy --gold ... --predictions ...
    PYTHONPATH=packages python -m eval.run --metric brier   --gold ... --predictions ... --out report.json
    PYTHONPATH=packages python -m eval.run --metric ece     --gold ... --predictions ... --no-bootstrap
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence

from pydantic import ValidationError

from eval.dataset import load
from eval.metrics import (
    IssuePrediction,
    Prediction,
    abstention_rate,
    balanced_accuracy,
    bootstrap_ci,
    brier_score,
    coverage_adjusted_accuracy,
    covered_accuracy,
    expected_calibration_error,
    issue_winner_accuracy,
    macro_f1,
)
from eval.metrics.types import MetricResult
from eval.schema import Winner

_METRICS = {
    "abstention_rate": abstention_rate,
    "accuracy": issue_winner_accuracy,
    "balanced_accuracy": balanced_accuracy,
    "brier": brier_score,
    "coverage_adjusted_accuracy": coverage_adjusted_accuracy,
    "covered_accuracy": covered_accuracy,
    "ece": expected_calibration_error,
    "macro_f1": macro_f1,
}


def _load_predictions(path: Path) -> list:
    """Read JSONL of predicted cases, return `list[Prediction]`."""
    if not path.exists():
        raise FileNotFoundError(f"Predictions file not found: {path}")
    preds: list = []
    with path.open() as f:
        for line_no, raw in enumerate(f, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            try:
                preds.append(_dict_to_prediction(data))
            except Exception as e:
                raise ValueError(
                    f"line {line_no} of {path}: {e}"
                ) from e
    return preds


def _dict_to_prediction(d: dict) -> Prediction:
    return Prediction(
        case_id=d["case_id"],
        overall_winner=Winner(d["overall_winner"]),
        overall_win_probability=float(d["overall_win_probability"]),
        total_predicted_gbp=_optional_decimal(d.get("total_predicted_gbp")),
        per_issue=[
            IssuePrediction(
                issue=ip["issue"],
                predicted_winner=Winner(ip["predicted_winner"]),
                win_probability=float(ip["win_probability"]),
                predicted_amount_gbp=_optional_decimal(
                    ip.get("predicted_amount_gbp")
                ),
                abstained=bool(
                    ip.get("abstained")
                    or ip.get("raw_outcome") in {"uncertain", "unknown"}
                ),
            )
            for ip in d.get("per_issue", [])
        ],
        abstained=bool(
            d.get("abstained")
            or d.get("raw_overall_outcome") in {"uncertain", "unknown"}
        ),
    )


def _optional_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _check_alignment(gold: list, predictions: list) -> None:
    """Raise if gold and predictions don't share the same case_ids in order."""
    if len(gold) != len(predictions):
        raise ValueError(
            f"length mismatch: gold has {len(gold)} cases, "
            f"predictions has {len(predictions)}"
        )
    for g, p in zip(gold, predictions):
        if g.case_id != p.case_id:
            raise ValueError(
                f"case_id mismatch in aligned order: "
                f"gold={g.case_id!r} vs prediction={p.case_id!r}. "
                "Sort both inputs by case_id before running."
            )


def _format_report(
    metric_name: str,
    metric_fn_name: str,
    gold_path: Path,
    predictions_path: Path,
    result: MetricResult,
    seed: int,
) -> dict:
    return {
        "metric": metric_fn_name,
        "metric_alias": metric_name,
        "gold_path": str(gold_path),
        "predictions_path": str(predictions_path),
        "point": result.point,
        "lower_95": result.lower_95,
        "upper_95": result.upper_95,
        "n": result.n,
        "n_resamples": result.n_resamples,
        "seed": seed,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run")
    parser.add_argument(
        "--metric",
        required=True,
        choices=sorted(_METRICS),
        help="Which metric to compute.",
    )
    parser.add_argument(
        "--gold",
        required=True,
        type=Path,
        help="Path to a gold-set JSONL (e.g. data/gold_standard/housing_v1.jsonl).",
    )
    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
        help="Path to predictions JSONL.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to PATH instead of stdout.",
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Skip bootstrap CI; emit point estimate only.",
    )
    parser.add_argument(
        "--n-resamples",
        type=int,
        default=1000,
        help="Bootstrap resample count (default 1000; ignored with --no-bootstrap).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Bootstrap RNG seed for determinism (default 42).",
    )
    args = parser.parse_args(argv)

    metric_fn = _METRICS[args.metric]
    try:
        gold_load = load(args.gold.stem, base_dir=args.gold.parent, strict=True)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as e:
        print(f"Gold set load error: {e}", file=sys.stderr)
        return 1
    if not gold_load.cases:
        print(f"Gold set at {args.gold} contains no valid cases.", file=sys.stderr)
        return 1
    try:
        predictions = _load_predictions(args.predictions)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"Predictions load error: {e}", file=sys.stderr)
        return 1

    try:
        _check_alignment(gold_load.cases, predictions)
    except ValueError as e:
        print(f"Alignment error: {e}", file=sys.stderr)
        return 1

    n_resamples = 0 if args.no_bootstrap else args.n_resamples
    result = bootstrap_ci(
        metric_fn,
        gold_load.cases,
        predictions,
        n_resamples=n_resamples,
        seed=args.seed,
    )

    report = _format_report(
        metric_name=args.metric,
        metric_fn_name=metric_fn.__name__,
        gold_path=args.gold,
        predictions_path=args.predictions,
        result=result,
        seed=args.seed,
    )

    payload = json.dumps(report, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
