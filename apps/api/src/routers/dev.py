"""Debug-only router for the agent-loop smoke endpoint.

Mounted only when config.debug is true (see main.create_app).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from llm_orchestrator.agent_loop.context import ToolContext
from llm_orchestrator.agent_loop.loop import AgentLoop
from llm_orchestrator.agent_loop.trace import TraceSummary
from llm_orchestrator.clients.base import BaseLLMClient
from llm_orchestrator.clients.types import LLMProvider
from llm_orchestrator.tools.smoke import SMOKE_TOOLS

from ..dependencies import get_agent_loop_client, get_agent_loop_provider, get_tool_context

logger = structlog.get_logger()

router = APIRouter(prefix="/api/dev", tags=["dev"])


class AgentSmokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    max_turns: Optional[int] = Field(default=None, ge=1, le=16)


class AgentSmokeResponse(BaseModel):
    final_text: Optional[str]
    termination: str
    trace_summary: TraceSummary


@router.post("/agent-smoke", response_model=AgentSmokeResponse)
async def agent_smoke(
    body: AgentSmokeRequest,
    ctx: ToolContext = Depends(get_tool_context),
    client: BaseLLMClient = Depends(get_agent_loop_client),
    provider: LLMProvider = Depends(get_agent_loop_provider),
) -> AgentSmokeResponse:
    """Run the agent loop against SMOKE_TOOLS with a single user prompt."""
    loop = AgentLoop(
        llm_client=client,
        tool_set=SMOKE_TOOLS,
        max_turns=body.max_turns or 8,
        provider=provider,
    )
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": body.prompt}
    ]
    result = await loop.run(
        system_prompt=(
            "You are an agent with access to a small set of deterministic tools. "
            "Use them when they help answer the user's question."
        ),
        messages=messages,
        ctx=ctx,
    )
    logger.info(
        "agent_smoke_completed",
        request_id=ctx.request_id,
        termination=result.termination.value,
        step_count=len(result.trace.steps),
    )
    return AgentSmokeResponse(
        final_text=result.final_text,
        termination=result.termination.value,
        trace_summary=result.trace,
    )
