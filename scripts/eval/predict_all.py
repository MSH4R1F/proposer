#!/usr/bin/env python3
"""Phase 5b/7 live runner — emit per-mode prediction JSONLs from a gold corpus.

Loops `(gold_case, mode)` pairs through:
    eval.case_file_adapter.gold_case_to_case_file
    → predict_fn(case_file, mode)
    → eval.adapter.from_prediction_result
    → JSONL row

In the default `--engine stub` mode, `predict_fn = make_stub_prediction`,
no LLM is touched, and CI exercises the full chain. The output JSONLs
feed `python -m eval.ablate` directly.

In `--engine live` mode, the runner additionally requires `--client
{claude,openai,stub}`. The `live --client stub` combination is a
deterministic placeholder used by tests; without `--client`, `--engine
live` refuses to run rather than silently substituting the stub. See
SHA-20 Phase 7 for the leakage controls and result-hash contract.

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
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# Allow running the script directly: prepend packages/ to sys.path.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval._stub_prediction import make_stub_prediction  # noqa: E402
from eval.adapter import from_prediction_result  # noqa: E402
from eval.case_file_adapter import gold_case_to_case_file  # noqa: E402
from eval.dataset import load  # noqa: E402

_VALID_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")
_VALID_CLIENTS = ("claude", "openai", "stub")


class LiveClientNotConfigured(RuntimeError):
    """Raised when `--engine live` is requested without an explicit client."""


def _stub_predict_fn(case_file, mode):
    return make_stub_prediction(case_file, mode)


def _live_predict_fn_factory(client_name: str) -> Callable:
    """Return a callable matching ``predict_fn(case_file, mode) -> PredictionResult``
    for the chosen LLM client. ``--client stub`` returns a deterministic
    placeholder; ``claude``/``openai`` build a real client.

    The returned callable closes over the heavy imports, so the stub /
    test paths never pay the orchestrator import cost.
    """
    if client_name == "stub":
        return _stub_predict_fn
    if client_name not in {"claude", "openai"}:
        raise LiveClientNotConfigured(
            f"--engine live requires --client {{claude,openai,stub}}; got {client_name!r}"
        )

    # Real LLM clients live in llm_orchestrator.clients. Build them once.
    import asyncio

    from llm_orchestrator import PredictionEngineV2
    from llm_orchestrator.prompts.packs import get_prompt_pack

    if client_name == "claude":
        from llm_orchestrator.clients.claude import ClaudeClient

        llm = ClaudeClient()
    else:  # openai
        from llm_orchestrator.clients.openai import OpenAIClient

        llm = OpenAIClient()

    def _live_call(case_file, mode):
        # Resolve a prompt pack from the case_file's domain metadata when
        # available; fall back to None (legacy IRAC prompts).
        domain_id = (case_file.metadata or {}).get("domain_id")
        prompt_pack = None
        if domain_id:
            try:
                prompt_pack = get_prompt_pack(domain_id)
            except KeyError:
                prompt_pack = None
        engine = PredictionEngineV2(
            llm_client=llm, rag_pipeline=None, prompt_pack=prompt_pack
        )
        # Run the async predict in an event loop.
        return asyncio.run(engine.predict(case_file, mode=mode))

    return _live_call


def _resolve_predict_fn(engine: str, client: Optional[str]) -> Callable:
    if engine == "stub":
        return _stub_predict_fn
    if engine == "live":
        if client is None:
            raise LiveClientNotConfigured(
                "--engine live requires an explicit --client {claude,openai,stub}; "
                "refusing to silently substitute the stub. The Phase 5b stub "
                "exists for CI; for thesis numbers wire a real client."
            )
        return _live_predict_fn_factory(client)
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


def _compute_result_hash(parts: Dict[str, Any]) -> str:
    """Stable SHA-256 of canonical JSON of the contributing parts.

    See SHA-20 Phase 7 acceptance: the result hash MUST cover
    ``corpus_version``, ``namespace_id``, ``prompt_pack_id``,
    ``ontology_id``, provider/model role identifier, verifier hash, and
    retrieval budget. ``gate_evaluation_seed`` is included when set.
    """
    canonical = json.dumps(
        parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_run_context(g, *, engine: str, client: Optional[str]) -> Dict[str, Any]:
    """Best-effort lookup of the per-case context that feeds the result hash.

    Returns a dict; missing components fall through as ``None`` so the
    hash is still well-defined for legacy gold rows.
    """
    ctx: Dict[str, Any] = {
        "corpus_version": g.corpus_version,
        "namespace_id": g.retrieval_namespace_id,
        "prompt_pack_id": None,
        "prompt_pack_hash": None,
        "ontology_id": None,
        "ontology_hash": None,
        "domain_spec_hash": None,
        "verifier_hash": None,
        "retrieval_budget": {"top_k": 10},
        "engine": engine,
        "client": client,
        "gate_evaluation_seed": None,
    }
    if not g.domain_id:
        return ctx
    try:
        from domain_core.hashing import hash_domain_spec
        from domain_core.registry import get_domain_spec

        spec = get_domain_spec(g.domain_id)
        ctx["domain_spec_hash"] = hash_domain_spec(spec)
    except Exception:
        pass
    try:
        from llm_orchestrator.prompts.packs import (
            get_prompt_pack,
            hash_prompt_pack,
        )

        pack = get_prompt_pack(g.domain_id)
        ctx["prompt_pack_id"] = getattr(pack, "id", None)
        ctx["prompt_pack_hash"] = hash_prompt_pack(pack)
    except Exception:
        pass
    try:
        from kg_builder.ontology.registry import (
            get_ontology_spec,
            hash_ontology_spec,
        )

        ont = get_ontology_spec(g.domain_id)
        ctx["ontology_id"] = getattr(ont, "id", None)
        ctx["ontology_hash"] = hash_ontology_spec(ont)
    except Exception:
        pass
    # Verifier hash: defer to a stable identifier of the citation verifier
    # version. The verifier package exposes ``__version__``-style hooks
    # in Phase 6; for now we use the module file hash as a placeholder.
    try:
        import llm_orchestrator.pipeline.citation_verifier as cv_mod

        src = Path(cv_mod.__file__).read_bytes()
        ctx["verifier_hash"] = hashlib.sha256(src).hexdigest()
    except Exception:
        pass
    return ctx


def _run(
    gold_cases: list,
    modes: List[str],
    *,
    predict_fn: Callable,
    out_dir: Path,
    engine: str,
    client: Optional[str],
    run_id: Optional[str] = None,
) -> Dict[str, int]:
    """Run the (gold × mode) loop. Returns counters used by the summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    unmapped_total: Counter = Counter()
    cases_done = 0
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_artifact_dir = (
        Path("data/eval_artifacts/runs") / run_id
    )
    run_artifact_dir.mkdir(parents=True, exist_ok=True)

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

                # Per-case artifact (live runner only — keep stub light).
                if engine == "live":
                    ctx = _resolve_run_context(g, engine=engine, client=client)
                    payload = {
                        "run_id": run_id,
                        "case_id": g.case_id,
                        "mode": mode_str,
                        "context": ctx,
                        "result_hash": _compute_result_hash(
                            {**ctx, "case_id": g.case_id, "mode": mode_str}
                        ),
                        "prediction": _serialise_prediction(eval_pred),
                    }
                    artifact_path = run_artifact_dir / f"{g.case_id}__{mode_str}.json"
                    artifact_path.write_text(json.dumps(payload, indent=2))
        cases_done = len(gold_cases)

    return {
        "cases_per_mode": cases_done,
        "modes": len(modes),
        "unmapped_claim_types": dict(unmapped_total),
        "run_id": run_id,
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
        help="stub: deterministic stand-in (CI). live: real prediction engine.",
    )
    parser.add_argument(
        "--client",
        choices=_VALID_CLIENTS,
        default=None,
        help=(
            "LLM client to use when --engine live. 'stub' returns a "
            "deterministic placeholder (tests only). Without this flag, "
            "--engine live REFUSES to run rather than silently using stub."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Optional run id used when writing per-case artifacts under "
            "data/eval_artifacts/runs/{run_id}/. Defaults to current UTC."
        ),
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

    try:
        predict_fn = _resolve_predict_fn(args.engine, args.client)
    except LiveClientNotConfigured as e:
        print(str(e), file=sys.stderr)
        return 2

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
        engine=args.engine,
        client=args.client,
        run_id=args.run_id,
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
