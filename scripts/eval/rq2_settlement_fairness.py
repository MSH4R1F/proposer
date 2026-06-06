#!/usr/bin/env python3
"""RQ2 — Settlement-fairness evaluation for Outcome-Driven Mediation.

Measures whether the settlement Proposer would propose (the centre of the
ZOPA derived from a predicted outcome) aligns with the *actual* tribunal /
Ombudsman award, compared to a naive median-award baseline.

This runner supports a 4-arm ablation that separates the "always predict a
monetary quantum" *policy* (env flags) from the retrieval / KG *capability*
(prediction mode), so the causal comparison is fair:

    legacy_llm_only_strict   mode=llm_only   (no flags)            -> current degenerate control
    llm_only_always_predict  mode=llm_only   STREAM_C_NO_RAG_PREDICT_AMOUNTS=1
    rag_only_always_predict  mode=rag_only   STREAM_C_ALWAYS_PREDICT_AMOUNTS=1
    hybrid_always_predict    mode=hybrid     STREAM_C_ALWAYS_PREDICT_AMOUNTS=1

The flags are read inside the predictor; this runner only selects the mode and
wires retrieval/KG. It builds the RAG pipeline + KG inline and ``await``s
``engine.predict`` directly (it does NOT call predict_all's sync ``_live_call``,
which runs its own ``asyncio.run`` and would dead-lock inside our event loop).

Metrics (reusing packages/eval/metrics/accuracy.py) are computed for the model
amount P, the mediator settlement S (ZOPA centre), and the leave-one-out
median-award baseline. ``zopa_found_rate`` is a *coverage/plumbing* metric, not
success evidence; success is judged by award alignment + a paired bootstrap of
the model-minus-baseline error delta.

Usage:

    PYTHONPATH=.:packages STREAM_C_ALWAYS_PREDICT_AMOUNTS=1 \\
      python scripts/eval/rq2_settlement_fairness.py \\
        --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \\
        --mode rag_only --arm rag_only_always_predict --client default \\
        --rag-index-root indices --limit 3   # smoke first, then drop --limit
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import random
import statistics
import sys
import traceback
from datetime import date as _date, datetime, timezone
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
from llm_orchestrator.pipeline.issue_predictor import _extract_order_amounts  # noqa: E402

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


def _decision_date(gold: Any) -> Optional[_date]:
    d = getattr(gold, "decision_date", None)
    return d if isinstance(d, _date) else None


def _rel_dev(predicted: Optional[float], actual: Optional[float]) -> Optional[float]:
    if predicted is None or actual is None or actual == 0:
        return None
    return abs(predicted - actual) / actual


def _score_block(golds: list, preds: list) -> dict:
    """Run the reusable amount metrics over aligned (gold, prediction) lists."""
    if not golds:
        return {"n": 0}
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


def _temporal_loo_median(
    values: list[Optional[float]], dates: list[Optional[_date]], i: int
) -> Optional[float]:
    """Median award over OTHER cases decided on or before case i's date.

    A causally honest baseline when retrieval is temporally filtered: only past
    awards are visible at prediction time. Falls back to None when case i has no
    date or no prior-dated case carries an award.
    """
    di = dates[i]
    if di is None:
        return None
    past = [
        v
        for j, (v, dj) in enumerate(zip(values, dates))
        if j != i and v is not None and dj is not None and dj <= di
    ]
    if not past:
        return None
    return float(statistics.median(past))


def _paired_bootstrap(
    deltas: list[float], *, seed: int = 42, n_resamples: int = 1000
) -> Optional[dict]:
    """Bootstrap the mean of per-case deltas (baseline_AE - settlement_AE).

    Positive ⇒ the settlement is closer to the award than the baseline. The CI
    crossing zero ⇒ no significant difference.
    """
    if not deltas:
        return None
    point = sum(deltas) / len(deltas)
    n = len(deltas)
    if n == 1:
        return {"point": point, "lower_95": point, "upper_95": point, "n": 1}
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        s = [deltas[rng.randrange(n)] for _ in range(n)]
        means.append(sum(s) / n)
    means.sort()
    lo = means[int(0.025 * n_resamples)]
    hi = means[int(0.975 * n_resamples)]
    return {"point": round(point, 2), "lower_95": round(lo, 2), "upper_95": round(hi, 2), "n": n}


def _retrieval_award_info(pred: Any) -> dict:
    """Pull retrieval logging + grounding signal from PredictionResult.

    ``amount_anchor_source`` is derived here (review point 2) from whether any
    retrieved chunk's text carried a £ figure — a retrieval-side coverage
    signal, computed over the serialised ``text_preview`` (capped ~500 chars),
    NOT a claim about which figure the model ultimately used.
    """
    src_ids: list[str] = []
    chunk_ids: list[str] = []
    amount_src_ids: list[str] = []
    comp_amounts: list[float] = []
    evidence = getattr(pred, "retrieval_evidence", None) or {}
    for ev in evidence.values():
        for r in (ev or {}).get("results", []) or []:
            cid = r.get("chunk_id")
            sid = r.get("source_id")
            if cid is not None:
                chunk_ids.append(str(cid))
            if sid is not None:
                src_ids.append(str(sid))
            amts = _extract_order_amounts(
                str(r.get("text_preview") or ""), r.get("section_type")
            )
            if amts:
                comp_amounts.extend(amts)
                if sid is not None:
                    amount_src_ids.append(str(sid))
    return {
        "retrieved_source_ids": src_ids,
        "amount_source_ids": amount_src_ids,
        "chunk_ids": chunk_ids,
        "comparator_amounts": comp_amounts,
        "dup_chunk_count": len(chunk_ids) - len(set(chunk_ids)),
    }


async def _build_pipeline_cached(gold_case: Any, rag_index_root: Optional[Path], cache: dict):
    """Replicate predict_all's nested ``_pipeline_for`` (module-level helpers)."""
    from scripts.eval.predict_all import (
        _decision_date_coverage,
        _ensure_rag_index_exists,
        _rag_config_for_namespace,
        _select_namespace,
    )
    from rag_engine.pipeline import RAGPipeline

    domain_id = str(getattr(gold_case, "domain_id", "") or "")
    namespace_id = getattr(gold_case, "retrieval_namespace_id", None)
    namespace = _select_namespace(domain_id, namespace_id)
    key = (domain_id, namespace.namespace_id, str(rag_index_root))
    if key in cache:
        return cache[key]
    cfg = _rag_config_for_namespace(namespace, rag_index_root)
    _ensure_rag_index_exists(cfg, namespace)
    rag = RAGPipeline(config=cfg, namespace=namespace)
    has_temporal = _decision_date_coverage(rag) >= 0.90
    cache[key] = (rag, namespace, has_temporal)
    return cache[key]


