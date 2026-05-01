#!/usr/bin/env python3
"""Phase 5b live runner — emit per-mode prediction JSONLs from a gold corpus.

Loops `(gold_case, mode)` pairs through:
    eval.case_file_adapter.gold_case_to_case_file
    → predict_fn(case_file, mode)
    → eval.adapter.from_prediction_result
    → JSONL row

In the default `--engine stub` mode, `predict_fn = make_stub_prediction`,
no LLM is touched, and CI exercises the full chain. The output JSONLs
feed `python -m eval.ablate` directly.

`--engine live` is a TODO sentinel — raises until a real `BaseLLMClient`
is wired in (the choice of provider/model is a project-level decision
deferred from this PR).

Usage:

    PYTHONPATH=packages python scripts/eval/predict_all.py \\
        --gold       data/gold_standard/housing_v1.jsonl \\
        --out-dir    eval/predictions/run_2026-05-01 \\
        --engine     stub \\
        --modes      hybrid,rag_only,kg_only,llm_only \\
        --limit      10
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

# Allow running the script directly: prepend packages/ to sys.path.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval._stub_prediction import make_stub_prediction  # noqa: E402
from eval.adapter import from_prediction_result  # noqa: E402
from eval.case_file_adapter import gold_case_to_case_file  # noqa: E402
from eval.dataset import load  # noqa: E402

_VALID_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")


def _live_predict_fn(case_file, mode):
    raise NotImplementedError(
        "engine='live' requires a real BaseLLMClient + PredictionEngineV2 wiring; "
        "deferred from Phase 5b PR. Use --engine stub for CI / pipeline checks; "
        "wire your LLM client (Anthropic/OpenAI key) in a follow-up before the "
        "thesis ablation table is generated."
    )


def _stub_predict_fn(case_file, mode):
    return make_stub_prediction(case_file, mode)


def _resolve_predict_fn(engine: str) -> Callable:
    if engine == "stub":
        return _stub_predict_fn
    if engine == "live":
        return _live_predict_fn
    raise ValueError(f"Unknown --engine {engine!r}; expected 'stub' or 'live'")


def _serialise_prediction(pred) -> dict:
    """Convert eval.metrics.Prediction → JSON-friendly dict (matches the
    shape eval.run._load_predictions consumes)."""
    return {
        "case_id": pred.case_id,
        "overall_winner": pred.overall_winner.value,
        "overall_win_probability": float(pred.overall_win_probability),
        "total_predicted_gbp": str(pred.total_predicted_gbp),
        "per_issue": [
            {
                "issue": ip.issue,
                "predicted_winner": ip.predicted_winner.value,
                "win_probability": float(ip.win_probability),
                "predicted_amount_gbp": str(ip.predicted_amount_gbp),
            }
            for ip in pred.per_issue
        ],
    }


def _resolve_mode_enum(mode_value: str):
    """Map a mode string to PredictionMode. Imported lazily so unit tests
    that don't touch live mode don't pay the orchestrator import cost."""
    from llm_orchestrator.models.prediction_v2 import PredictionMode

    return PredictionMode(mode_value)


def _run(
    gold_cases: list,
    modes: List[str],
    *,
    predict_fn: Callable,
    out_dir: Path,
) -> Dict[str, int]:
    """Run the (gold × mode) loop. Returns counters used by the summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    unmapped_total: Counter = Counter()
    cases_done = 0

    for mode_str in modes:
        mode_enum = _resolve_mode_enum(mode_str)
        out_path = out_dir / f"{mode_str}.jsonl"
        with out_path.open("w") as f:
            for g in gold_cases:
                recon = gold_case_to_case_file(g)
                for ct in recon.unmapped_claim_types:
                    unmapped_total[ct] += 1
                pred_result = predict_fn(recon.case_file, mode_enum)
                eval_pred = from_prediction_result(pred_result)
                _apply_gold_issue_label_alignment(
                    eval_pred, recon.gold_issue_labels_by_claim_type
                )
                f.write(json.dumps(_serialise_prediction(eval_pred)) + "\n")
        cases_done = len(gold_cases)

    return {
        "cases_per_mode": cases_done,
        "modes": len(modes),
        "unmapped_claim_types": dict(unmapped_total),
    }


def _apply_gold_issue_label_alignment(pred, label_map: dict[str, str]) -> None:
    """Rewrite eval ClaimType issue keys to the gold case's claimed labels.

    Gold per-issue metrics join on `ground_truth_outcome.per_issue[].issue`,
    which is a free-text claimed-amount label. `eval.adapter` can only normalise
    orchestrator enum values to eval `ClaimType` values. The reconstructor
    supplies a one-to-one map from pre-decision claimed labels when that map is
    unambiguous; otherwise this is a no-op and metrics count missing labels in
    the usual conservative way.
    """
    if not label_map:
        return
    for issue_prediction in pred.per_issue:
        issue_prediction.issue = label_map.get(
            issue_prediction.issue, issue_prediction.issue
        )


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/eval/predict_all.py")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--engine",
        choices=("stub", "live"),
        default="stub",
        help="stub: deterministic stand-in (CI). live: real LLM (deferred wiring).",
    )
    parser.add_argument(
        "--modes",
        default=",".join(_VALID_MODES),
        help=(
            "Comma-separated PredictionMode values. Default runs all four. "
            f"Valid: {','.join(_VALID_MODES)}"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap on the number of gold cases to predict (default: all).",
    )
    args = parser.parse_args(argv)

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    invalid = [m for m in modes if m not in _VALID_MODES]
    if invalid:
        print(f"Unknown mode(s): {invalid}; valid: {_VALID_MODES}", file=sys.stderr)
        return 2

    predict_fn = _resolve_predict_fn(args.engine)

    # Load gold
    gold_load = load(args.gold.stem, base_dir=args.gold.parent, strict=True)
    gold_cases = gold_load.cases
    if args.limit is not None:
        gold_cases = gold_cases[: args.limit]
    if not gold_cases:
        print(f"Gold corpus at {args.gold} is empty.", file=sys.stderr)
        return 1

    summary = _run(
        gold_cases,
        modes,
        predict_fn=predict_fn,
        out_dir=args.out_dir,
    )

    # Human-readable summary to stdout (also a CI signal that alignment
    # incidents happened).
    print(
        f"Wrote {summary['modes']} prediction file(s) × "
        f"{summary['cases_per_mode']} case(s) into {args.out_dir}"
    )
    if summary["unmapped_claim_types"]:
        print("Unmappable claim types encountered (per case occurrence):")
        for ct, count in sorted(summary["unmapped_claim_types"].items()):
            print(f"  - {ct}: {count}")
    else:
        print("All gold claim types mapped cleanly to DisputeIssue.")

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
