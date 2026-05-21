#!/usr/bin/env python3
"""Aggregate metrics across multiple ET ablation runs.

Single-run accuracy on n=49 with 8 minority-class claimant cases is
noisy: a single LLM call drift on one Pyman/Spencer-shaped case moves
headline accuracy by ~2pp. This script consumes the ``_metrics.json``
output from several runs of ``run_employment_et_predictions.py`` and
emits mean ± stdev per (mode, metric) so the structural-vs-noise
question can be answered honestly.

Usage:

    venv/bin/python scripts/eval/aggregate_employment_et_runs.py \\
        data/eval_artifacts/runs/employment_unfair_dismissal_v1/<run_a> \\
        data/eval_artifacts/runs/employment_unfair_dismissal_v1/<run_b> \\
        ...

The script writes both a markdown summary (to stdout) and a JSON
payload (to ``--out``).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Sequence

METRIC_KEYS = (
    "accuracy",
    "balanced_accuracy",
    "respondent_brier",
    "ece",
    "log_loss",
    "determination_accuracy",
    "abstention_rate",
)


def _load_metrics(run_dir: Path) -> dict[str, dict[str, float]]:
    metrics_path = run_dir / "_metrics.json"
    if not metrics_path.exists():
        raise SystemExit(f"missing _metrics.json under {run_dir}")
    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    return {row["mode"]: row for row in data["metrics"]}


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return mean, std


def aggregate(run_dirs: Sequence[Path]) -> dict:
    per_run = [_load_metrics(rd) for rd in run_dirs]
    modes = sorted({m for run in per_run for m in run.keys()})
    out: dict = {
        "n_runs": len(run_dirs),
        "run_dirs": [str(p) for p in run_dirs],
        "modes": {},
    }
    for mode in modes:
        agg: dict[str, dict[str, float]] = {}
        for key in METRIC_KEYS:
            values: list[float] = []
            for run in per_run:
                row = run.get(mode)
                if row is None or row.get(key) is None:
                    continue
                values.append(float(row[key]))
            mean, std = _mean_std(values)
            agg[key] = {
                "mean": mean,
                "stdev": std,
                "n": len(values),
                "values": values,
            }
        out["modes"][mode] = agg
    return out


def _fmt(mean: float, std: float, *, pct: bool = False) -> str:
    if mean != mean:  # NaN
        return "—"
    if pct:
        return f"{mean * 100:.1f}±{std * 100:.1f}%"
    return f"{mean:.4f}±{std:.4f}"


def render_markdown(agg: dict) -> str:
    out: list[str] = []
    out.append(f"# ET ablation — mean ± std across {agg['n_runs']} runs")
    out.append("")
    out.append("| Mode | Accuracy | Bal-Acc | Brier (R) | LogLoss | Det-Acc |")
    out.append("|---|---|---|---|---|---|")
    for mode, mvals in sorted(agg["modes"].items()):
        row = [
            f"`{mode}`",
            _fmt(mvals["accuracy"]["mean"], mvals["accuracy"]["stdev"], pct=True),
            _fmt(
                mvals["balanced_accuracy"]["mean"],
                mvals["balanced_accuracy"]["stdev"],
            ),
            _fmt(mvals["respondent_brier"]["mean"], mvals["respondent_brier"]["stdev"]),
            _fmt(mvals["log_loss"]["mean"], mvals["log_loss"]["stdev"]),
            _fmt(
                mvals["determination_accuracy"]["mean"],
                mvals["determination_accuracy"]["stdev"],
                pct=True,
            ),
        ]
        out.append("| " + " | ".join(row) + " |")
    out.append("")
    out.append("Single-run accuracy is unreliable: with 8 minority-class")
    out.append("claimant cases in n=49, a single Pyman/Spencer-shaped flip")
    out.append("moves headline accuracy by ~2pp. Bal-acc, Brier, and")
    out.append("determination accuracy aggregate sub-case signal and are")
    out.append("the metrics to track across runs.")
    return "\n".join(out)


def _cli_main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=Path(__file__).name)
    p.add_argument("run_dirs", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(list(argv) if argv is not None else None)
    agg = aggregate(args.run_dirs)
    md = render_markdown(agg)
    print(md)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(agg, indent=2, default=str), encoding="utf-8"
        )
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
