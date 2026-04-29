"""FastAPI dependencies for the agent-loop foundation.

Intentionally thin. get_tool_context composes request metadata and the
minimum dependencies a tool needs; get_agent_loop_client returns a cached
ClaudeClient for the debug smoke endpoint.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from collections.abc import AsyncIterator
from typing import Optional

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
