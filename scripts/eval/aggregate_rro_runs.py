#!/usr/bin/env python3
"""Aggregate RRO 4-mode metrics across N seed runs (mean ± std).

Reads each run's ``_metrics.json`` (written by
``scripts/eval/score_rro_eval.py``) and produces a per-mode mean ± std for
the headline metrics (accuracy, balanced_accuracy, respondent_brier [=
positive-class/landlord Brier], ece, log_loss, determination_accuracy,
amount_bucket_accuracy). Mirrors the shape the cross-domain aggregator
expects.

Usage:
    PYTHONPATH=packages python scripts/eval/aggregate_rro_runs.py \
        --metrics RUN1/_metrics.json RUN2/_metrics.json RUN3/_metrics.json \
        --out data/eval_artifacts/runs/rro_aggregate.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

_FIELDS = (
    "accuracy",
    "balanced_accuracy",
    "respondent_brier",
    "ece",
    "log_loss",
    "determination_accuracy",
    "amount_bucket_accuracy",
)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and x == x  # not NaN


def run(args: argparse.Namespace) -> int:
    per_mode_vals: dict[str, dict[str, list[float]]] = {}
    n_cases_by_mode: dict[str, list[int]] = {}
    for mp in args.metrics:
        path = Path(mp)
        if not path.is_absolute():
            path = REPO_ROOT / path
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data.get("metrics", []):
            mode = m["mode"]
            per_mode_vals.setdefault(mode, {f: [] for f in _FIELDS})
            n_cases_by_mode.setdefault(mode, [])
            n_cases_by_mode[mode].append(m.get("n_cases", 0))
            for f in _FIELDS:
                v = m.get(f)
                if _is_num(v):
                    per_mode_vals[mode][f].append(float(v))

    agg: dict[str, Any] = {"n_runs": len(args.metrics), "modes": {}}
    for mode, fields in per_mode_vals.items():
        agg["modes"][mode] = {"n_cases": max(n_cases_by_mode[mode]) if n_cases_by_mode[mode] else 0}
        for f, vals in fields.items():
            if vals:
                agg["modes"][mode][f] = {
                    "mean": round(statistics.fmean(vals), 4),
                    "std": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
                    "n": len(vals),
                    "values": [round(v, 4) for v in vals],
                }
            else:
                agg["modes"][mode][f] = None

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(agg, indent=2, default=str), encoding="utf-8")
    print(f"aggregate -> {out_path}")

    # Console table.
    hdr = f"{'mode':10s} " + " ".join(f"{f[:10]:>12s}" for f in _FIELDS)
    print(hdr)
    for mode, d in agg["modes"].items():
        cells = []
        for f in _FIELDS:
            v = d.get(f)
            cells.append(f"{v['mean']:.3f}±{v['std']:.3f}" if v else "—")
        print(f"{mode:10s} " + " ".join(f"{c:>12s}" for c in cells))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aggregate RRO 4-mode metrics across seed runs.")
    p.add_argument("--metrics", nargs="+", required=True, help="paths to per-run _metrics.json")
    p.add_argument("--out", default="data/eval_artifacts/runs/rro_aggregate.json")
    return p


def main(argv=None) -> int:
    return run(_parser().parse_args(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
