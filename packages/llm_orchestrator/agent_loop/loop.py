"""Agent control-flow loop.

Drives a conversation with an LLM that can call tools. The loop is agnostic of
the underlying model backend: anything that implements :class:`AgentTurnClient`
works. A fake scripted client is used in tests; the real Anthropic adapter
lands in step 5.

Contract (mirrors Architecture > AgentLoop behavior 1-8):
    1. Start trace via ``ctx.trace_logger.start_trace(...)``.
    2. Each iteration call ``llm_client.run_agent_turn(...)``.
    3. Record a ``model_turn`` step with latency and token usage.
    4. If response has no ``tool_use`` blocks and stop_reason == ``end_turn``:
       record termination and return final text.
    5. For each ``tool_use`` block dispatch through ``ToolSet``, record a
       ``tool_call`` / ``tool_error`` step, append a ``tool_result`` block to
       the conversation with the compact ``model_payload``.
    6. If the LLM call fails after its own retries, record ``MODEL_ERROR`` and
       re-raise.
    7. If ``max_turns`` reached without ``end_turn``: record ``MAX_TURNS`` and
       return with ``final_text=None``.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from ..clients.types import LLMProvider
from .context import ToolContext
from .tool import ToolResult, ToolSet, UnknownToolError
from .trace import (
    TraceStep,
    TraceSummary,
    TraceTerminationReason,
    _scrub_employment_trace_text,
    redact_text,
)

_PREVIEW_MAX_CHARS = 500


class AgentTurnResponse(BaseModel):
    """Single response from the LLM for one turn of the agent loop."""

    content_blocks: List[Dict[str, Any]]
    stop_reason: str
    tokens_in: int
    tokens_out: int
    model_used: str


class AgentLoopResult(BaseModel):
    """Outcome of a full :meth:`AgentLoop.run` call."""

    final_text: Optional[str]
    trace: TraceSummary
    termination: TraceTerminationReason


@runtime_checkable
class AgentTurnClient(Protocol):
    """Minimal surface an LLM adapter must expose for the AgentLoop."""

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> AgentTurnResponse:
        ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_ms(start: float) -> int:
    return max(0, int((time.monotonic() - start) * 1000))


def _preview(
    value: Any,
    *,
    redact: bool,
    domain_family: Optional[str] = None,
    party_names: Optional[List[str]] = None,
) -> str:
    """Render a preview string for trace steps (truncated, optionally redacted).

    SHA-20 Phase 8: when ``domain_family == "employment"`` the text is run
    through :func:`_scrub_employment_trace_text` BEFORE storage, on top of
    the standard ``redact_text`` path. Other families are unaffected.
    """
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            text = repr(value)
    if redact:
        text = redact_text(text, max_chars=_PREVIEW_MAX_CHARS)
    elif len(text) > _PREVIEW_MAX_CHARS:
        text = text[:_PREVIEW_MAX_CHARS] + "\u2026"
    if domain_family == "employment":
        text = _scrub_employment_trace_text(
            text,
            party_names=party_names,
            max_chars=_PREVIEW_MAX_CHARS,
        )
    return text


def _extract_text(content_blocks: List[Dict[str, Any]]) -> Optional[str]:
    parts: List[str] = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text_val = block.get("text")
            if isinstance(text_val, str):
                parts.append(text_val)
    if not parts:
        return None
    return "".join(parts)


def _tool_use_blocks(content_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        block
        for block in content_blocks
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


class AgentLoop:
    """Driver that alternates LLM turns with tool execution until termination."""

    def __init__(
        self,
        *,
        llm_client: AgentTurnClient,
        tool_set: ToolSet,
        model: Optional[str] = None,
        max_turns: int = 8,
        max_tokens: int = 1024,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
    ) -> None:
        # ``provider`` selects the tool-schema shape ``ToolSet.schemas_for``
        # emits for each model turn. Defaults to ANTHROPIC so existing call
        # sites (and tests that construct AgentLoop with an Anthropic-shaped
        # fake client) keep working unchanged. OpenAI-backed callers must
        # opt in explicitly — typically via ``provider=role_cfg.provider``
        # at construction time.
        self.llm_client = llm_client
        self.tool_set = tool_set
        self.model = model
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.provider = provider

    async def run(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
    ) -> AgentLoopResult:
        # SHA-20 Phase 3+8: forward domain tags into the trace so LangFuse
        # spans + the no-op TraceSummary metadata both carry the routing
        # context. ``ctx.domain_tags`` is empty when no domain runtime has
        # been resolved (legacy / test paths). The employment-family
        # scrubbing path reads ``ctx.domain_tags["domain.family"]`` to
        # decide whether to apply :func:`_scrub_employment_trace_text`.
        ctx.trace_logger.start_trace(
            trace_id=ctx.request_id,
            tags=dict(ctx.domain_tags) if ctx.domain_tags else None,
        )
        domain_family = (ctx.domain_tags or {}).get("domain.family")
        party_names = list(ctx.employment_party_names or ())

        def _prev(value: Any) -> str:
            return _preview(
                value,
                redact=ctx.redact_pii,
                domain_family=domain_family,
                party_names=party_names,
            )

        # Don't mutate the caller's list.
        local_messages: List[Dict[str, Any]] = list(messages)
        tool_schemas = self.tool_set.schemas_for(self.provider)

        step_index = 0

        for _turn in range(self.max_turns):
            # --- Model turn ---
            turn_started_at = _now()
            turn_clock_start = time.monotonic()
            try:
                response = await self.llm_client.run_agent_turn(
                    system_prompt=system_prompt,
                    messages=local_messages,
                    tool_schemas=tool_schemas,
                    model=self.model,
                    max_tokens=self.max_tokens,
                )
            except Exception as exc:
                # Model call failed after the client's own retries. Record the
                # termination step then re-raise; caller can recover the trace
                # from ctx.trace_logger if they need to.
                err_preview = _prev(str(exc))
                ctx.trace_logger.record_step(
                    TraceStep(
                        index=step_index,
                        kind="termination",
                        name="model_error",
                        started_at=turn_started_at,
                        duration_ms=_elapsed_ms(turn_clock_start),
                        output_preview=err_preview,
                        is_error=True,
                    )
                )
                step_index += 1
                ctx.trace_logger.end_trace(
                    termination=TraceTerminationReason.MODEL_ERROR
                )
                raise

            turn_duration = _elapsed_ms(turn_clock_start)
            ctx.trace_logger.record_step(
                TraceStep(
                    index=step_index,
                    kind="model_turn",
                    name=response.model_used,
                    started_at=turn_started_at,
                    duration_ms=turn_duration,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    output_preview=_prev(
                        _extract_text(response.content_blocks) or ""
                    ),
                )
            )
            step_index += 1

            # Append the assistant message to the rolling conversation.
            local_messages.append(
                {"role": "assistant", "content": response.content_blocks}
            )

            tool_use_blocks = _tool_use_blocks(response.content_blocks)

            # --- Terminal end_turn ---
            if not tool_use_blocks and response.stop_reason == "end_turn":
                final_text = _extract_text(response.content_blocks)
                term_started_at = _now()
                ctx.trace_logger.record_step(
                    TraceStep(
                        index=step_index,
                        kind="termination",
                        name="end_turn",
                        started_at=term_started_at,
                        duration_ms=0,
                        output_preview=_prev(final_text or ""),
                    )
                )
                step_index += 1
                summary = ctx.trace_logger.end_trace(
                    termination=TraceTerminationReason.END_TURN
                )
                return AgentLoopResult(
                    final_text=final_text,
                    trace=summary,
                    termination=TraceTerminationReason.END_TURN,
                )

            # --- Dispatch tool_use blocks (possibly multiple in one turn — dispatched sequentially here) ---
            if tool_use_blocks:
                tool_result_blocks: List[Dict[str, Any]] = []
                for block in tool_use_blocks:
                    tool_name = str(block.get("name", ""))
                    raw_args = block.get("input") or {}
                    if not isinstance(raw_args, dict):
                        raw_args = {}
                    tool_use_id = str(block.get("id", ""))

                    tool_started_at = _now()
                    tool_clock_start = time.monotonic()
                    try:
                        result = await self.tool_set.dispatch(
                            tool_name, raw_args, ctx
                        )
                    except UnknownToolError:
                        result = ToolResult(
                            is_error=True,
                            model_payload={
                                "error": f"Unknown tool: {tool_name}"
                            },
                        )

                    tool_duration = _elapsed_ms(tool_clock_start)

                    step_kind = "tool_error" if result.is_error else "tool_call"
                    ctx.trace_logger.record_step(
                        TraceStep(
                            index=step_index,
                            kind=step_kind,
                            name=tool_name,
                            started_at=tool_started_at,
                            duration_ms=tool_duration,
                            input_preview=_prev(raw_args),
                            output_preview=_prev(result.model_payload),
                            is_error=result.is_error,
                        )
                    )
                    step_index += 1

                    # Serialize model_payload for the wire. Anthropic accepts a
                    # string content for tool_result; we use JSON for structure.
                    try:
                        payload_text = json.dumps(
                            result.model_payload, ensure_ascii=True, default=str
                        )
                    except Exception:
                        payload_text = str(result.model_payload)

                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": payload_text,
                            "is_error": result.is_error,
                        }
                    )

                local_messages.append(
                    {"role": "user", "content": tool_result_blocks}
                )
                # Loop back for the next model turn.
                continue

            # No tool_use blocks and stop_reason wasn't end_turn (e.g.
            # max_tokens, pause_turn). Looping would resend an
            # assistant-terminated message list — Anthropic rejects that and we
            # would mislabel a benign stop as MODEL_ERROR. Terminate now and
            # surface whatever text the model produced.
            final_text = _extract_text(response.content_blocks)
            term_started_at = _now()
            ctx.trace_logger.record_step(
                TraceStep(
                    index=step_index,
                    kind="termination",
                    name=f"stop_{response.stop_reason}",
                    started_at=term_started_at,
                    duration_ms=0,
                    output_preview=_prev(final_text or ""),
                )
            )
            step_index += 1
            summary = ctx.trace_logger.end_trace(
                termination=TraceTerminationReason.END_TURN
            )
            return AgentLoopResult(
                final_text=final_text,
                trace=summary,
                termination=TraceTerminationReason.END_TURN,
            )

        # --- Max turns reached ---
        term_started_at = _now()
        ctx.trace_logger.record_step(
            TraceStep(
                index=step_index,
                kind="termination",
                name="max_turns",
                started_at=term_started_at,
                duration_ms=0,
            )
        )
        step_index += 1
        summary = ctx.trace_logger.end_trace(
            termination=TraceTerminationReason.MAX_TURNS
        )
        return AgentLoopResult(
            final_text=None,
            trace=summary,
            termination=TraceTerminationReason.MAX_TURNS,
        )
