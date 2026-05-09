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
import inspect
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

# Allow running the script directly: prepend packages/ to sys.path.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from dotenv import load_dotenv  # noqa: E402

from eval._stub_prediction import make_stub_prediction  # noqa: E402
from eval.adapter import from_prediction_result  # noqa: E402
from eval.case_file_adapter import gold_case_to_case_file  # noqa: E402
from eval.dataset import load  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

_VALID_MODES = ("hybrid", "rag_only", "kg_only", "llm_only")
_VALID_CLIENTS = ("claude", "openai", "stub")


class LiveClientNotConfigured(RuntimeError):
    """Raised when `--engine live` is requested without an explicit client."""


def _stub_predict_fn(case_file, mode, *, gold_case=None):
    del gold_case
    return make_stub_prediction(case_file, mode)


def _source_id_variants(*values: Any) -> list[str]:
    """Return exact source-id variants used across gold rows and indexes.

    Older Ombudsman pilots used URL slugs as ``source_id`` while the full
    1,000-case scrape uses the numeric Ombudsman case number. Eval exclusion
    must cover both or it can retrieve the answer document.
    """
    variants: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        raw = str(value).strip()
        if not raw:
            return
        raw = raw.rstrip("/")
        variants.add(raw)
        compact = re.sub(r"\s+", "", raw)
        if compact:
            variants.add(compact)

        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                add(path_parts[-1])
            return

        if raw.startswith("housing-ombudsman-"):
            add(raw.removeprefix("housing-ombudsman-"))

        tail_digits = re.search(r"(\d{6,})$", compact)
        if tail_digits:
            variants.add(tail_digits.group(1))

    for value in values:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
        else:
            add(value)
    return sorted(variants)


def _enum_or_none(enum_cls, value: Any):
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    if not value:
        return None
    return enum_cls(str(value))


def _build_eval_retrieval_filter(
    gold_case: Any,
    *,
    include_temporal: bool,
):
    """Build the eval-only filter envelope for one gold row."""
    from domain_core.spec import Forum, SourceKind, SourcePublisher
    from rag_engine.config import RetrievalFilterEnvelope

    excluded_source_ids = _source_id_variants(
        getattr(gold_case, "target_source_id", None),
        getattr(gold_case, "excluded_source_ids", []),
        getattr(gold_case, "case_id", None),
        getattr(gold_case, "source_url", None),
    )

    max_decision_date = None
    if include_temporal:
        candidate = getattr(gold_case, "decision_date", None)
        if isinstance(candidate, date):
            max_decision_date = candidate

    return RetrievalFilterEnvelope(
        excluded_source_ids=excluded_source_ids,
        max_decision_date=max_decision_date,
        forum=_enum_or_none(Forum, getattr(gold_case, "forum", None)),
        source_kind=_enum_or_none(SourceKind, getattr(gold_case, "source_kind", None)),
        source_publisher=_enum_or_none(
            SourcePublisher, getattr(gold_case, "source_publisher", None)
        ),
        matter_type=getattr(gold_case, "matter_type", None),
        eval_only=True,
    )


def _merge_filter_envelopes(base, extra):
    if extra is None:
        return base
    from rag_engine.config import RetrievalFilterEnvelope

    data = base.model_dump()
    data["excluded_source_ids"] = sorted(
        set(data.get("excluded_source_ids") or [])
        | set(extra.excluded_source_ids or [])
    )
    data["legacy_where"] = {
        **(data.get("legacy_where") or {}),
        **(extra.legacy_where or {}),
    }
    data["cross_domain_allowed"] = bool(
        data.get("cross_domain_allowed") or extra.cross_domain_allowed
    )
    data["eval_only"] = bool(data.get("eval_only") or extra.eval_only)

    for key in (
        "max_decision_date",
        "as_of_date",
        "forum",
        "source_kind",
        "source_publisher",
        "matter_type",
    ):
        value = getattr(extra, key)
        if value is None:
            continue
        current = data.get(key)
        if current is not None and current != value:
            raise ValueError(
                f"Conflicting retrieval filter for {key}: {current!r} vs {value!r}"
            )
        data[key] = value
    return RetrievalFilterEnvelope(**data)


