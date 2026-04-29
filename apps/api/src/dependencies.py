"""FastAPI dependencies for the agent-loop foundation.

Intentionally thin. get_tool_context composes request metadata and the
minimum dependencies a tool needs; get_agent_loop_client returns a cached
ClaudeClient for the debug smoke endpoint.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from collections.abc import AsyncIterator
from typing import Any, Optional

from fastapi import Request

from apps.api.src.db.uow import UnitOfWork
from llm_orchestrator.agent_loop.context import ToolContext
from llm_orchestrator.agent_loop.trace import LangFuseTraceLogger, TraceLogger
from llm_orchestrator.clients.claude_client import ClaudeClient

from .config import config


def get_tool_context(request: Request) -> ToolContext:
    """Build a per-request ToolContext.

    Pulls an X-Request-Id header if present, otherwise generates one.
    When LangFuse is fully configured (public key, secret key, and host all
    set) we export traces to it; otherwise fall back to the no-op logger.
    """
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    trace_logger: TraceLogger
    if config.langfuse_configured:
        trace_logger = LangFuseTraceLogger(
            public_key=config.langfuse_public_key,
            secret_key=config.langfuse_secret_key,
            host=config.langfuse_host,
        )
    else:
        trace_logger = TraceLogger.no_op()
    return ToolContext(
        request_id=request_id,
        trace_logger=trace_logger,
        redact_pii=True,
    )


@lru_cache(maxsize=1)
def _cached_agent_loop_client() -> ClaudeClient:
    return ClaudeClient(api_key=config.anthropic_api_key)


def get_agent_loop_client() -> ClaudeClient:
    """Return a process-cached ClaudeClient for the agent loop smoke path."""
    return _cached_agent_loop_client()


async def get_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    """Yield one UnitOfWork bound to the request-scoped app sessionmaker."""
    async with UnitOfWork(request.app.state.db_sessionmaker) as uow:
        yield uow


# --- Service factories (Task 5.4) -------------------------------------------
#
# Routers import these instead of pulling singleton getters out of the
# service modules directly. Each factory takes a request-scoped UnitOfWork so
# that Phase 6-9 service rewrites can drop their internal mutable caches
# without further router changes — only the factory body and service
# constructor change.
#
# Until each service is rewritten, the factory ignores `uow` and returns
# the legacy process-singleton; the UoW just rides along on the request so
# /readyz and downstream rewrites see a live transactional boundary.

from fastapi import Depends  # noqa: E402

from apps.api.src.services.dispute_service import (  # noqa: E402
    DisputeService,
    get_dispute_service as _legacy_get_dispute_service,
)
from apps.api.src.services.intake_service import (  # noqa: E402
    IntakeService,
    get_intake_service as _legacy_get_intake_service,  # kept for rollback
)
from llm_orchestrator.agents.intake_agent import IntakeAgent  # noqa: E402
from apps.api.src.services.mediation_service import (  # noqa: E402
    MediationService,
    get_mediation_service as _legacy_get_mediation_service,
)
from apps.api.src.services.prediction_service import (  # noqa: E402
    PredictionService,
    _build_prediction_engine,
    get_prediction_service as _legacy_get_prediction_service,
)
from apps.api.src.services.storage_service import (  # noqa: E402
    StorageService,
    get_storage_service as _legacy_get_storage_service,
)


@lru_cache(maxsize=1)
def _cached_intake_agent() -> IntakeAgent:
    """Process-level cache for the heavy LLM agent (avoids per-request client construction)."""
    from llm_orchestrator.clients.claude_client import ClaudeClient
    from llm_orchestrator.config import LLMConfig

    cfg = LLMConfig.from_env()
    return IntakeAgent(ClaudeClient(api_key=cfg.anthropic_api_key))


def get_intake_service(request: Request) -> IntakeService:
    """Per-request IntakeService backed by the request-scoped Postgres sessionmaker."""
    sm = request.app.state.db_sessionmaker
    return IntakeService(sessionmaker=sm, agent=_cached_intake_agent())


def get_dispute_service(request: Request) -> DisputeService:
    """Per-request DisputeService backed by the request-scoped Postgres sessionmaker."""
    sm = request.app.state.db_sessionmaker
    return DisputeService(sessionmaker=sm)


@lru_cache(maxsize=1)
def _cached_prediction_engine() -> Any:
    """Process-level cache for the heavy prediction engine + RAG pipeline."""
    return _build_prediction_engine()


def get_prediction_service(request: Request) -> PredictionService:
    """Per-request PredictionService backed by the request-scoped sessionmaker."""
    sm = request.app.state.db_sessionmaker
    # Engine/graph_builder/RAG are constructed lazily inside PredictionService
    # via internal helpers; we don't need to inject them at this layer.
    return PredictionService(sessionmaker=sm)


def get_storage_service(
    uow: UnitOfWork = Depends(get_uow),
) -> StorageService:
    """Per-request StorageService. Phase 8.1 will swap to a UoW-aware ctor."""
    del uow
    return _legacy_get_storage_service()


def get_mediation_service(
    uow: UnitOfWork = Depends(get_uow),
) -> MediationService:
    """Per-request MediationService. Phase 9.1 will swap to a UoW-aware ctor."""
    del uow
    return _legacy_get_mediation_service()
