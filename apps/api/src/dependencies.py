"""FastAPI dependencies for the agent-loop foundation.

Intentionally thin. get_tool_context composes request metadata and the
minimum dependencies a tool needs; get_agent_loop_client returns a cached
role-aware LLM client for the debug smoke endpoint.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from fastapi import Request

from apps.api.src.db.uow import UnitOfWork
from llm_orchestrator.agent_loop.context import ToolContext
from llm_orchestrator.agent_loop.trace import LangFuseTraceLogger, TraceLogger
from llm_orchestrator.clients.base import BaseLLMClient
from llm_orchestrator.clients.factory import get_llm_client
from llm_orchestrator.clients.types import LLMProvider, LLMRole
from llm_orchestrator.config import LLMConfig

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
def _cached_agent_loop_client() -> BaseLLMClient:
    # The /api/dev agent-smoke endpoint is a generic debug surface — it has
    # no role-specific behaviour, so we route through the PREDICTION role's
    # config (the most likely role to be flipped to OpenAI in dev/eval).
    # Operators can swap providers via ``LLM_PREDICTION_PROVIDER=openai``
    # without touching this file.
    return get_llm_client(LLMRole.PREDICTION)


@lru_cache(maxsize=1)
def _cached_agent_loop_provider() -> LLMProvider:
    return LLMConfig().role_config(LLMRole.PREDICTION).provider


def get_agent_loop_client() -> BaseLLMClient:
    """Return a process-cached LLM client for the agent loop smoke path."""
    return _cached_agent_loop_client()


def get_agent_loop_provider() -> LLMProvider:
    """Return the provider backing the generic debug agent-loop client."""
    return _cached_agent_loop_provider()


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

from apps.api.src.services.dispute_service import (  # noqa: E402
    DisputeService,
    get_dispute_service as _legacy_get_dispute_service,  # noqa: F401
)
from apps.api.src.services.intake_service import (  # noqa: E402
    IntakeService,
    get_intake_service as _legacy_get_intake_service,  # noqa: F401
)
from llm_orchestrator.agents.intake_agent import IntakeAgent  # noqa: E402
from apps.api.src.services.mediation_service import (  # noqa: E402
    MediationService,
    get_mediation_service as _legacy_get_mediation_service,  # noqa: F401
)
from apps.api.src.services.prediction_service import (  # noqa: E402
    PredictionService,
    _build_prediction_engine,
    get_prediction_service as _legacy_get_prediction_service,  # noqa: F401
)
from apps.api.src.services.storage_service import StorageService  # noqa: E402


@lru_cache(maxsize=1)
def _cached_intake_agent() -> IntakeAgent:
    """Process-level cache for the heavy LLM agent (avoids per-request client construction)."""
    return IntakeAgent(get_llm_client(LLMRole.INTAKE))


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
    return PredictionService(
        sessionmaker=sm,
        engine=_cached_prediction_engine(),
    )


def get_storage_service(request: Request) -> StorageService:
    """Per-request StorageService backed by the request-scoped sessionmaker."""
    sm = request.app.state.db_sessionmaker
    return StorageService(sessionmaker=sm)


# --- SHA-20 Phase 9: domain router -----------------------------------------
#
# The router is process-cached because it holds only static phrase tables
# and a (currently null) LLM classifier. When the router flag is off the
# factory still returns a router instance — callers gate on
# ``config.domain_router_enabled`` themselves so the deposit-default path
# remains identical to Phase 3 behaviour.

@lru_cache(maxsize=1)
def _cached_domain_router():
    from llm_orchestrator.routing import build_default_router

    return build_default_router(tuple(config.enabled_domains))


def get_domain_router():  # type: ignore[no-untyped-def]
    """Return the process-cached :class:`DomainRouter`.

    The router is shared across requests; it is stateless apart from
    its configured enabled-domain list. Configuration changes between
    process restarts are picked up automatically (we read
    ``config.enabled_domains`` once per process).
    """
    return _cached_domain_router()


@lru_cache(maxsize=1)
def _cached_mediator_agent() -> Any:
    """Process-level cache for the heavy LLM mediator agent."""
    from llm_orchestrator.agents.mediator_agent import MediatorAgent

    llm_config = LLMConfig()
    return MediatorAgent(
        get_llm_client(LLMRole.MEDIATOR, config=llm_config),
        provider=llm_config.role_config(LLMRole.MEDIATOR).provider,
    )


def get_mediation_service(request: Request) -> MediationService:
    """Per-request MediationService backed by the request-scoped Postgres sessionmaker."""
    sm = request.app.state.db_sessionmaker
    return MediationService(sessionmaker=sm, mediator_agent=_cached_mediator_agent())