class _EvalFilteredRAGPipeline:
    """Inject eval leakage filters into an existing RAG pipeline."""

    def __init__(self, base: Any, filters: Any, requesting_namespace: Any = None):
        self._base = base
        self._filters = filters
        self._requesting_namespace = requesting_namespace

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    async def retrieve(self, *args, **kwargs):
        kwargs["filters"] = _merge_filter_envelopes(
            self._filters, kwargs.get("filters")
        )
        if kwargs.get("requesting_namespace") is None:
            kwargs["requesting_namespace"] = self._requesting_namespace
        return await self._base.retrieve(*args, **kwargs)


def _namespace_index_paths(root: Path, namespace: Any) -> tuple[Path, Path]:
    """Resolve an optional --rag-index-root.

    Accepts either:
      * ``indices`` / ``data/indices``; or
      * a concrete ``.../{namespace_id}/{corpus_version}`` directory.
    """
    root = Path(root)
    if (root / "bm25.pkl").exists() or (root / "chroma").exists():
        return root / "bm25.pkl", root / "chroma"
    cv = namespace.corpus_version or "unversioned"
    version_dir = root / namespace.namespace_id / cv
    return version_dir / "bm25.pkl", version_dir / "chroma"


def _rag_config_for_namespace(namespace: Any, rag_index_root: Optional[Path]):
    from rag_engine.config import RAGConfig

    base_cfg = RAGConfig.from_env()
    cfg = RAGConfig.from_namespace(namespace, base=base_cfg, project_root=_REPO_ROOT)
    if rag_index_root is not None:
        bm25_path, chroma_dir = _namespace_index_paths(rag_index_root, namespace)
        cfg = cfg.model_copy(
            update={
                "bm25_index_path": bm25_path,
                "chroma_persist_dir": chroma_dir,
            }
        )
    return cfg


def _ensure_rag_index_exists(cfg: Any, namespace: Any) -> None:
    missing = []
    if not cfg.bm25_index_path.exists():
        missing.append(str(cfg.bm25_index_path))
    if not cfg.chroma_persist_dir.exists():
        missing.append(str(cfg.chroma_persist_dir))
    if missing:
        raise FileNotFoundError(
            "RAG index missing for namespace "
            f"{namespace.namespace_id!r}. Missing: {', '.join(missing)}. "
            "Run the Ombudsman ingest first or pass --rag-index-root "
            "to the directory containing {namespace_id}/{corpus_version}/."
        )


def _select_namespace(domain_id: str, namespace_id: Optional[str]):
    from domain_core.registry import get_domain_spec

    spec = get_domain_spec(domain_id)
    if not spec.retrieval_namespaces:
        raise ValueError(f"Domain {domain_id!r} has no retrieval namespace")
    if namespace_id:
        for namespace in spec.retrieval_namespaces:
            if namespace.namespace_id == namespace_id:
                return namespace
        raise ValueError(
            f"Domain {domain_id!r} does not declare namespace {namespace_id!r}; "
            f"available={[ns.namespace_id for ns in spec.retrieval_namespaces]}"
        )
    if len(spec.retrieval_namespaces) > 1:
        raise ValueError(
            f"Domain {domain_id!r} declares multiple namespaces; gold row must "
            "set retrieval_namespace_id"
        )
    return spec.retrieval_namespaces[0]


def _decision_date_coverage(rag_pipeline: Any) -> float:
    chunks = []
    try:
        chunks = rag_pipeline.bm25_index.get_all_chunks()
    except Exception:
        return 0.0
    if not chunks:
        return 0.0
    with_dates = 0
    for chunk in chunks:
        metadata = getattr(chunk, "source_metadata", None)
        if metadata is not None and getattr(metadata, "decision_date", None):
            with_dates += 1
            continue
        try:
            if chunk.to_chroma_metadata().get("decision_date"):
                with_dates += 1
        except Exception:
            continue
    return with_dates / len(chunks)


