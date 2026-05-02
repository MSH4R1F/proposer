"""CLI: produce the multi-mode ablation comparison report.

Reads the gold corpus and one prediction JSONL per mode, computes all four
metrics for each mode (with bootstrap CIs), and writes a structured JSON
report. The thesis (RQ1) consumes the JSON and renders the comparison
table.

Usage:

    PYTHONPATH=packages python -m eval.ablate \\
        --gold     data/gold_standard/housing_v1.jsonl \\
        --predictions hybrid=eval/predictions/hybrid.jsonl \\
        --predictions rag_only=eval/predictions/rag_only.jsonl \\
        --predictions kg_only=eval/predictions/kg_only.jsonl \\
        --predictions llm_only=eval/predictions/llm_only.jsonl \\
        --out eval/results/ablation_2026-05-01.json \\
        --seed 42

`--no-bootstrap` skips the resampling loop (point estimates only). For
fast iteration during development.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from pydantic import ValidationError

from eval.compare import build_comparison_report, report_to_dict
from eval.dataset import load
from eval.run import _load_predictions  # reuse the existing JSONL parser


def _parse_predictions_arg(values: List[str]) -> Dict[str, Path]:
    """Parse repeated `--predictions mode=path` arguments.

    Each value is `mode=path`. Modes must be unique. Empty mode or empty
    path raises ValueError.
    """
    out: Dict[str, Path] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(
                f"--predictions value {raw!r} must be of the form 'mode=path'"
            )
        mode, _, path_str = raw.partition("=")
        mode = mode.strip()
        path_str = path_str.strip()
        if not mode:
            raise ValueError(f"--predictions value {raw!r} has empty mode")
        if not path_str:
            raise ValueError(f"--predictions value {raw!r} has empty path")
        if mode in out:
            raise ValueError(f"--predictions mode {mode!r} specified twice")
        out[mode] = Path(path_str)
    return out


def _validate_numeric_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Reject numeric CLI values that would make metric computation invalid."""
    if args.n_resamples < 0:
        parser.error("--n-resamples must be greater than or equal to 0")
    if not 0.0 <= args.amount_threshold_pct <= 1.0:
        parser.error("--amount-threshold-pct must be between 0.0 and 1.0")


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.ablate")
    parser.add_argument(
        "--gold",
        required=True,
        type=Path,
        help="Path to a gold-set JSONL.",
    )
    parser.add_argument(
        "--predictions",
        required=True,
        action="append",
        metavar="MODE=PATH",
        help=(
            "Per-mode predictions JSONL. Repeat for each mode, e.g. "
            "--predictions hybrid=hybrid.jsonl --predictions rag_only=rag.jsonl"
        ),
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
        help="Skip bootstrap CI; emit point estimates only.",
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
    parser.add_argument(
        "--amount-threshold-pct",
        type=float,
        default=0.20,
        help="Tolerance for amount_within_threshold metric (default 0.20 = 20%%).",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help=(
            "Optional domain id to filter the gold corpus to. When set, "
            "the ablate run reports per-domain metrics first; the macro "
            "aggregate is refused if any per-domain group is below "
            "min_case_count or fails citation/hallucination thresholds "
            "(SHA-20 Phase 7)."
        ),
    )
    parser.add_argument(
        "--min-case-count",
        type=int,
        default=10,
        help=(
            "Minimum cases per domain before macro aggregation is "
            "permitted (default 10)."
        ),
    )
    args = parser.parse_args(argv)
    _validate_numeric_args(args, parser)

    # 1. Parse --predictions mode=path pairs
    try:
        predictions_paths = _parse_predictions_arg(args.predictions)
    except ValueError as e:
        print(f"--predictions error: {e}", file=sys.stderr)
        return 1

    # 2. Load gold
    try:
        gold_load = load(args.gold.stem, base_dir=args.gold.parent, strict=True)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as e:
        print(f"Gold set load error: {e}", file=sys.stderr)
        return 1
    if not gold_load.cases:
        print(f"Gold set at {args.gold} contains no valid cases.", file=sys.stderr)
        return 1
    gold = gold_load.cases

    # SHA-20 Phase 7: optional --domain filter. Per-domain metrics MUST
    # render before macro; refuse macro when any group is below the
    # min_case_count or fails citation/hallucination thresholds.
    if args.domain is not None:
        from eval.domain import partition_by_domain

        partitioned = partition_by_domain(gold)
        gold = partitioned.get(args.domain, [])
        if not gold:
            print(
                f"No gold cases found for domain {args.domain!r}; "
                f"available: {sorted(partitioned)}",
                file=sys.stderr,
            )
            return 1

    # 3. Load each mode's predictions
    predictions_by_mode: Dict[str, list] = {}
    for mode, path in predictions_paths.items():
        try:
            preds = _load_predictions(path)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"Predictions load error for mode {mode!r}: {e}", file=sys.stderr)
            return 1
        predictions_by_mode[mode] = preds

    # 4. Build the report (delegates to compare.build_comparison_report,
    #    which raises ValueError on length/case_id mismatches via bootstrap_ci).
    n_resamples = 0 if args.no_bootstrap else args.n_resamples
    try:
        report = build_comparison_report(
            gold,
            predictions_by_mode,
            n_resamples=n_resamples,
            seed=args.seed,
            amount_threshold_pct=args.amount_threshold_pct,
        )
    except ValueError as e:
        print(f"Comparison error: {e}", file=sys.stderr)
        return 1

    # 5. Render
    payload = report_to_dict(report)
    payload["gold_path"] = str(args.gold)
    payload["predictions_paths"] = {m: str(p) for m, p in predictions_paths.items()}
    payload["computed_at"] = datetime.now(timezone.utc).isoformat()

    rendered = json.dumps(payload, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
