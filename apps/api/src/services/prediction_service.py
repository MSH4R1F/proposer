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

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_orchestrator.models.case_file import CaseFile, merge_case_files

from apps.api.src.db.uow import UnitOfWork

logger = structlog.get_logger()

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
    from llm_orchestrator.config import LLMConfig
    from llm_orchestrator.clients.claude_client import ClaudeClient
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    llm_config = LLMConfig.from_env()
    llm_client = ClaudeClient(api_key=llm_config.anthropic_api_key)
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

    # ------------------------------------------------------------------
    # Lazy property accessors for heavy components
    # ------------------------------------------------------------------

    @property
    def prediction_engine(self) -> Any:
        """Process-cached prediction engine (constructed on first use)."""
        if self._engine is None:
            self._engine = _build_prediction_engine()
        return self._engine

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
    ) -> Any:
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
        # ── Stage 1: short read transaction ─────────────────────────────────
        async with UnitOfWork(self._sm) as uow:
            case_file, dispute_id, cacheable, cache_key = (
                await self._resolve_and_merge_from_repos(case_id, uow)
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
        kg = self.graph_builder.build(case_file)
        prediction = await self.prediction_engine.predict(
            case_file=case_file,
            knowledge_graph=kg,
        )

        if cacheable and dispute_id:
            prediction.metadata["dispute_id"] = dispute_id
            prediction.metadata["merged"] = True
            prediction.metadata["prediction_cache_key"] = cache_key

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
                    await self._current_cache_key_for_locked_dispute(locked, uow)
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
    ) -> Optional[str]:
        """Build the current shared-prediction cache key from live session versions."""
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

        return (
            f"{tenant_session_id}:{tenant.version}:"
            f"{landlord_session_id}:{landlord.version}"
        )

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
                cache_key = (
                    f"{tenant_session_id}:{t_ver}:"
                    f"{landlord_session_id}:{l_ver}"
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
        except Exception as e:
            logger.warning(
                "dispute_merge_failed",
                case_id=case_id,
                error=str(e),
                error_type=type(e).__name__,
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
