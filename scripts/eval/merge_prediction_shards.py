#!/usr/bin/env python3
"""Merge sharded prediction runs into one run dir the scorer can consume.

``run_employment_et_predictions.py --num-shards M --shard-index k`` writes
each shard to its own run dir. This concatenates the per-mode JSONLs
across all shards into a single merged run dir plus a ``_summary.json``
so ``score_employment_et_eval.py --run-dir <merged>`` works unchanged.

Usage:

    venv/bin/python scripts/eval/merge_prediction_shards.py \\
        --out-dir  data/eval_artifacts/runs/<domain>/<merged_run_id> \\
        --shard-dir data/eval_artifacts/runs/<domain>/<run>-shard0 \\
        --shard-dir data/eval_artifacts/runs/<domain>/<run>-shard1 ...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def _modes_in(shard_dir: Path) -> list[str]:
    return sorted(
        p.name[len("predictions_") : -len(".jsonl")]
        for p in shard_dir.glob("predictions_*.jsonl")
    )


def merge(out_dir: Path, shard_dirs: Sequence[Path]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    modes = _modes_in(shard_dirs[0])
    per_mode_counts: dict[str, int] = {}
    for mode in modes:
        seen: set[str] = set()
        lines: list[str] = []
        for sd in shard_dirs:
            f = sd / f"predictions_{mode}.jsonl"
            if not f.exists():
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                cid = json.loads(line).get("case_id")
                if cid in seen:  # dedupe defensively
                    continue
                seen.add(cid)
                lines.append(line)
        (out_dir / f"predictions_{mode}.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        per_mode_counts[mode] = len(lines)

    # Carry forward the first shard's summary (provider/seed metadata) and
    # repoint the mode outputs at the merged files.
    base_summary = {}
    s0 = shard_dirs[0] / "_summary.json"
    if s0.exists():
        base_summary = json.loads(s0.read_text(encoding="utf-8"))
    base_summary["modes"] = [
        {"mode": m, "n_rows": per_mode_counts[m], "output": str(out_dir / f"predictions_{m}.jsonl")}
        for m in modes
    ]
    base_summary["merged_from_shards"] = [str(p) for p in shard_dirs]
    base_summary["n_gold_cases"] = max(per_mode_counts.values()) if per_mode_counts else 0
    (out_dir / "_summary.json").write_text(
        json.dumps(base_summary, indent=2, default=str), encoding="utf-8"
    )
    return {"out_dir": str(out_dir), "modes": per_mode_counts}


def _cli(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=Path(__file__).name)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--shard-dir", action="append", required=True, type=Path, dest="shard_dirs")
    args = p.parse_args(list(argv) if argv is not None else None)
    result = merge(args.out_dir, args.shard_dirs)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
