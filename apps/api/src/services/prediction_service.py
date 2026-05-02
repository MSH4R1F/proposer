"""
Prediction service.

Orchestrates prediction generation with RAG integration.
Supports two-party dispute merging: when both tenant and landlord
have submitted for the same dispute, their CaseFiles are merged
into one and a single shared prediction is generated.

Phase 7.1: All persistence is routed through UnitOfWork (Postgres).
JSONGraphStore is no longer used.  The legacy singleton getter is kept
for rollback compatibility.
"""

from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_orchestrator.clients.factory import get_llm_client
from llm_orchestrator.clients.types import LLMRole
from llm_orchestrator.models.prediction import PredictionResult
from llm_orchestrator.models.prediction_v2 import PredictionMode, RetrievalStrategy
from llm_orchestrator.models.case_file import CaseFile, merge_case_files

from apps.api.src.config import config
from apps.api.src.db.uow import UnitOfWork
from apps.api.src.domain_runtime import (
    DomainRuntimeContext,
    resolve_domain_runtime,
)

logger = structlog.get_logger()


# SHA-20 Phase 8 fallback sentinels — used ONLY when ``runtime`` is ``None``
# (no domain context resolved at all, i.e. legacy code path that hasn't
# been threaded through ``DomainRuntimeContext`` yet). Once a runtime is
# present the real prompt-pack / ontology / namespace / corpus-version
# values are looked up from the spec + registries.
_LEGACY_PROMPT_PACK_HASH = "legacy_deposit_v1"
_LEGACY_ONTOLOGY_HASH = "legacy_deposit_v1"
_LEGACY_CORPUS_VERSION = "legacy"
_LEGACY_NAMESPACE_ID = "tribunal_cases"


def _resolve_domain_artifact_hashes(
    runtime: Optional[DomainRuntimeContext],
) -> Dict[str, str]:
    """Look up the real prompt-pack / ontology / corpus / namespace values
    for the resolved domain.

    Returns a dict with keys ``prompt_pack_hash``, ``ontology_hash``,
    ``corpus_version``, ``namespace_id``. Falls back to legacy sentinels
    only when ``runtime`` is ``None`` or a registry lookup fails (which is
    treated as a programming error: we log and continue rather than
    crashing the request).
    """
    if runtime is None:
        return {
            "prompt_pack_hash": _LEGACY_PROMPT_PACK_HASH,
            "ontology_hash": _LEGACY_ONTOLOGY_HASH,
            "corpus_version": _LEGACY_CORPUS_VERSION,
            "namespace_id": _LEGACY_NAMESPACE_ID,
        }

    domain_id = runtime.domain_id

    # --- prompt pack hash ---
    try:
        from llm_orchestrator.prompts.packs import (
            get_prompt_pack,
            hash_prompt_pack,
        )

        pack = get_prompt_pack(domain_id)
        prompt_pack_hash = hash_prompt_pack(pack)
    except Exception as exc:  # pragma: no cover - logged + falls back
        logger.warning(
            "prompt_pack_lookup_failed_using_sentinel",
            domain_id=domain_id,
            error=str(exc),
        )
        prompt_pack_hash = _LEGACY_PROMPT_PACK_HASH

    # --- ontology hash ---
    try:
        from kg_builder.ontology.registry import (
            get_ontology,
            hash_ontology_spec,
        )

        ontology = get_ontology(domain_id)
        ontology_hash = hash_ontology_spec(ontology)
    except Exception as exc:  # pragma: no cover - logged + falls back
        logger.warning(
            "ontology_lookup_failed_using_sentinel",
            domain_id=domain_id,
            error=str(exc),
        )
        ontology_hash = _LEGACY_ONTOLOGY_HASH

    # --- namespace id + corpus version ---
    namespaces = list(runtime.domain_spec.retrieval_namespaces)
    chosen_ns = None
    if namespaces:
        # Prefer one tagged as ``default`` in metadata_filters; otherwise
        # fall back to the first declared namespace.
        for ns in namespaces:
            tag = ns.metadata_filters.get("default") if ns.metadata_filters else None
            if tag:
                chosen_ns = ns
                break
        if chosen_ns is None:
            chosen_ns = namespaces[0]

    namespace_id = chosen_ns.namespace_id if chosen_ns else _LEGACY_NAMESPACE_ID
    corpus_version = (
        chosen_ns.corpus_version
        if chosen_ns and chosen_ns.corpus_version
        else _LEGACY_CORPUS_VERSION
    )

    return {
        "prompt_pack_hash": prompt_pack_hash,
        "ontology_hash": ontology_hash,
        "corpus_version": corpus_version,
        "namespace_id": namespace_id,
    }