def _predict_fn_accepts_gold_case(predict_fn: Callable) -> bool:
    try:
        signature = inspect.signature(predict_fn)
    except (TypeError, ValueError):
        return False
    return (
        "gold_case" in signature.parameters
        or any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )
    )


def _call_predict_fn(
    predict_fn: Callable,
    case_file: Any,
    mode: Any,
    *,
    gold_case: Any,
    accepts_gold_case: bool,
):
    if accepts_gold_case:
        return predict_fn(case_file, mode, gold_case=gold_case)
    return predict_fn(case_file, mode)


def _build_eval_knowledge_graph(
    case_file: Any,
    domain_id: str | None,
    *,
    factor_assertion_sidecar: Optional[dict] = None,
) -> Any:
    """Build the same structured KG used by the product prediction service.

    Live eval should not call a mode "hybrid" while passing ``None`` for the
    knowledge graph. Building the graph here keeps the eval runner aligned
    with ``PredictionService`` and makes KG construction failures visible
    instead of silently degrading the ablation.

    *factor_assertion_sidecar*, when provided, is a ``case_id -> List[FactorAssertion]``
    map (output of :func:`eval.factor_assertion_sidecar.load_sidecar`). Stream C
    case-side backfill: this hydrates the KG's ``factor_assertions`` field
    so the FactorRetriever / EvidencePathValidator path actually fires
    instead of falling back to chunk-RAG with an empty pack.
    """
    from kg_builder.builders.graph_builder import GraphBuilder

    builder = GraphBuilder(validate=False, domain_id=domain_id)
    kg = builder.build(case_file)

    if factor_assertion_sidecar:
        from eval.factor_assertion_sidecar import hydrate_knowledge_graph

        kg = hydrate_knowledge_graph(
            kg,
            case_id=getattr(case_file, "case_id", "") or "",
            sidecar=factor_assertion_sidecar,
        )
    return kg