async def _run(args) -> int:
    from llm_orchestrator import PredictionEngineV2
    from llm_orchestrator.models.prediction_v2 import PredictionMode
    from llm_orchestrator.tools.mediator._calculations import compute_zopa
    from scripts.eval.predict_all import (
        _build_eval_knowledge_graph,
        _build_eval_retrieval_filter,
        _EvalFilteredRAGPipeline,
        _PropositionRetrieverShim,
        _resolve_factor_assertion_sidecar_path,
    )

    from llm_orchestrator.models.prediction_v2 import RetrievalStrategy

    # `--mode agentic` is sugar for the agentic GraphRAG predictor: it runs under
    # mode=HYBRID with retrieval_strategy=AGENTIC_PREDICT and needs RAG + KG.
    agentic = args.mode == "agentic"
    retrieval_strategy = RetrievalStrategy.AGENTIC_PREDICT if agentic else None
    mode = PredictionMode.HYBRID if agentic else PredictionMode(args.mode)
    needs_rag = agentic or mode in (PredictionMode.RAG_ONLY, PredictionMode.HYBRID)
    needs_kg = agentic or mode in (PredictionMode.HYBRID, PredictionMode.KG_ONLY)

    rag_index_root: Optional[Path] = None
    if needs_rag:
        root = Path(args.rag_index_root) if args.rag_index_root else (_REPO_ROOT / "indices")
        rag_index_root = root if root.exists() else None

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
    _client_cls = type(llm).__name__
    resolved_provider = (
        "openai"
        if _client_cls == "OpenAIClient"
        else "anthropic"
        if _client_cls == "ClaudeClient"
        else _client_cls
    )
    flags = {
        k: os.getenv(k, "0")
        for k in (
            "STREAM_C_ALWAYS_PREDICT_AMOUNTS",
            "STREAM_C_NO_RAG_PREDICT_AMOUNTS",
            "STREAM_C_FACTOR_RETRIEVAL",
            "STREAM_C_KG_GATE_RELAXED",
            "STREAM_C_PROPOSITION_TAG_FUZZY",
            "STREAM_C_PR4",
        )
    }
    print(
        f"[provenance] arm={args.arm!r} mode={mode.value} provider={resolved_provider} "
        f"model={getattr(llm, 'model', None)} flags={flags}",
        file=sys.stderr,
    )

    prompt_pack = _resolve_prompt_pack(domain_id)
    pipeline_cache: dict = {}

    # KG backfill (hybrid/kg_only): load the factor-assertion sidecar + JSONL
    # proposition store so the graph-quality gate can fire (kg_used_for_prediction
    # → True). Mirrors predict_all; no Postgres needed. Without these the KG is
    # inert (graph_quality 0). Requires the STREAM_C_KG_GATE_RELAXED / _FACTOR_
    # RETRIEVAL / _PROPOSITION_TAG_FUZZY env flags on the run to actually engage.
    factor_assertion_sidecar = None
    proposition_store = None
    if needs_kg:
        from eval.factor_assertion_sidecar import load_full_sidecar

        sc_path = _resolve_factor_assertion_sidecar_path(gold_path, None)
        if sc_path.exists():
            factor_assertion_sidecar = load_full_sidecar(sc_path)
            print(f"[kg] loaded factor-assertion sidecar {sc_path.name}", file=sys.stderr)
        else:
            print(f"[kg][warn] no factor-assertion sidecar at {sc_path}", file=sys.stderr)
        ps_path = (
            _REPO_ROOT / "data" / "eval_artifacts" / "propositions"
            / "housing_repairs_social_v1.propositions.tagged.jsonl"
        )
        if ps_path.exists():
            from kg_builder.storage.jsonl_proposition_store import JsonlPropositionStore

            proposition_store = JsonlPropositionStore.from_path(ps_path)
            print(f"[kg] loaded {len(proposition_store)} propositions", file=sys.stderr)
        else:
            print(f"[kg][warn] no proposition store at {ps_path}", file=sys.stderr)

    used_golds: list = []
    model_preds: list = []
    zopa_preds: list = []
    actuals: list[Optional[float]] = []
    dates: list[Optional[_date]] = []
    rows: list[dict] = []
    errors: list[dict] = []
    any_temporal = False

    for idx, g in enumerate(golds):
        case_id = getattr(g, "case_id", f"case_{idx}")
        try:
            case_file = gold_case_to_case_file(g).case_file
            rag_pipeline = None
            excluded_ids: set[str] = set()
            if needs_rag:
                rag, namespace, has_temporal = await _build_pipeline_cached(
                    g, rag_index_root, pipeline_cache
                )
                any_temporal = any_temporal or has_temporal
                filters = _build_eval_retrieval_filter(
                    g, include_temporal=bool(args.temporal_filters and has_temporal)
                )
                excluded_ids = set(str(x) for x in getattr(filters, "excluded_source_ids", []) or [])
                rag_pipeline = _EvalFilteredRAGPipeline(
                    rag, filters, requesting_namespace=namespace
                )
            knowledge_graph = None
            if needs_kg:
                knowledge_graph = _build_eval_knowledge_graph(
                    case_file, domain_id,
                    factor_assertion_sidecar=factor_assertion_sidecar,
                )
            engine = PredictionEngineV2(
                llm_client=llm,
                rag_pipeline=rag_pipeline,
                prompt_pack=prompt_pack,
                proposition_retriever=(
                    _PropositionRetrieverShim(proposition_store)
                    if proposition_store is not None
                    else None
                ),
            )
            pred = await engine.predict(
                case_file,
                knowledge_graph=knowledge_graph,
                top_k=args.top_k,
                mode=mode,
                retrieval_strategy=retrieval_strategy,
                matter_type=getattr(g, "matter_type", None),
                gold_case_id=str(case_id),
            )
        except Exception as exc:  # one bad case must not kill the run
            errors.append({"case_id": case_id, "error": repr(exc)})
            print(f"[error] {case_id}: {exc}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            continue

        eval_pred = from_prediction_result(pred)
        zopa = compute_zopa(pred)
        zmin, zmax, settlement = float(zopa["min"]), float(zopa["max"]), float(zopa["center"])
        zopa_found = bool(zmax > zmin and zmax > 0)
        actual = _actual_award(g)
        predicted_gbp = (
            float(eval_pred.total_predicted_gbp)
            if eval_pred.total_predicted_gbp is not None
            else None
        )

        info = _retrieval_award_info(pred)
        comp_amounts = info["comparator_amounts"]
        anchor_source = (
            "comparator"
            if comp_amounts
            else ("free_estimate" if predicted_gbp is not None else "none")
        )
        comparator_median = (
            float(statistics.median(comp_amounts)) if comp_amounts else None
        )
        actual_within_zopa = (
            bool(actual is not None and zopa_found and zmin <= actual <= zmax)
        )
        over_under = None
        if actual is not None:
            over_under = "over" if settlement > actual else "under" if settlement < actual else "exact"
        leakage_ok = not (set(info["retrieved_source_ids"]) & excluded_ids)

        justification = ""
        if pred.issue_predictions:
            justification = (pred.issue_predictions[0].reasoning or "")[:300]

        meta = getattr(pred, "pipeline_metadata", None)

        used_golds.append(g)
        model_preds.append(eval_pred)
        zopa_preds.append(
            dataclasses.replace(
                eval_pred, total_predicted_gbp=Decimal(str(round(settlement, 2)))
            )
        )
        actuals.append(actual)
        dates.append(_decision_date(g))
        rows.append(
            {
                "case_id": case_id,
                "actual_gbp": actual,
                "model_predicted_gbp": predicted_gbp,
                "settlement_center_gbp": round(settlement, 2),
                "zopa_min": round(zmin, 2),
                "zopa_max": round(zmax, 2),
                "zopa_width": round(zmax - zmin, 2),
                "zopa_found": zopa_found,
                "actual_within_zopa": actual_within_zopa,
                "over_under": over_under,
                "amount_anchor_source": anchor_source,
                "comparator_count": len(comp_amounts),
                "comparator_median_gbp": comparator_median,
                "abstained": bool(eval_pred.abstained),
                "rel_dev_settlement": _rel_dev(settlement, actual),
                "rel_dev_model": _rel_dev(predicted_gbp, actual),
                "retrieved_source_ids": info["retrieved_source_ids"],
                "amount_source_ids": info["amount_source_ids"],
                "n_retrieved": len(info["chunk_ids"]),
                "dup_chunk_count": info["dup_chunk_count"],
                "leakage_excluded_count": len(excluded_ids),
                "leakage_ok": leakage_ok,
                "justification": justification,
                "kg_used": getattr(meta, "kg_used_for_prediction", None),
                "graph_quality_score": getattr(meta, "graph_quality_score", None),
            }
        )

    if not used_golds:
        print("No successful predictions; aborting before metrics.", file=sys.stderr)
        return 1

    # Baselines.
    baseline_preds = [
        dataclasses.replace(
            ep,
            total_predicted_gbp=(
                Decimal(str(round(m, 2))) if (m := _loo_median(actuals, i)) is not None else None
            ),
        )
        for i, ep in enumerate(model_preds)
    ]
    temporal_preds = [
        dataclasses.replace(
            ep,
            total_predicted_gbp=(
                Decimal(str(round(m, 2)))
                if (m := _temporal_loo_median(actuals, dates, i)) is not None
                else None
            ),
        )
        for i, ep in enumerate(model_preds)
    ]
    has_temporal_baseline = any(
        p.total_predicted_gbp is not None for p in temporal_preds
    )

    # Paired bootstrap: settlement vs LOO-median baseline on the evaluable subset.
    deltas: list[float] = []
    for i, a in enumerate(actuals):
        if a is None:
            continue
        s = float(rows[i]["settlement_center_gbp"])
        b = _loo_median(actuals, i)
        if b is None:
            continue
        deltas.append(abs(b - a) - abs(s - a))  # +ve ⇒ settlement closer

    # Disaggregate the settlement block by grounding source.
    def _subset(pred_label: str) -> dict:
        idxs = [i for i, r in enumerate(rows) if r["amount_anchor_source"] == pred_label]
        return _score_block(
            [used_golds[i] for i in idxs], [zopa_preds[i] for i in idxs]
        )

    zopa_found_rate = sum(1 for r in rows if r["zopa_found"]) / len(rows)
    actual_within_zopa_rate = sum(1 for r in rows if r["actual_within_zopa"]) / len(rows)
    widths = [r["zopa_width"] for r in rows if r["zopa_found"]]
    grounding_mix = {
        k: sum(1 for r in rows if r["amount_anchor_source"] == k)
        for k in ("comparator", "free_estimate", "none")
    }
    over_under_mix = {
        k: sum(1 for r in rows if r["over_under"] == k)
        for k in ("over", "under", "exact")
    }
    settlement_rel_devs = [
        r["rel_dev_settlement"] for r in rows if r["rel_dev_settlement"] is not None
    ]

    summary = {
        "experiment": "rq2_settlement_fairness",
        "arm": args.arm,
        "gold": gold_path.name,
        "domain_id": domain_id,
        "mode": mode.value,
        "flags": flags,
        "client_flag": args.client,
        "resolved_provider": resolved_provider,
        "resolved_model": getattr(llm, "model", None),
        "n_cases": len(golds),
        "n_scored": len(used_golds),
        "n_errors": len(errors),
        # Coverage / plumbing (NOT success evidence):
        "zopa_found_rate": round(zopa_found_rate, 4),
        "grounding_mix": grounding_mix,
        "leakage_ok_rate": round(sum(1 for r in rows if r["leakage_ok"]) / len(rows), 4),
        "total_dup_chunks": sum(r["dup_chunk_count"] for r in rows),
        # Alignment / success:
        "actual_within_zopa_rate": round(actual_within_zopa_rate, 4),
        "mean_zopa_width_gbp": round(statistics.mean(widths), 2) if widths else None,
        "over_under_mix": over_under_mix,
        "settlement_rel_dev_median": (
            round(statistics.median(settlement_rel_devs), 4) if settlement_rel_devs else None
        ),
        "model_prediction": _score_block(used_golds, model_preds),
        "mediator_settlement_zopa_center": _score_block(used_golds, zopa_preds),
        "baseline_loo_median_award": _score_block(used_golds, baseline_preds),
        "baseline_temporal_loo_median": (
            _score_block(used_golds, temporal_preds) if has_temporal_baseline else None
        ),
        "settlement_by_grounding": {
            "comparator": _subset("comparator"),
            "free_estimate": _subset("free_estimate"),
        },
        "paired_bootstrap_settlement_minus_baseline_ae": _paired_bootstrap(deltas),
        "temporal_filters_active": bool(args.temporal_filters and any_temporal),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else _REPO_ROOT / "data" / "eval_artifacts" / "runs" / f"rq2_{args.arm}"
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
    p.add_argument("--mode", default="llm_only", help="llm_only | rag_only | hybrid | kg_only")
    p.add_argument("--arm", default="rq2", help="Arm label for provenance + output dir.")
    p.add_argument("--rag-index-root", default=None, help="Index root (default: ./indices).")
    p.add_argument(
        "--temporal-filters",
        action="store_true",
        default=True,
        help="Apply temporal leakage filter when ≥90%% of chunks carry dates.",
    )
    p.add_argument("--no-temporal-filters", dest="temporal_filters", action="store_false")
    p.add_argument("--limit", type=int, default=None, help="Cap cases (smoke test).")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--verbose", action="store_true", help="Print full tracebacks on per-case errors.")
    args = p.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(_cli())