def _build_domain_cache_segment(
    runtime: Optional[DomainRuntimeContext],
    *,
    mode: PredictionMode,
    cross_domain: bool,
) -> str:
    """Produce the SHA-20 cache-key segment that captures domain state.

    The segment includes everything that, if changed, must invalidate any
    cached prediction:

    - ``domain_id`` and ``domain_spec_hash`` (spec changes)
    - ``prompt_pack_hash`` — looked up via ``get_prompt_pack`` (Phase 6/8)
    - ``ontology_hash`` — looked up via ``get_ontology`` (Phase 5/8)
    - ``corpus_version`` — from ``RetrievalNamespace.corpus_version``
    - retrieval ``namespace_id`` — from ``DomainSpec.retrieval_namespaces``
    - prediction ``mode``
    - ``cross_domain`` flag

    Phase 8 swapped the Phase 3 sentinels for real artifact lookups. The
    format is intentionally a single delimited string so callers can
    prepend it to existing ``session:version`` cache keys without
    changing schema.
    """
    if runtime is None:
        # No domain context — fall back to the deposit baseline + sentinels.
        domain_id = "housing.deposit.v1"
        spec_hash = "legacy_deposit_v1"
    else:
        domain_id = runtime.domain_id
        spec_hash = runtime.domain_spec_hash

    hashes = _resolve_domain_artifact_hashes(runtime)
    return (
        f"d={domain_id}"
        f"|sh={spec_hash}"
        f"|pp={hashes['prompt_pack_hash']}"
        f"|on={hashes['ontology_hash']}"
        f"|cv={hashes['corpus_version']}"
        f"|ns={hashes['namespace_id']}"
        f"|m={mode.value}"
        f"|x={'1' if cross_domain else '0'}"
    )

# Legacy singleton kept for rollback compatibility.
_prediction_service: Optional["PredictionService"] = None


class PredictionCacheConflictError(RuntimeError):
    """Raised when intake sessions changed while a prediction was being generated."""


def _build_prediction_engine() -> Any:
    """
    Construct the heavy prediction engine (LLM client + optional RAG pipeline).

    This is pulled into a module-level helper so that dependencies.py can
    cache it at process level via lru_cache without importing the engine at
    module-import time.
    """
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    llm_client = get_llm_client(LLMRole.PREDICTION)
    engine = PredictionEngineV2(llm_client=llm_client, rag_pipeline=None)

    # Try to attach RAG pipeline.
    try:
        from rag_engine import RAGPipeline, RAGConfig

        rag_config = RAGConfig.from_env()
        rag_pipeline = RAGPipeline(config=rag_config)
        engine.set_rag_pipeline(rag_pipeline)
        logger.info("rag_pipeline_loaded")
    except Exception as e:
        logger.warning("rag_pipeline_not_loaded", error=str(e))

    return engine


