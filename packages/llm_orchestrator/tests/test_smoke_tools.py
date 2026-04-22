"""Tests for the smoke ToolSet (echo, add).

These tests exercise the full @tool -> schema -> dispatch -> result path for
the two smoke tools, plus an end-to-end run through AgentLoop using a
scripted fake AgentTurnClient.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from ..agent_loop.context import ToolContext
from ..agent_loop.loop import (
    AgentLoop,
    AgentTurnResponse,
)
from ..agent_loop.tool import UnknownToolError
from ..agent_loop.trace import TraceLogger, TraceTerminationReason
from ..tools.smoke import SMOKE_TOOLS, add, echo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx() -> ToolContext:
    ctx = ToolContext()
    ctx.trace_logger = TraceLogger.no_op()
    return ctx


class _ScriptedClient:
    """Consumes a queue of AgentTurnResponse objects; can optionally loop a
    single response forever (for max-turns tests), or raise a pre-seeded error.
    """

    def __init__(
        self,
        responses: Optional[List[AgentTurnResponse]] = None,
        *,
        loop_forever: Optional[AgentTurnResponse] = None,
        raise_on_call: Optional[Exception] = None,
    ) -> None:
        self._responses: List[AgentTurnResponse] = list(responses or [])
        self._loop_forever = loop_forever
        self._raise_on_call = raise_on_call
        self.calls: List[Dict[str, Any]] = []

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> AgentTurnResponse:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "messages": [dict(m) for m in messages],
                "tool_schemas": list(tool_schemas),
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        if self._raise_on_call is not None:
            raise self._raise_on_call
        if self._responses:
            return self._responses.pop(0)
        if self._loop_forever is not None:
            return self._loop_forever
        raise AssertionError(
            "Scripted client called more times than scripted."
        )


def _text_response(text: str, *, tokens_in: int = 10, tokens_out: int = 5) -> AgentTurnResponse:
    return AgentTurnResponse(
        content_blocks=[{"type": "text", "text": text}],
        stop_reason="end_turn",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_used="fake-model",
    )


def _tool_use_response(
    calls: List[Dict[str, Any]],
    *,
    tokens_in: int = 12,
    tokens_out: int = 7,
) -> AgentTurnResponse:
    content_blocks = [
        {
            "type": "tool_use",
            "id": call["id"],
            "name": call["name"],
            "input": call["input"],
        }
        for call in calls
    ]
    return AgentTurnResponse(
        content_blocks=content_blocks,
        stop_reason="tool_use",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_used="fake-model",
    )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_echo_schema_has_required_message() -> None:
    schema = echo.to_anthropic_schema()
    assert schema["name"] == "echo"
    assert isinstance(schema["description"], str) and schema["description"]
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    assert "message" in input_schema["properties"]
    assert input_schema["properties"]["message"]["type"] == "string"
    assert input_schema["required"] == ["message"]


def test_add_schema_has_required_int_args() -> None:
    schema = add.to_anthropic_schema()
    assert schema["name"] == "add"
    assert isinstance(schema["description"], str) and schema["description"]
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    assert "a" in input_schema["properties"]
    assert "b" in input_schema["properties"]
    assert input_schema["properties"]["a"]["type"] == "integer"
    assert input_schema["properties"]["b"]["type"] == "integer"
    assert "a" in input_schema["required"]
    assert "b" in input_schema["required"]


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_echo_dispatch_returns_echoed_message() -> None:
    ctx = _ctx()
    result = await echo.dispatch(ctx, {"message": "hello"})
    assert result.is_error is False
    assert result.model_payload == {"echoed": "hello"}


@pytest.mark.asyncio
async def test_add_dispatch_returns_sum() -> None:
    ctx = _ctx()
    result = await add.dispatch(ctx, {"a": 2, "b": 3})
    assert result.is_error is False
    assert result.model_payload == {"sum": 5}


# ---------------------------------------------------------------------------
# ToolSet tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smoke_tool_set_routes_by_name() -> None:
    ctx = _ctx()

    echo_result = await SMOKE_TOOLS.dispatch("echo", {"message": "hi"}, ctx)
    assert echo_result.model_payload == {"echoed": "hi"}

    add_result = await SMOKE_TOOLS.dispatch("add", {"a": 1, "b": 2}, ctx)
    assert add_result.model_payload == {"sum": 3}

    with pytest.raises(UnknownToolError):
        await SMOKE_TOOLS.dispatch("nope", {}, ctx)


def test_smoke_tool_set_anthropic_schemas() -> None:
    schemas = SMOKE_TOOLS.anthropic_schemas()
    assert len(schemas) == 2
    names = {s["name"] for s in schemas}
    assert names == {"echo", "add"}


# ---------------------------------------------------------------------------
# End-to-end AgentLoop test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_loop_runs_add_end_to_end() -> None:
    client = _ScriptedClient(
        [
            _tool_use_response(
                [{"id": "tu_1", "name": "add", "input": {"a": 17, "b": 25}}]
            ),
            _text_response("42"),
        ]
    )
    loop = AgentLoop(llm_client=client, tool_set=SMOKE_TOOLS, max_turns=4)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "do math"}],
        ctx=ctx,
    )

    assert result.final_text == "42"
    assert result.termination == TraceTerminationReason.END_TURN

    kinds = [s.kind for s in result.trace.steps]
    assert kinds == ["model_turn", "tool_call", "model_turn", "termination"]
