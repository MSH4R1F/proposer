#!/usr/bin/env python3
"""Run the full gold-set eval bundle for one prediction run.

This is a thin orchestrator around the existing eval CLIs:

* ``python -m eval.dataset audit``
* ``python -m eval.run`` for accuracy/Brier/ECE per mode
* ``python -m eval.ablate`` for the four-mode comparison report

It intentionally does not fabricate labels. The ``--gold`` input must be an
adjudicated GoldCase JSONL, not a selection manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")
DEFAULT_METRICS = (
    "accuracy",
    "balanced_accuracy",
    "macro_f1",
    "abstention_rate",
    "covered_accuracy",
    "coverage_adjusted_accuracy",
    "brier",
    "ece",
)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    packages = str(REPO_ROOT / "packages")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = packages if not current else f"{packages}{os.pathsep}{current}"
    return env


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _require_ok(proc: subprocess.CompletedProcess[str]) -> None:
    if proc.stdout.strip():
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _metric_point(metric: dict[str, Any] | None) -> float | None:
    if not isinstance(metric, dict):
        return None
    point = metric.get("point")
    return float(point) if point is not None else None


def _metric_ci(metric: dict[str, Any] | None) -> list[float | None]:
    if not isinstance(metric, dict):
        return [None, None]
    return [metric.get("lower_95"), metric.get("upper_95")]


def _summarise_eval_row(row: dict[str, Any]) -> dict[str, Any]:
    amount = row.get("amount", {})
    amount_threshold = row.get("amount_threshold")
    within_20pct = amount.get("within_20pct") if isinstance(amount, dict) else None
    within_gbp100 = amount.get("within_gbp100") if isinstance(amount, dict) else None
    mae = amount.get("mae_gbp") if isinstance(amount, dict) else None
    median_ae = (
        amount.get("median_absolute_error_gbp") if isinstance(amount, dict) else None
    )
    bias = amount.get("mean_signed_error_gbp") if isinstance(amount, dict) else None

    return {
        "accuracy": _metric_point(row.get("accuracy")),
        "accuracy_ci": _metric_ci(row.get("accuracy")),
        "balanced_accuracy": _metric_point(row.get("balanced_accuracy")),
        "balanced_accuracy_ci": _metric_ci(row.get("balanced_accuracy")),
        "macro_f1": _metric_point(row.get("macro_f1")),
        "macro_f1_ci": _metric_ci(row.get("macro_f1")),
        "abstention_rate": _metric_point(row.get("abstention_rate")),
        "abstention_rate_ci": _metric_ci(row.get("abstention_rate")),
        "covered_accuracy": _metric_point(row.get("covered_accuracy")),
        "covered_accuracy_ci": _metric_ci(row.get("covered_accuracy")),
        "coverage_adjusted_accuracy": _metric_point(
            row.get("coverage_adjusted_accuracy")
        ),
        "coverage_adjusted_accuracy_ci": _metric_ci(
            row.get("coverage_adjusted_accuracy")
        ),
        "brier": _metric_point(row.get("brier")),
        "brier_ci": _metric_ci(row.get("brier")),
        "ece": _metric_point(row.get("ece")),
        # Legacy flat key retained for callers reading amount@20%.
        "amount_threshold": _metric_point(amount_threshold),
        "amount_threshold_ci": _metric_ci(amount_threshold),
        "amount_within_20pct": _metric_point(within_20pct),
        "amount_within_gbp100": _metric_point(within_gbp100),
        "amount_mae_gbp": _metric_point(mae),
        "amount_median_absolute_error_gbp": _metric_point(median_ae),
        "amount_mean_signed_error_gbp": _metric_point(bias),
        "amount": amount,
        "n": row["accuracy"]["n"],
    }


def _format_optional(value: float | None, *, precision: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{precision}f}"


def _default_out_dir(gold: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "eval" / "results" / f"{gold.stem}_full_eval_{timestamp}"


def run(args: argparse.Namespace) -> None:
    gold = args.gold.expanduser()
    if not gold.is_absolute():
        gold = REPO_ROOT / gold

    predictions_dir = args.predictions_dir.expanduser()
    if not predictions_dir.is_absolute():
        predictions_dir = REPO_ROOT / predictions_dir

    out_dir = args.out_dir or _default_out_dir(gold)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    prediction_paths = {mode: predictions_dir / f"{mode}.jsonl" for mode in modes}
    missing = [str(path) for path in prediction_paths.values() if not path.exists()]
    if missing:
        raise SystemExit("missing prediction file(s): " + ", ".join(missing))

    audit_path = out_dir / "audit.json"
    metric_dir = out_dir / "metrics"
    ablation_path = out_dir / "ablation.json"

    audit_cmd = [
        sys.executable,
        "-m",
        "eval.dataset",
        "audit",
        str(gold),
        "--json",
        str(audit_path),
    ]
    if args.strict_audit:
        audit_cmd.append("--strict")
    audit_proc = _run(audit_cmd)
    _require_ok(audit_proc)

    metric_outputs: dict[str, dict[str, str]] = {}
    for mode, pred_path in prediction_paths.items():
        metric_outputs[mode] = {}
        for metric in metrics:
            out_path = metric_dir / f"{mode}_{metric}.json"
            cmd = [
                sys.executable,
                "-m",
                "eval.run",
                "--metric",
                metric,
                "--gold",
                str(gold),
                "--predictions",
                str(pred_path),
                "--out",
                str(out_path),
                "--seed",
                str(args.seed),
            ]
            if args.no_bootstrap:
                cmd.append("--no-bootstrap")
            else:
                cmd.extend(["--n-resamples", str(args.n_resamples)])
            proc = _run(cmd)
            _require_ok(proc)
            metric_outputs[mode][metric] = str(out_path)

    ablate_cmd = [
        sys.executable,
        "-m",
        "eval.ablate",
        "--gold",
        str(gold),
        "--out",
        str(ablation_path),
        "--seed",
        str(args.seed),
        "--amount-threshold-pct",
        str(args.amount_threshold_pct),
        "--min-case-count",
        str(args.min_case_count),
    ]
    if args.no_bootstrap:
        ablate_cmd.append("--no-bootstrap")
    else:
        ablate_cmd.extend(["--n-resamples", str(args.n_resamples)])
    if args.domain:
        ablate_cmd.extend(["--domain", args.domain])
    for mode, pred_path in prediction_paths.items():
        ablate_cmd.extend(["--predictions", f"{mode}={pred_path}"])

    ablate_proc = _run(ablate_cmd)
    _require_ok(ablate_proc)

    ablation = _read_json(ablation_path)
    audit = _read_json(audit_path)
    by_mode = {row["mode"]: _summarise_eval_row(row) for row in ablation["modes"]}
    by_baseline = {}
    for row in ablation.get("baselines", []):
        summary_row = _summarise_eval_row(row)
        summary_row["description"] = row.get("description")
        summary_row["supported"] = row.get("supported", {})
        by_baseline[row["baseline"]] = summary_row

    summary = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "gold": str(gold),
        "predictions_dir": str(predictions_dir),
        "out_dir": str(out_dir),
        "audit": audit,
        "modes": by_mode,
        "baselines": by_baseline,
        "metric_outputs": metric_outputs,
        "ablation": str(ablation_path),
        "seed": args.seed,
        "n_resamples": 0 if args.no_bootstrap else args.n_resamples,
    }
    summary_path = out_dir / "summary.json"
    _write_json(summary_path, summary)

    print("\nFull eval complete")
    print(f"out_dir: {out_dir}")
    print(f"audit: {audit_path}")
    print(f"ablation: {ablation_path}")
    print(f"summary: {summary_path}")
    print("\nPoint estimates:")
    for mode, row in by_mode.items():
        custom_amount = ""
        if abs(args.amount_threshold_pct - 0.20) > 1e-9:
            custom_amount = (
                f"amount@{args.amount_threshold_pct:.0%}="
                f"{_format_optional(row['amount_threshold'])}, "
            )
        print(
            f"  {mode}: "
            f"accuracy={_format_optional(row['accuracy'])}, "
            f"balanced_accuracy={_format_optional(row['balanced_accuracy'])}, "
            f"macro_f1={_format_optional(row['macro_f1'])}, "
            f"abstention_rate={_format_optional(row['abstention_rate'])}, "
            f"covered_accuracy={_format_optional(row['covered_accuracy'])}, "
            f"coverage_adjusted_accuracy={_format_optional(row['coverage_adjusted_accuracy'])}, "
            f"brier={_format_optional(row['brier'])}, "
            f"ece={_format_optional(row['ece'])}, "
            f"{custom_amount}"
            f"amount@20%={_format_optional(row['amount_within_20pct'])}, "
            f"amount@GBP100={_format_optional(row['amount_within_gbp100'])}, "
            f"mae_gbp={_format_optional(row['amount_mae_gbp'])}, "
            f"bias_gbp={_format_optional(row['amount_mean_signed_error_gbp'])}, "
            f"amount_n={row.get('amount', {}).get('coverage', {}).get('n_evaluable', 0)}, "
            f"n={row['n']}"
        )
    if by_baseline:
        print("\nDeterministic baselines:")
        for baseline, row in by_baseline.items():
            print(
                f"  {baseline}: "
                f"accuracy={_format_optional(row['accuracy'])}, "
                f"balanced_accuracy={_format_optional(row['balanced_accuracy'])}, "
                f"macro_f1={_format_optional(row['macro_f1'])}, "
                f"abstention_rate={_format_optional(row['abstention_rate'])}, "
                f"coverage_adjusted_accuracy={_format_optional(row['coverage_adjusted_accuracy'])}, "
                f"brier={_format_optional(row['brier'])}, "
                f"amount@GBP100={_format_optional(row['amount_within_gbp100'])}, "
                f"mae_gbp={_format_optional(row['amount_mae_gbp'])}, "
                f"amount_n={row.get('amount', {}).get('coverage', {}).get('n_evaluable', 0)}, "
                f"n={row['n']}"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run audit, per-mode metrics, and ablation for a gold set."
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path("data/gold_standard/housing_repairs_social_v1.jsonl"),
    )
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=Path("eval/predictions/housing_ombudsman_gold_pilot_20260504"),
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--modes", default=",".join(DEFAULT_MODES))
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--domain", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-resamples", type=int, default=1000)
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--strict-audit", action="store_true")
    parser.add_argument("--min-case-count", type=int, default=10)
    parser.add_argument("--amount-threshold-pct", type=float, default=0.20)
    return parser


def main(argv: list[str] | None = None) -> int:
    run(_parser().parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
