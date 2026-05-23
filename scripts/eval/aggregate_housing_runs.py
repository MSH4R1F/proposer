#!/usr/bin/env python3
"""Aggregate N housing eval runs into mean ± std per mode per metric.

Reads several ``_metrics.json`` files (each emitted by
``scripts/eval/score_housing_eval.py`` — the employment-compatible shape)
and produces a combined ``_aggregate.json`` with mean ± std across runs
for the headline metrics, plus a markdown table.

Usage:

    PYTHONPATH=packages python scripts/eval/aggregate_housing_runs.py \\
        --metrics run_seed1/_metrics.json run_seed2/_metrics.json run_seed3/_metrics.json \\
        --out data/eval_artifacts/runs/housing_150_aggregate.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

_HEADLINE = (
    "accuracy",
    "balanced_accuracy",
    "respondent_brier",
    "ece",
    "log_loss",
    "determination_accuracy",
    "abstention_rate",
)
_MODES = ("llm_only", "rag_only", "kg_only", "hybrid")


def _mean_std(vals: list[float]) -> tuple[float, float]:
    clean = [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not clean:
        return float("nan"), float("nan")
    if len(clean) == 1:
        return clean[0], 0.0
    return statistics.mean(clean), statistics.pstdev(clean)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", nargs="+", required=True, help="paths to per-run _metrics.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()

    # mode -> metric -> [values across runs]
    collected: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    n_cases_by_mode: dict[str, list[int]] = defaultdict(list)
    run_paths = []
    for mp in args.metrics:
        p = Path(mp)
        if not p.is_absolute():
            p = REPO_ROOT / p
        run_paths.append(str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        for m in data.get("metrics", []):
            mode = m["mode"]
            n_cases_by_mode[mode].append(int(m.get("n_cases") or 0))
            for metric in _HEADLINE:
                v = m.get(metric)
                if v is not None:
                    collected[mode][metric].append(float(v))

    agg: dict[str, Any] = {"n_runs": len(args.metrics), "run_metrics_paths": run_paths, "modes": {}}
    for mode in _MODES:
        if mode not in collected:
            continue
        per_metric: dict[str, Any] = {}
        for metric in _HEADLINE:
            mean, std = _mean_std(collected[mode].get(metric, []))
            per_metric[metric] = {"mean": mean, "std": std, "values": collected[mode].get(metric, [])}
        agg["modes"][mode] = {
            "n_cases": n_cases_by_mode[mode][0] if n_cases_by_mode[mode] else None,
            "metrics": per_metric,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(agg, indent=2, default=str), encoding="utf-8")

    # Markdown table
    def fmt(mode: str, metric: str) -> str:
        d = agg["modes"].get(mode, {}).get("metrics", {}).get(metric)
        if not d or (isinstance(d["mean"], float) and math.isnan(d["mean"])):
            return "—"
        return f"{d['mean']:.3f} ± {d['std']:.3f}"

    lines = [
        f"# Housing Ombudsman 150-gold 4-mode ablation ({agg['n_runs']} seeds, mean ± std)",
        "",
        "| Mode | n | Accuracy | Bal-Acc | Brier (L) | LogLoss | Det-Acc |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode in _MODES:
        if mode not in agg["modes"]:
            continue
        n = agg["modes"][mode]["n_cases"]
        lines.append(
            f"| `{mode}` | {n} | {fmt(mode,'accuracy')} | {fmt(mode,'balanced_accuracy')} | "
            f"{fmt(mode,'respondent_brier')} | {fmt(mode,'log_loss')} | {fmt(mode,'determination_accuracy')} |"
        )
    lines.append("")
    lines.append("*Brier (L): positive class = landlord winner; lower is better (0.25 = coin flip).*")
    lines.append("*Det-Acc: 6-class determination accuracy — the discriminative merits target on this corpus.*")
    report = "\n".join(lines)

    if args.report:
        rp = args.report if args.report.is_absolute() else REPO_ROOT / args.report
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(report, encoding="utf-8")
        print(f"report -> {rp}")
    print(f"aggregate -> {args.out}")
    print()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