class PredictionService:
    """
    Service for generating outcome predictions.

    Integrates RAG retrieval, knowledge graph, and LLM synthesis.
    Supports two-party disputes: merges both parties' CaseFiles and
    generates a single shared prediction cached by dispute_id.

    All persistence goes through UnitOfWork (Postgres).
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        engine: Optional[Any] = None,        # PredictionEngineV2 — heavy LLM piece
        graph_builder: Optional[Any] = None,  # GraphBuilder — pure Python
        rag_pipeline: Optional[Any] = None,   # heavy RAG (unused if engine provided)
        intake_service: Optional[Any] = None,  # kept for API compat, not used internally
        dispute_service: Optional[Any] = None, # kept for API compat, not used internally
    ) -> None:
        self._sm = sessionmaker

        # Lazy-init heavy pieces only when not injected (allows test mocking).
        self._engine = engine
        self._graph_builder = graph_builder

        # intake_service / dispute_service are no longer called internally —
        # all IO goes through repos — but we accept them so callers that
        # pass keyword arguments don't break.
        _ = intake_service
        _ = dispute_service

        logger.info("prediction_service_initialized")
        self._configure_proposition_retriever()

    # ------------------------------------------------------------------
    # Lazy property accessors for heavy components
    # ------------------------------------------------------------------

    @property
    def prediction_engine(self) -> Any:
        """Process-cached prediction engine (constructed on first use)."""
        if self._engine is None:
            self._engine = _build_prediction_engine()
            self._configure_proposition_retriever()
        return self._engine

    def _configure_proposition_retriever(self) -> None:
        """Attach a sessionmaker-backed proposition retriever to cached engines."""
        if self._engine is None or not hasattr(self._engine, "set_proposition_retriever"):
            return
        from unittest.mock import Mock

        setter = getattr(self._engine, "set_proposition_retriever")
        if isinstance(setter, Mock):
            return
        from apps.api.src.services.proposition_graph_store import (
            PostgresPropositionGraphStore,
        )
        from llm_orchestrator.pipeline.proposition_retrieval import PropositionRetriever

        store = PostgresPropositionGraphStore(self._sm)
        setter(PropositionRetriever(store))

    @property
    def graph_builder(self) -> Any:
        """GraphBuilder (constructed on first use)."""
        if self._graph_builder is None:
            from kg_builder.builders.graph_builder import GraphBuilder
            self._graph_builder = GraphBuilder()
        return self._graph_builder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_case_ready(self, case_id: str) -> Dict[str, Any]:
        """
        Check if a case is ready for prediction.

        Only dispute issues are strictly required. Other fields improve
        prediction quality but don't block generation.
        """
        async with UnitOfWork(self._sm) as uow:
            state = await uow.sessions.get_by_case_id(case_id)

        if not state:
            return {
                "exists": False,
                "is_complete": False,
                "completeness": 0,
                "missing_info": [],
                "missing_recommended": [],
                "data_quality_tier": "insufficient",
            }

        case_file = state.case_file
        case_file.calculate_completeness()
        missing = case_file.get_missing_required_info()
        missing_recommended = case_file.get_missing_recommended_info()
        quality_tier = case_file.get_data_quality_tier()
        is_ready = case_file.has_all_required_info()

        logger.debug(
            "case_readiness_check",
            case_id=case_id,
            completeness=case_file.completeness_score,
            is_ready=is_ready,
            data_quality_tier=quality_tier,
            missing_required=missing,
            missing_recommended=missing_recommended,
        )

        return {
            "exists": True,
            "is_complete": is_ready,
            "completeness": case_file.completeness_score,
            "missing_info": missing,
            "missing_recommended": missing_recommended,
            "data_quality_tier": quality_tier,
        }

    async def generate_prediction(
        self,
        case_id: str,
        include_reasoning: bool = True,
        mode_override: Optional[PredictionMode] = None,
        retrieval_strategy_override: Optional[RetrievalStrategy] = None,
        *,
        domain_runtime: Optional[DomainRuntimeContext] = None,
    ) -> PredictionResult:
        """
        Generate a prediction for a case.

        If the case belongs to a two-party dispute (both tenant and landlord
        have submitted), their CaseFiles are merged and a single shared
        prediction is generated. Both parties will receive the same result.

        3-stage flow:
          Stage 1 (read transaction) — resolve case_file, check cache.
          Stage 2 (no transaction) — build KG + run LLM prediction engine.
          Stage 3 (write transaction) — re-check cache (row-lock), write KG +
            prediction + update disputes.cached_prediction_id atomically.
        """
        # Resolve effective mode early so the cache key segment is correct
        # even at Stage 1 (the cache key MUST change when mode changes).
        if mode_override is not None:
            effective_mode = mode_override
        else:
            try:
                effective_mode = PredictionMode(config.prediction_mode)
            except ValueError:
                effective_mode = PredictionMode.HYBRID
        cross_domain = (
            domain_runtime.cross_domain_retrieval if domain_runtime else False
        )
        domain_segment = _build_domain_cache_segment(
            domain_runtime, mode=effective_mode, cross_domain=cross_domain
        )

        # ── Stage 1: short read transaction ─────────────────────────────────
        async with UnitOfWork(self._sm) as uow:
            case_file, dispute_id, cacheable, cache_key = (
                await self._resolve_and_merge_from_repos(
                    case_id, uow, domain_segment=domain_segment
                )
            )
            if cacheable and dispute_id:
                locked = await uow.disputes.lock_for_prediction_cache(dispute_id)
                if (
                    locked
                    and locked.cached_prediction_id
                    and locked.prediction_cache_key == cache_key
                ):
                    cached = await uow.predictions.get(locked.cached_prediction_id)
                    if cached:
                        logger.info(
                            "returning_cached_dispute_prediction_stage1",
                            case_id=case_id,
                            dispute_id=dispute_id,
                            prediction_id=locked.cached_prediction_id,
                        )
                        return cached

        # ── Stage 2: external work — NO transaction ──────────────────────────
        # Effective mode was resolved before Stage 1 so the cache key segment
        # is correct; reuse it here and emit the legacy warning log if the
        # configured env value was unparseable.
        if mode_override is None:
            try:
                PredictionMode(config.prediction_mode)
            except ValueError:
                logger.warning(
                    "invalid_prediction_mode_env_falling_back_to_hybrid",
                    configured=config.prediction_mode,
                )
        default_mode = effective_mode
        if retrieval_strategy_override is not None:
            default_retrieval_strategy = retrieval_strategy_override
        else:
            configured_strategy = getattr(config, "retrieval_strategy", "chunk_rag")
            try:
                default_retrieval_strategy = RetrievalStrategy(configured_strategy)
            except ValueError:
                logger.warning(
                    "invalid_retrieval_strategy_env_falling_back_to_chunk_rag",
                    configured=configured_strategy,
                )
                default_retrieval_strategy = RetrievalStrategy.CHUNK_RAG

        # Build knowledge graph from the (already merged in Stage 1) case file.
        # No silent fallbacks: if KG construction throws, log structured event
        # and degrade explicitly to RAG_ONLY for this case. The KG itself is
        # persisted in Stage 3 via uow.knowledge_graphs (no JSON file write).
        kg = None
        mode = default_mode
        try:
            kg = self.graph_builder.build(case_file)
        except Exception as e:
            logger.error(
                "kg_build_failed_degrading_to_rag_only",
                case_id=case_id,
                dispute_id=dispute_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            mode = PredictionMode.RAG_ONLY
            kg = None

        logger.info(
            "generating_prediction",
            case_id=case_id,
            dispute_id=dispute_id,
            is_merged=dispute_id is not None,
            mode=mode.value,
            retrieval_strategy=default_retrieval_strategy.value,
            kg_nodes=len(kg.nodes) if kg else 0,
            kg_edges=len(kg.edges) if kg else 0,
        )
        predict_kwargs = {
            "case_file": case_file,
            "knowledge_graph": kg,
            "mode": mode,
        }
        if default_retrieval_strategy != RetrievalStrategy.CHUNK_RAG:
            predict_kwargs["retrieval_strategy"] = default_retrieval_strategy
        prediction = await self.prediction_engine.predict(**predict_kwargs)

        if cacheable and dispute_id:
            prediction.metadata["dispute_id"] = dispute_id
            prediction.metadata["merged"] = True
            prediction.metadata["prediction_cache_key"] = cache_key

        # SHA-20 Phase 8: stamp the domain block into prediction.metadata and
        # mirror the routing fields onto the new top-level Pydantic columns.
        # The four artifact hashes (prompt-pack / ontology / corpus /
        # namespace) are now real values resolved from registries — the
        # legacy sentinels remain only for the no-runtime fallback path.
        if domain_runtime is not None:
            spec = domain_runtime.domain_spec
            hashes = _resolve_domain_artifact_hashes(domain_runtime)
            domain_meta_block = {
                "id": str(spec.id),
                "version": spec.domain_version,
                "family": spec.family.value,
                "stage": spec.stage.value,
                "spec_hash": domain_runtime.domain_spec_hash,
                "prompt_pack_hash": hashes["prompt_pack_hash"],
                "ontology_hash": hashes["ontology_hash"],
                "corpus_version": hashes["corpus_version"],
                "namespace_id": hashes["namespace_id"],
                "prediction_mode": effective_mode.value,
                "cross_domain_retrieval": cross_domain,
                "routing_metadata": dict(domain_runtime.routing_metadata),
                "gate_artifact_id": domain_runtime.gate_artifact_id,
                "gate_artifact_hash": domain_runtime.gate_artifact_hash,
            }
            prediction.metadata["domain"] = domain_meta_block

            # Mirror onto Pydantic top-level fields so the projection layer
            # picks them up directly.
            prediction.domain_id = str(spec.id)
            prediction.domain_version = spec.domain_version
            prediction.matter_types = list(spec.matter_types)
            prediction.routing_metadata = dict(domain_runtime.routing_metadata)
            prediction.domain_spec_hash = domain_runtime.domain_spec_hash
            prediction.prompt_pack_hash = hashes["prompt_pack_hash"]
            prediction.ontology_hash = hashes["ontology_hash"]
            prediction.corpus_version = hashes["corpus_version"]

        logger.info(
            "prediction_generated_pre_write",
            case_id=case_id,
            prediction_id=prediction.prediction_id,
            dispute_id=dispute_id,
            cacheable=cacheable,
        )

        # ── Stage 3: short write transaction with row-lock re-check ──────────
        async with UnitOfWork(self._sm) as uow:
            if cacheable and dispute_id:
                locked = await uow.disputes.lock_for_prediction_cache(dispute_id)
                current_cache_key = (
                    await self._current_cache_key_for_locked_dispute(
                        locked, uow, domain_segment=domain_segment
                    )
                    if locked
                    else None
                )
                if current_cache_key != cache_key:
                    logger.warning(
                        "prediction_cache_conflict_stage3",
                        case_id=case_id,
                        dispute_id=dispute_id,
                        generated_cache_key=cache_key,
                        current_cache_key=current_cache_key,
                    )
                    raise PredictionCacheConflictError(
                        "Case intake changed while generating prediction; retry with current case data."
                    )
                if (
                    locked
                    and locked.cached_prediction_id
                    and locked.prediction_cache_key == current_cache_key
                ):
                    cached = await uow.predictions.get(locked.cached_prediction_id)
                    if cached:
                        logger.info(
                            "returning_cached_dispute_prediction_stage3",
                            case_id=case_id,
                            dispute_id=dispute_id,
                            prediction_id=locked.cached_prediction_id,
                        )
                        return cached

            if kg is not None:
                await uow.knowledge_graphs.save(kg)
            await uow.predictions.save(prediction)
            if cacheable and dispute_id:
                await uow.disputes.set_cached_prediction_id(
                    dispute_id, prediction.prediction_id, cache_key=cache_key
                )

        logger.info(
            "prediction_written",
            case_id=case_id,
            prediction_id=prediction.prediction_id,
            dispute_id=dispute_id,
            cacheable=cacheable,
        )
        return prediction

    async def get_prediction(self, prediction_id: str) -> Optional[Dict]:
        """Get a saved prediction."""
        async with UnitOfWork(self._sm) as uow:
            result = await uow.predictions.get(prediction_id)
        if result is None:
            return None
        return result.model_dump(mode="json")

    async def list_predictions_for_case(self, case_id: str) -> List[Dict]:
        """
        List all predictions for a case.

        Also checks if this case belongs to a dispute with a shared prediction,
        so both parties see the same result.
        """
        async with UnitOfWork(self._sm) as uow:
            # 1. Direct predictions by case_id.
            direct = await uow.predictions.get_by_case_id(case_id)
            seen_ids: set = set()
            predictions: List[Dict] = []
            for p in direct:
                if not await self._prediction_is_current_for_shared_cache(p, uow):
                    continue
                seen_ids.add(p.prediction_id)
                predictions.append(
                    {
                        "prediction_id": p.prediction_id,
                        "timestamp": p.timestamp,
                        "overall_outcome": p.overall_outcome.value,
                        "overall_confidence": p.overall_confidence,
                    }
                )

            # 2. Shared cached dispute prediction.
            try:
                state = await uow.sessions.get_by_case_id(case_id)
                if state:
                    session_id = state.session_id
                    disputes = await uow.disputes.get_by_session_id(session_id)
                    if disputes:
                        dispute = disputes[0]
                        # lock_for_prediction_cache returns the cached_prediction_id
                        # alongside the row lock; acceptable here as this is a
                        # short read transaction and the lock is released at commit.
                        locked = await uow.disputes.lock_for_prediction_cache(
                            dispute.dispute_id
                        )
                        if locked and locked.cached_prediction_id:
                            current_cache_key = (
                                await self._current_cache_key_for_locked_dispute(
                                    locked, uow
                                )
                            )
                            if locked.prediction_cache_key != current_cache_key:
                                logger.info(
                                    "clearing_stale_prediction_cache",
                                    case_id=case_id,
                                    dispute_id=dispute.dispute_id,
                                    cached_prediction_id=locked.cached_prediction_id,
                                    cached_cache_key=locked.prediction_cache_key,
                                    current_cache_key=current_cache_key,
                                )
                                await uow.disputes.set_cached_prediction_id(
                                    dispute.dispute_id, None, cache_key=None
                                )
                                return predictions
                            cached_pid = locked.cached_prediction_id
                            if cached_pid not in seen_ids:
                                cached = await uow.predictions.get(cached_pid)
                                if cached:
                                    seen_ids.add(cached_pid)
                                    predictions.append(
                                        {
                                            "prediction_id": cached.prediction_id,
                                            "timestamp": cached.timestamp,
                                            "overall_outcome": cached.overall_outcome.value,
                                            "overall_confidence": cached.overall_confidence,
                                        }
                                    )
            except Exception as e:
                logger.warning(
                    "dispute_prediction_lookup_failed",
                    case_id=case_id,
                    error=str(e),
                )

        return predictions

    async def _current_cache_key_for_locked_dispute(
        self,
        locked: Any,
        uow: UnitOfWork,
        *,
        domain_segment: str = "",
    ) -> Optional[str]:
        """Build the current shared-prediction cache key from live session versions.

        ``domain_segment`` is prepended (Phase 3) so that the key matches
        what ``_resolve_and_merge_from_repos`` produces for the same domain
        + mode + namespace combination.

        When ``domain_segment`` is empty (e.g. staleness checks invoked from
        ``list_predictions_for_case`` that don't have a fresh runtime context),
        derive the segment from the stored ``prediction_cache_key`` so the
        comparison stays apples-to-apples for legacy rows.
        """
        if not domain_segment:
            stored = getattr(locked, "prediction_cache_key", None)
            if stored and "|" in stored and stored.startswith("d="):
                # Stored key has a Phase-3 domain prefix; reuse it.
                domain_segment = stored.rsplit("|", 1)[0]
        dispute = locked.dispute
        if not dispute.has_both_parties:
            return None

        tenant_session_id = dispute.tenant_session_id
        landlord_session_id = dispute.landlord_session_id
        if not tenant_session_id or not landlord_session_id:
            return None

        tenant = await uow.sessions.get_with_version(tenant_session_id)
        landlord = await uow.sessions.get_with_version(landlord_session_id)
        if not tenant or not landlord:
            return None

        base_key = (
            f"{tenant_session_id}:{tenant.version}:"
            f"{landlord_session_id}:{landlord.version}"
        )
        return f"{domain_segment}|{base_key}" if domain_segment else base_key

    async def _prediction_is_current_for_shared_cache(
        self,
        prediction: Any,
        uow: UnitOfWork,
    ) -> bool:
        """Hide merged predictions whose dispute cache key no longer matches intake."""
        metadata = prediction.metadata or {}
        if not metadata.get("merged") or not metadata.get("dispute_id"):
            return True

        dispute_id = metadata["dispute_id"]
        locked = await uow.disputes.lock_for_prediction_cache(dispute_id)
        if not locked:
            return False

        current_cache_key = await self._current_cache_key_for_locked_dispute(locked, uow)
        prediction_cache_key = metadata.get("prediction_cache_key")
        is_current = (
            locked.cached_prediction_id == prediction.prediction_id
            and locked.prediction_cache_key == current_cache_key
            and prediction_cache_key == current_cache_key
        )
        if not is_current and locked.cached_prediction_id == prediction.prediction_id:
            logger.info(
                "clearing_stale_direct_prediction_cache",
                dispute_id=dispute_id,
                prediction_id=prediction.prediction_id,
                cached_cache_key=locked.prediction_cache_key,
                prediction_cache_key=prediction_cache_key,
                current_cache_key=current_cache_key,
            )
            await uow.disputes.set_cached_prediction_id(dispute_id, None, cache_key=None)
        return is_current

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _resolve_and_merge_from_repos(
        self,
        case_id: str,
        uow: UnitOfWork,
        *,
        domain_segment: str = "",
    ) -> Tuple[CaseFile, Optional[str], bool, Optional[str]]:
        """
        Resolve case_file and optionally merge both parties' data via repos.

        Returns:
            (case_file, dispute_id, cacheable, cache_key)
            - cacheable is True only when BOTH parties are present and merged.
            - cache_key includes both session IDs + their row versions so that
              any save on either session invalidates the cache automatically.
        """
        state = await uow.sessions.get_by_case_id(case_id)
        if not state:
            raise ValueError(f"Case not found: {case_id}")

        case_file = state.case_file
        session_id = state.session_id

        try:
            disputes = await uow.disputes.get_by_session_id(session_id)
            if not disputes:
                logger.debug("no_dispute_for_session", session_id=session_id)
                return case_file, None, False, None

            dispute = disputes[0]
            dispute_id = dispute.dispute_id

            logger.info(
                "dispute_found",
                dispute_id=dispute_id,
                has_both=dispute.has_both_parties,
                status=dispute.status.value,
            )

            if not dispute.has_both_parties:
                # One party joined — link dispute_id for listing but don't cache.
                return case_file, dispute_id, False, None

            # Both parties present — load each session + version.
            tenant_session_id = dispute.tenant_session_id
            landlord_session_id = dispute.landlord_session_id

            # Retrieve versioned sessions for cache-key composition.
            t_versioned = None
            l_versioned = None
            tenant_cf: Optional[CaseFile] = None
            landlord_cf: Optional[CaseFile] = None

            if tenant_session_id:
                t_versioned = await uow.sessions.get_with_version(tenant_session_id)
                if t_versioned:
                    tenant_cf = t_versioned.state.case_file

            if landlord_session_id:
                l_versioned = await uow.sessions.get_with_version(landlord_session_id)
                if l_versioned:
                    landlord_cf = l_versioned.state.case_file

            if tenant_cf and landlord_cf:
                merged = merge_case_files(tenant_cf, landlord_cf)
                t_ver = t_versioned.version if t_versioned else 0
                l_ver = l_versioned.version if l_versioned else 0
                base_key = (
                    f"{tenant_session_id}:{t_ver}:"
                    f"{landlord_session_id}:{l_ver}"
                )
                # SHA-20 Phase 3: prepend the domain/mode segment so that any
                # change to spec/prompt-pack/ontology/corpus/namespace/mode
                # invalidates the cached prediction without touching the
                # session-version segment.
                cache_key = (
                    f"{domain_segment}|{base_key}" if domain_segment else base_key
                )
                logger.info(
                    "case_files_merged",
                    dispute_id=dispute_id,
                    tenant_issues=len(tenant_cf.issues),
                    landlord_issues=len(landlord_cf.issues),
                    merged_issues=len(merged.issues),
                    merged_evidence=len(merged.evidence),
                    cache_key=cache_key,
                )
                return merged, dispute_id, True, cache_key

            # Partial fallback — one side failed to load.
            logger.warning(
                "partial_merge_fallback",
                dispute_id=dispute_id,
                has_tenant_cf=tenant_cf is not None,
                has_landlord_cf=landlord_cf is not None,
            )
            return case_file, dispute_id, False, None

        except ValueError:
            raise
        except SQLAlchemyError:
            raise
        except (KeyError, AttributeError) as exc:
            logger.warning(
                "dispute_merge_failed",
                case_id=case_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return case_file, None, False, None


# ---------------------------------------------------------------------------
# Legacy singleton getter — kept for rollback compatibility.
# The dependencies.py factory no longer calls this; the updated factory in
# dependencies.py creates a per-request PredictionService with the app
# sessionmaker directly.
# ---------------------------------------------------------------------------

def get_prediction_service() -> "PredictionService":
    """Legacy process-singleton getter.  Kept for rollback compatibility."""
    global _prediction_service
    if _prediction_service is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.ext.asyncio import async_sessionmaker as _asm

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sm = _asm(engine, expire_on_commit=False, class_=AsyncSession)
        _prediction_service = PredictionService(sessionmaker=sm)
    return _prediction_service
