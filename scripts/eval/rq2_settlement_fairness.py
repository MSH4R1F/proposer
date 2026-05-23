#!/usr/bin/env python3
"""RQ2 — Settlement-fairness evaluation for Outcome-Driven Mediation.

Measures whether the settlement Proposer would propose (the centre of the
ZOPA derived from a predicted outcome) aligns with the *actual* tribunal /
Ombudsman award, compared to a naive market-rate baseline.

Pipeline (per gold case), reusing the production prediction path:

    eval.dataset.load(...)                      -> gold cases
    eval.case_file_adapter.gold_case_to_case_file -> CaseFile
    PredictionEngineV2.predict(mode=LLM_ONLY)   -> PredictionResult
    eval.adapter.from_prediction_result         -> eval Prediction (predicted GBP, P)
    llm_orchestrator...mediator._calculations.compute_zopa -> settlement centre (S)

Metrics (reusing packages/eval/metrics/accuracy.py verbatim) are computed three
ways and reported side by side:
  * model prediction P (total_predicted_gbp)
  * mediator settlement S (ZOPA centre)
  * baseline: leave-one-out median award (the "market-rate anchor")

IMPORTANT LIMITATIONS (state these in the report):
  1. The gold corpora are POST-decision records. They do not preserve the
     parties' pre-decision opening positions, so "split-the-difference" and
     "claimant-claimed" baselines are NOT computable. The only honest naive
     baseline is the median-award anchor.
  2. compute_zopa() is deposit-centric: it keys off predicted_settlement_range,
     else tenant_recovery_amount, else deposit_at_stake. For domains where the
     predictor does not emit those (e.g. employment), the ZOPA degenerates to
     {0,0}; the per-domain `zopa_found_rate` in the summary surfaces this.
  3. n is small (~48-49 per domain) and awards are class-imbalanced.

Default mode is LLM_ONLY, which needs neither the RAG index nor Postgres — only
an LLM client (ANTHROPIC_API_KEY, or OPENAI_API_KEY with --client openai).

Usage:

    PYTHONPATH=packages python scripts/eval/rq2_settlement_fairness.py \\
        --gold   data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \\
        --client claude \\
        --limit  3            # smoke test first, then drop --limit
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import statistics
import sys
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

from eval.adapter import from_prediction_result  # noqa: E402
from eval.case_file_adapter import gold_case_to_case_file  # noqa: E402
from eval.dataset import load  # noqa: E402
from eval.metrics.accuracy import (  # noqa: E402
    amount_coverage,
    amount_mae_gbp,
    amount_mean_signed_error_gbp,
    amount_median_absolute_error_gbp,
    amount_within_absolute_threshold,
    amount_within_threshold,
)

_VALID_CLIENTS = ("claude", "openai", "default")


def _build_llm_client(client_name: str):
    """Mirror scripts/eval/predict_all.py client construction."""
    from llm_orchestrator.clients.factory import get_llm_client
    from llm_orchestrator.config import LLMRole

    if client_name in ("claude", "default"):
        return get_llm_client(LLMRole.PREDICTION)
    if client_name == "openai":
        from llm_orchestrator.clients.openai_client import OpenAIClient

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise SystemExit("--client openai requires OPENAI_API_KEY in .env")
        return OpenAIClient(
            api_key=api_key,
            model=os.getenv("LLM_PREDICTION_PRIMARY_MODEL", "gpt-5.5"),
            fallback_model=os.getenv("LLM_PREDICTION_FALLBACK_MODEL", "gpt-5.4"),
            reasoning_effort=os.getenv("LLM_PREDICTION_REASONING_EFFORT", "high"),
            text_verbosity=os.getenv("LLM_PREDICTION_TEXT_VERBOSITY", "medium"),
            max_retries=3,
        )
    raise SystemExit(f"--client must be one of {_VALID_CLIENTS}; got {client_name!r}")


def _resolve_prompt_pack(domain_id: Optional[str]):
    if not domain_id:
        return None
    try:
        from llm_orchestrator.prompts.packs import get_prompt_pack

        return get_prompt_pack(domain_id)
    except KeyError:
        return None


def _actual_award(gold: Any) -> Optional[float]:
    gt = getattr(gold, "ground_truth_outcome", None)
    raw = getattr(gt, "total_awarded_gbp", None) if gt is not None else None
    if raw is None:
        return None
    try:
        return float(Decimal(str(raw)))
    except Exception:
        return None


def _rel_dev(predicted: Optional[float], actual: Optional[float]) -> Optional[float]:
    if predicted is None or actual is None or actual == 0:
        return None
    return abs(predicted - actual) / actual


def _score_block(golds: list, preds: list) -> dict:
    """Run the reusable amount metrics over aligned (gold, prediction) lists."""
    return {
        "within_20pct": amount_within_threshold(golds, preds, 0.20),
        "amount_at_gbp100": amount_within_absolute_threshold(golds, preds, Decimal("100")),
        "mae_gbp": amount_mae_gbp(golds, preds),
        "median_ae_gbp": amount_median_absolute_error_gbp(golds, preds),
        "mean_signed_error_gbp": amount_mean_signed_error_gbp(golds, preds),
        "coverage": amount_coverage(golds, preds),
    }


def _loo_median(values: list[Optional[float]], i: int) -> Optional[float]:
    others = [v for j, v in enumerate(values) if j != i and v is not None]
    if len(others) < 1:
        return None
    return float(statistics.median(others))


async def _run(args) -> int:
    from llm_orchestrator import PredictionEngineV2
    from llm_orchestrator.models.prediction_v2 import PredictionMode

    mode = PredictionMode(args.mode)
    if mode != PredictionMode.LLM_ONLY:
        print(
            f"[warn] mode={args.mode} needs the RAG index / KG / Postgres wiring that "
            "predict_all.py provides; this RQ2 runner only wires LLM_ONLY. "
            "Re-run with --mode llm_only or extend the runner.",
            file=sys.stderr,
        )

    gold_path = Path(args.gold).resolve()
    loaded = load(gold_path.stem, base_dir=gold_path.parent, strict=True)
    golds = list(loaded.cases)
    if args.limit is not None:
        golds = golds[: args.limit]
    if not golds:
        print(f"Gold corpus at {gold_path} is empty.", file=sys.stderr)
        return 1

    domain_id = getattr(golds[0], "domain_id", None)
    llm = _build_llm_client(args.client)
    # Provenance: --client claude/default defer to LLMRole.PREDICTION, whose
    # provider is env-driven (LLM_PREDICTION_PROVIDER). Record what actually ran
    # rather than the CLI flag, so summary.json never claims Claude when an
    # OpenAI-backed role was used (or vice versa).
    _client_cls = type(llm).__name__
    resolved_provider = (
        "openai"
        if _client_cls == "OpenAIClient"
        else "anthropic"
        if _client_cls == "ClaudeClient"
        else _client_cls
    )
    resolved_model = getattr(llm, "model", None)
    resolved_fallback_model = getattr(llm, "fallback_model", None)
    print(
        f"[provenance] --client {args.client!r} resolved to provider="
        f"{resolved_provider} model={resolved_model} "
        f"fallback={resolved_fallback_model}",
        file=sys.stderr,
    )
    engine = PredictionEngineV2(
        llm_client=llm,
        rag_pipeline=None,
        prompt_pack=_resolve_prompt_pack(domain_id),
    )

    used_golds: list = []
    model_preds: list = []
    zopa_preds: list = []
    actuals: list[Optional[float]] = []
    rows: list[dict] = []
    errors: list[dict] = []
    total_cost_gbp = 0.0

    from llm_orchestrator.tools.mediator._calculations import compute_zopa

    for idx, g in enumerate(golds):
        case_id = getattr(g, "case_id", f"case_{idx}")
        try:
            case_file = gold_case_to_case_file(g).case_file
            pred = await engine.predict(
                case_file,
                knowledge_graph=None,
                top_k=args.top_k,
                mode=mode,
                matter_type=getattr(g, "matter_type", None),
            )
        except Exception as exc:  # one bad case must not kill the run
            errors.append({"case_id": case_id, "error": repr(exc)})
            print(f"[error] {case_id}: {exc}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            continue

        eval_pred = from_prediction_result(pred)
        zopa = compute_zopa(pred)
        settlement = float(zopa["center"])
        zopa_found = bool(zopa["max"] > zopa["min"] and zopa["max"] > 0)
        actual = _actual_award(g)
        predicted_gbp = (
            float(eval_pred.total_predicted_gbp)
            if eval_pred.total_predicted_gbp is not None
            else None
        )

        meta = getattr(pred, "pipeline_metadata", None)
        case_cost = float(getattr(meta, "estimated_cost_gbp", 0.0) or 0.0)
        total_cost_gbp += case_cost

        used_golds.append(g)
        model_preds.append(eval_pred)
        zopa_preds.append(
            dataclasses.replace(
                eval_pred, total_predicted_gbp=Decimal(str(round(settlement, 2)))
            )
        )
        actuals.append(actual)
        rows.append(
            {
                "case_id": case_id,
                "actual_gbp": actual,
                "model_predicted_gbp": predicted_gbp,
                "settlement_center_gbp": round(settlement, 2),
                "zopa_min": zopa["min"],
                "zopa_max": zopa["max"],
                "zopa_found": zopa_found,
                "abstained": bool(eval_pred.abstained),
                "rel_dev_settlement": _rel_dev(settlement, actual),
                "rel_dev_model": _rel_dev(predicted_gbp, actual),
                "est_cost_gbp": case_cost,
            }
        )

    if not used_golds:
        print("No successful predictions; aborting before metrics.", file=sys.stderr)
        return 1

    # Baseline: leave-one-out median award (market-rate anchor).
    baseline_preds = [
        dataclasses.replace(
            ep,
            total_predicted_gbp=(
                Decimal(str(round(m, 2))) if (m := _loo_median(actuals, i)) is not None else None
            ),
        )
        for i, ep in enumerate(model_preds)
    ]

    zopa_found_rate = sum(1 for r in rows if r["zopa_found"]) / len(rows)
    settlement_rel_devs = [r["rel_dev_settlement"] for r in rows if r["rel_dev_settlement"] is not None]

    summary = {
        "experiment": "rq2_settlement_fairness",
        "gold": gold_path.name,
        "domain_id": domain_id,
        "mode": mode.value,
        "client_flag": args.client,
        "resolved_provider": resolved_provider,
        "resolved_model": resolved_model,
        "resolved_fallback_model": resolved_fallback_model,
        "n_cases": len(golds),
        "n_scored": len(used_golds),
        "n_errors": len(errors),
        "zopa_found_rate": round(zopa_found_rate, 4),
        "settlement_rel_dev_mean": (
            round(statistics.mean(settlement_rel_devs), 4) if settlement_rel_devs else None
        ),
        "settlement_rel_dev_median": (
            round(statistics.median(settlement_rel_devs), 4) if settlement_rel_devs else None
        ),
        "estimated_total_cost_gbp": round(total_cost_gbp, 4),
        "model_prediction": _score_block(used_golds, model_preds),
        "mediator_settlement_zopa_center": _score_block(used_golds, zopa_preds),
        "baseline_loo_median_award": _score_block(used_golds, baseline_preds),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else _REPO_ROOT / "data" / "eval_artifacts" / "runs" / f"rq2_settlement_{gold_path.stem}_{ts}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "per_case.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    if errors:
        (out_dir / "errors.jsonl").write_text(
            "\n".join(json.dumps(e) for e in errors) + "\n", encoding="utf-8"
        )

    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote {len(rows)} rows + summary to {out_dir}")
    return 0


def _cli(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="scripts/eval/rq2_settlement_fairness.py")
    p.add_argument("--gold", required=True, help="Path to a gold-standard JSONL file.")
    p.add_argument("--client", choices=_VALID_CLIENTS, default="claude")
    p.add_argument("--mode", default="llm_only", help="PredictionMode value (default llm_only).")
    p.add_argument("--limit", type=int, default=None, help="Cap cases (smoke test).")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--verbose", action="store_true", help="Print full tracebacks on per-case errors.")
    args = p.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(_cli())