def _live_predict_fn_factory(
    client_name: str,
    *,
    rag_index_root: Optional[Path] = None,
    temporal_filters: bool = True,
    top_k: int = 10,
    factor_assertion_sidecar: Optional[dict] = None,
) -> Callable:
    """Return a callable matching ``predict_fn(case_file, mode) -> PredictionResult``
    for the chosen LLM client. ``--client stub`` returns a deterministic
    placeholder; ``claude``/``openai`` build a real client.

    The returned callable closes over the heavy imports, so the stub /
    test paths never pay the orchestrator import cost.

    *factor_assertion_sidecar*, when provided, is a ``case_id -> List[FactorAssertion]``
    map that hydrates the per-case KnowledgeGraph so the FactorRetriever's
    ``asserted_factors`` input is populated (Stream C case-side backfill).
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
    from llm_orchestrator.models.prediction_v2 import PredictionMode
    from llm_orchestrator.prompts.packs import get_prompt_pack

    # Route through the SHA-114 provider factory so every direct client
    # construction in the codebase remains accounted for by
    # ``test_guard_direct_claude_client_construction_count``.
    from llm_orchestrator.clients.factory import get_llm_client
    from llm_orchestrator.config import LLMRole

    if client_name == "claude":
        llm = get_llm_client(LLMRole.PREDICTION)
    else:  # openai
        # Force the OpenAI path. The factory returns whichever provider the
        # role config selects; for live eval we want explicit selection so
        # tests are reproducible. Override via env var if the default role
        # is currently configured for Anthropic.
        from llm_orchestrator.clients.openai_client import OpenAIClient

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise LiveClientNotConfigured(
                "--engine live --client openai requires OPENAI_API_KEY"
            )
        llm = OpenAIClient(
            api_key=api_key,
            model=os.getenv("LLM_PREDICTION_PRIMARY_MODEL", "gpt-5.5"),
            fallback_model=os.getenv("LLM_PREDICTION_FALLBACK_MODEL", "gpt-5.4"),
            reasoning_effort=os.getenv("LLM_PREDICTION_REASONING_EFFORT", "high"),
            text_verbosity=os.getenv("LLM_PREDICTION_TEXT_VERBOSITY", "medium"),
            max_retries=3,
        )

    pipeline_cache: dict[tuple[str, str, Optional[str]], tuple[Any, Any, bool]] = {}
    rag_index_root = rag_index_root or (
        Path(os.environ["RAG_INDEX_ROOT"]) if os.environ.get("RAG_INDEX_ROOT") else None
    )

    def _pipeline_for(gold_case: Any):
        domain_id = str(getattr(gold_case, "domain_id", "") or "")
        namespace_id = getattr(gold_case, "retrieval_namespace_id", None)
        if not domain_id:
            raise ValueError("Live eval requires gold rows with domain_id")
        namespace = _select_namespace(domain_id, namespace_id)
        cache_key = (
            domain_id,
            namespace.namespace_id,
            str(rag_index_root) if rag_index_root is not None else None,
        )
        cached = pipeline_cache.get(cache_key)
        if cached is not None:
            return cached

        from rag_engine.pipeline import RAGPipeline

        cfg = _rag_config_for_namespace(namespace, rag_index_root)
        _ensure_rag_index_exists(cfg, namespace)
        rag = RAGPipeline(config=cfg, namespace=namespace)
        has_temporal_dates = _decision_date_coverage(rag) >= 0.90
        pipeline_cache[cache_key] = (rag, namespace, has_temporal_dates)
        return pipeline_cache[cache_key]

    def _live_call(case_file, mode, *, gold_case=None):
        if gold_case is None:
            raise ValueError("Live eval prediction requires gold_case context")
        # Resolve a prompt pack from the case_file's domain metadata when
        # available; fall back to None (legacy IRAC prompts).
        domain_id = (
            getattr(gold_case, "domain_id", None)
            or (case_file.metadata or {}).get("domain_id")
        )
        prompt_pack = None
        if domain_id:
            try:
                prompt_pack = get_prompt_pack(domain_id)
            except KeyError:
                prompt_pack = None
        rag_pipeline = None
        if mode in (PredictionMode.HYBRID, PredictionMode.RAG_ONLY):
            rag, namespace, has_temporal_dates = _pipeline_for(gold_case)
            filters = _build_eval_retrieval_filter(
                gold_case,
                include_temporal=bool(temporal_filters and has_temporal_dates),
            )
            rag_pipeline = _EvalFilteredRAGPipeline(
                rag, filters, requesting_namespace=namespace
            )
        knowledge_graph = None
        if mode in (PredictionMode.HYBRID, PredictionMode.KG_ONLY):
            knowledge_graph = _build_eval_knowledge_graph(
                case_file,
                domain_id,
                factor_assertion_sidecar=factor_assertion_sidecar,
            )
        engine = PredictionEngineV2(
            llm_client=llm, rag_pipeline=rag_pipeline, prompt_pack=prompt_pack
        )
        # Run the async predict in an event loop.
        return asyncio.run(
            engine.predict(
                case_file,
                knowledge_graph=knowledge_graph,
                top_k=top_k,
                mode=mode,
                matter_type=getattr(gold_case, "matter_type", None),
            )
        )

    return _live_call


def _resolve_predict_fn(
    engine: str,
    client: Optional[str],
    *,
    rag_index_root: Optional[Path] = None,
    temporal_filters: bool = True,
    top_k: int = 10,
    factor_assertion_sidecar: Optional[dict] = None,
) -> Callable:
    if engine == "stub":
        return _stub_predict_fn
    if engine == "live":
        if client is None:
            raise LiveClientNotConfigured(
                "--engine live requires an explicit --client {claude,openai,stub}; "
                "refusing to silently substitute the stub. The Phase 5b stub "
                "exists for CI; for thesis numbers wire a real client."
            )
        return _live_predict_fn_factory(
            client,
            rag_index_root=rag_index_root,
            temporal_filters=temporal_filters,
            top_k=top_k,
            factor_assertion_sidecar=factor_assertion_sidecar,
        )
    raise ValueError(f"Unknown --engine {engine!r}; expected 'stub' or 'live'")


def _serialise_prediction(pred, raw_result: Any = None) -> dict:
    """Convert eval.metrics.Prediction → JSON-friendly dict (matches the
    shape eval.run._load_predictions consumes)."""
    out = {
        "case_id": pred.case_id,
        "overall_winner": pred.overall_winner.value,
        "overall_win_probability": float(pred.overall_win_probability),
        "total_predicted_gbp": _serialise_amount(pred.total_predicted_gbp),
        "predicted_determination": (
            pred.predicted_determination.value
            if getattr(pred, "predicted_determination", None) is not None
            else None
        ),
        "per_issue": [
            {
                "issue": ip.issue,
                "predicted_winner": ip.predicted_winner.value,
                "win_probability": float(ip.win_probability),
                "predicted_amount_gbp": _serialise_amount(
                    ip.predicted_amount_gbp
                ),
                "amount_construct": getattr(ip, "amount_construct", None),
            }
            for ip in pred.per_issue
        ],
    }
    if raw_result is not None:
        raw_outcome = getattr(getattr(raw_result, "overall_outcome", None), "value", None)
        out["raw_overall_outcome"] = raw_outcome
        out["raw_overall_confidence"] = float(
            getattr(raw_result, "overall_confidence", 0.0) or 0.0
        )
        out["abstained"] = raw_outcome == "uncertain"
        raw_issues = list(getattr(raw_result, "issue_predictions", []) or [])
        if len(out["per_issue"]) != len(raw_issues):
            raise ValueError(
                "serialisation issue-count mismatch: "
                f"adapted={len(out['per_issue'])} raw={len(raw_issues)}"
            )
        for row, raw_issue in zip(out["per_issue"], raw_issues):
            issue_outcome = getattr(getattr(raw_issue, "outcome", None), "value", None)
            row["raw_outcome"] = issue_outcome
            row["abstained"] = issue_outcome == "uncertain"
            row["amount_band"] = getattr(raw_issue, "amount_band", None)
            row["supporting_cases"] = [
                _serialise_model(citation)
                for citation in getattr(raw_issue, "supporting_cases", []) or []
            ]
        out["verification"] = _serialise_model(
            getattr(raw_result, "citation_verification", None)
        )
        out["retrieval"] = _json_ready(
            getattr(raw_result, "retrieval_evidence", {}) or {}
        )
        out["retrieved_cases"] = list(getattr(raw_result, "retrieved_cases", []) or [])
        out["total_cases_analyzed"] = int(
            getattr(raw_result, "total_cases_analyzed", 0) or 0
        )
        out["rag_confidence"] = float(getattr(raw_result, "rag_confidence", 0.0) or 0.0)
        out["retrieval_quality"] = getattr(raw_result, "retrieval_quality", None)
        # Stream C: surface pipeline_metadata so artifacts carry the full
        # §17.6 / Cross-PR Contract C5 schema (kg_used_for_prediction,
        # graph_quality_score, kg_fallback_mode, kg_gate_failure_reasons,
        # core_schema, domain_pack, factor_catalog_version,
        # evidence_path_results). Without this, downstream metrics like
        # gate_pass_rate / two_slice_report run against empty metadata.
        pipeline_meta = getattr(raw_result, "pipeline_metadata", None)
        out["pipeline_metadata"] = (
            _serialise_model(pipeline_meta) if pipeline_meta is not None else {}
        )
    return out


def _serialise_amount(amount) -> str | None:
    if amount is None:
        return None
    value = Decimal(str(amount))
    if value == value.to_integral_value():
        return f"{value:.1f}"
    return format(value, "f")


def _serialise_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return _json_ready(value)


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    return str(value)


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


def _resolve_run_context(
    g,
    *,
    engine: str,
    client: Optional[str],
    retrieval_top_k: int = 10,
) -> Dict[str, Any]:
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
        "retrieval_budget": {"top_k": retrieval_top_k},
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
            get_ontology,
            hash_ontology_spec,
        )

        ont = get_ontology(g.domain_id)
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
    retrieval_top_k: int = 10,
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
    accepts_gold_case = _predict_fn_accepts_gold_case(predict_fn)

    for mode_str in modes:
        mode_enum = _resolve_mode_enum(mode_str)
        out_path = out_dir / f"{mode_str}.jsonl"
        with out_path.open("w") as f:
            for g in gold_cases:
                recon = gold_case_to_case_file(g)
                for ct in recon.unmapped_claim_types:
                    unmapped_total[ct] += 1
                pred_result = _call_predict_fn(
                    predict_fn,
                    recon.case_file,
                    mode_enum,
                    gold_case=g,
                    accepts_gold_case=accepts_gold_case,
                )
                eval_pred = from_prediction_result(pred_result)
                _apply_gold_issue_label_alignment(
                    eval_pred, recon.gold_issue_labels_by_claim_type
                )
                serialised = _serialise_prediction(eval_pred, pred_result)
                f.write(json.dumps(serialised) + "\n")

                # Per-case artifact (live runner only — keep stub light).
                if engine == "live":
                    ctx = _resolve_run_context(
                        g,
                        engine=engine,
                        client=client,
                        retrieval_top_k=retrieval_top_k,
                    )
                    payload = {
                        "run_id": run_id,
                        "case_id": g.case_id,
                        "mode": mode_str,
                        "context": ctx,
                        "result_hash": _compute_result_hash(
                            {**ctx, "case_id": g.case_id, "mode": mode_str}
                        ),
                        "prediction": serialised,
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
        "--rag-index-root",
        type=Path,
        default=None,
        help=(
            "Optional root containing namespace/corpus-version RAG indexes "
            "(for example: indices or data/indices). Live RAG modes use "
            "domain defaults when omitted. Can also be set with RAG_INDEX_ROOT."
        ),
    )
    parser.add_argument(
        "--no-temporal-filter",
        action="store_true",
        help=(
            "Disable decision-date max filtering in live RAG modes. Target-source "
            "exclusion and domain metadata filters still apply."
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
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help=(
            "Retrieval budget passed into live RAG modes. Default keeps the "
            "legacy runner behavior at 10."
        ),
    )
    parser.add_argument(
        "--factor-assertion-sidecar",
        type=Path,
        default=None,
        help=(
            "Optional path to a Stream-C factor-assertion sidecar JSON "
            "(see eval.factor_assertion_sidecar). When omitted, the runner "
            "auto-resolves the canonical path "
            "data/eval_artifacts/factor_assertions/<gold-stem>.factor_assertions.json. "
            "If neither path exists, hybrid/kg_only modes run with empty "
            "asserted_factors (legacy fallback)."
        ),
    )
    args = parser.parse_args(argv)

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    invalid = [m for m in modes if m not in _VALID_MODES]
    if invalid:
        print(f"Unknown mode(s): {invalid}; valid: {_VALID_MODES}", file=sys.stderr)
        return 2

    # Stream C: load the case-side factor-assertion sidecar (if present).
    # Default location is canonical; explicit --factor-assertion-sidecar
    # overrides. A missing sidecar is NOT an error — eval still runs with
    # the legacy empty-pack fallback so old eval scripts keep working.
    from eval.factor_assertion_sidecar import (  # noqa: PLC0415
        load_sidecar,
        resolve_sidecar_for_gold_path,
    )

    sidecar_path = args.factor_assertion_sidecar
    if sidecar_path is None:
        sidecar_path = resolve_sidecar_for_gold_path(args.gold.resolve())
    factor_assertion_sidecar: Optional[dict] = None
    if sidecar_path.exists():
        factor_assertion_sidecar = load_sidecar(sidecar_path)
        n_cases = len(factor_assertion_sidecar)
        n_assertions = sum(len(v) for v in factor_assertion_sidecar.values())
        print(
            f"Loaded factor-assertion sidecar from {sidecar_path}: "
            f"{n_cases} cases, {n_assertions} assertions"
        )

    try:
        predict_fn = _resolve_predict_fn(
            args.engine,
            args.client,
            rag_index_root=args.rag_index_root,
            temporal_filters=not args.no_temporal_filter,
            top_k=args.top_k,
            factor_assertion_sidecar=factor_assertion_sidecar,
        )
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
        retrieval_top_k=args.top_k,
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
