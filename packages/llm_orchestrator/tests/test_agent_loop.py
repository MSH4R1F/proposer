"""Tests for AgentLoop control flow (step 4).

Uses a scripted fake LLM client that implements AgentTurnClient by consuming
a queue of pre-built AgentTurnResponse objects. Real @tool-decorated helpers
exercise the genuine ToolSet.dispatch path.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from pydantic import BaseModel

from ..agent_loop.context import ToolContext
from ..agent_loop.loop import (
    AgentLoop,
    AgentLoopResult,
    AgentTurnClient,
    AgentTurnResponse,
)
from ..agent_loop.tool import ToolSet, tool
from ..agent_loop.trace import TraceLogger, TraceTerminationReason


# ---------------------------------------------------------------------------
# Real tools (exercise the genuine Tool.dispatch path)
# ---------------------------------------------------------------------------


class AddArgs(BaseModel):
    a: int
    b: int


@tool(description="Add two integers.")
def add(ctx: ToolContext, args: AddArgs) -> dict:
    return {"sum": args.a + args.b}


class HeavyArgs(BaseModel):
    size: int


@tool(description="Returns a large blob.", max_output_chars=100)
def heavy(ctx: ToolContext, args: HeavyArgs) -> dict:
    return {"blob": "x" * args.size}


def _tool_set() -> ToolSet:
    return ToolSet(name="test", tools=[add, heavy])


# ---------------------------------------------------------------------------
# Scripted fake AgentTurnClient
# ---------------------------------------------------------------------------


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
        self.calls: List[Dict[str, Any]] = []  # captured kwargs per call

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> AgentTurnResponse:
        # Deep-ish snapshot of the messages list so later mutations don't
        # affect what the test inspects.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _ctx() -> ToolContext:
    ctx = ToolContext()
    # ensure each test gets a fresh logger
    ctx.trace_logger = TraceLogger.no_op()
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_tool_turn_returns_text_and_end_turn() -> None:
    client = _ScriptedClient([_text_response("Hello there.")])
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=4)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        ctx=ctx,
    )

    assert isinstance(result, AgentLoopResult)
    assert result.final_text == "Hello there."
    assert result.termination == TraceTerminationReason.END_TURN
    # one model_turn + one termination
    kinds = [s.kind for s in result.trace.steps]
    assert kinds == ["model_turn", "termination"]
    assert result.trace.steps[-1].name == "end_turn"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_one_tool_turn_dispatches_and_returns_final_text() -> None:
    client = _ScriptedClient(
        [
            _tool_use_response(
                [{"id": "tu_1", "name": "add", "input": {"a": 2, "b": 3}}]
            ),
            _text_response("5"),
        ]
    )
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=4)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "add 2 and 3"}],
        ctx=ctx,
    )

    assert result.final_text == "5"
    assert result.termination == TraceTerminationReason.END_TURN

    kinds = [s.kind for s in result.trace.steps]
    assert kinds == ["model_turn", "tool_call", "model_turn", "termination"]

    # Second call should include the tool_result in its messages.
    assert len(client.calls) == 2
    second_msgs = client.calls[1]["messages"]
    # last message before the second model call is the user-side tool_result
    assert second_msgs[-1]["role"] == "user"
    tr_blocks = second_msgs[-1]["content"]
    assert len(tr_blocks) == 1
    assert tr_blocks[0]["type"] == "tool_result"
    assert tr_blocks[0]["tool_use_id"] == "tu_1"
    assert tr_blocks[0]["is_error"] is False
    assert '"sum": 5' in tr_blocks[0]["content"]


@pytest.mark.asyncio
async def test_two_tool_parallel_turn_dispatches_both_before_next_call() -> None:
    client = _ScriptedClient(
        [
            _tool_use_response(
                [
                    {"id": "tu_a", "name": "add", "input": {"a": 1, "b": 2}},
                    {"id": "tu_b", "name": "add", "input": {"a": 10, "b": 20}},
                ]
            ),
            _text_response("done"),
        ]
    )
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=4)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "do two adds"}],
        ctx=ctx,
    )

    assert result.final_text == "done"
    assert result.termination == TraceTerminationReason.END_TURN

    kinds = [s.kind for s in result.trace.steps]
    # model_turn, tool_call, tool_call, model_turn, termination
    assert kinds == [
        "model_turn",
        "tool_call",
        "tool_call",
        "model_turn",
        "termination",
    ]

    # Second call must see a SINGLE user message with TWO tool_result blocks,
    # proving both tools were dispatched before the next model call.
    second_msgs = client.calls[1]["messages"]
    assert second_msgs[-1]["role"] == "user"
    tr_blocks = second_msgs[-1]["content"]
    assert len(tr_blocks) == 2
    ids = {b["tool_use_id"] for b in tr_blocks}
    assert ids == {"tu_a", "tu_b"}


@pytest.mark.asyncio
async def test_tool_error_is_error_flag_flows_back_to_model() -> None:
    # 'a' is required to be int; pass a non-coercible string to force
    # Pydantic validation failure inside Tool.dispatch.
    client = _ScriptedClient(
        [
            _tool_use_response(
                [{"id": "tu_1", "name": "add", "input": {"a": "x", "b": 3}}]
            ),
            _text_response("recovered"),
        ]
    )
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=4)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "try bad add"}],
        ctx=ctx,
    )

    assert result.termination == TraceTerminationReason.END_TURN
    assert result.final_text == "recovered"

    # The tool step must be a tool_error.
    tool_steps = [s for s in result.trace.steps if s.kind == "tool_error"]
    assert len(tool_steps) == 1
    assert tool_steps[0].is_error is True

    # And the model saw is_error=True in the tool_result it received.
    second_msgs = client.calls[1]["messages"]
    tr_block = second_msgs[-1]["content"][0]
    assert tr_block["type"] == "tool_result"
    assert tr_block["is_error"] is True
    assert "Invalid arguments" in tr_block["content"]


@pytest.mark.asyncio
async def test_model_error_records_termination_and_reraises() -> None:
    err = RuntimeError("model went boom")
    client = _ScriptedClient(raise_on_call=err)
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=3)

    ctx = _ctx()
    with pytest.raises(RuntimeError, match="model went boom"):
        await loop.run(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            ctx=ctx,
        )

    # ctx.trace_logger retains the steps recorded before the raise.
    steps = ctx.trace_logger._steps
    assert len(steps) == 1
    assert steps[0].kind == "termination"
    assert steps[0].name == "model_error"
    assert steps[0].is_error is True


@pytest.mark.asyncio
async def test_max_turns_terminates_with_max_turns_reason() -> None:
    # A single tool_use response that the scripted client serves forever.
    looping = _tool_use_response(
        [{"id": "tu_loop", "name": "add", "input": {"a": 1, "b": 1}}]
    )
    client = _ScriptedClient(loop_forever=looping)
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=3)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "loop"}],
        ctx=ctx,
    )

    assert result.termination == TraceTerminationReason.MAX_TURNS
    assert result.final_text is None

    # Exactly 3 model_turn steps and 3 tool_call steps, then a termination.
    model_turns = [s for s in result.trace.steps if s.kind == "model_turn"]
    tool_calls = [s for s in result.trace.steps if s.kind == "tool_call"]
    terms = [s for s in result.trace.steps if s.kind == "termination"]
    assert len(model_turns) == 3
    assert len(tool_calls) == 3
    assert len(terms) == 1
    assert terms[0].name == "max_turns"
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_payload_budget_truncates_model_payload_and_preview() -> None:
    client = _ScriptedClient(
        [
            _tool_use_response(
                [{"id": "tu_h", "name": "heavy", "input": {"size": 10_000}}]
            ),
            _text_response("ok"),
        ]
    )
    loop = AgentLoop(llm_client=client, tool_set=_tool_set(), max_turns=4)

    ctx = _ctx()
    result = await loop.run(
        system_prompt="sys",
        messages=[{"role": "user", "content": "fetch big"}],
        ctx=ctx,
    )

    assert result.termination == TraceTerminationReason.END_TURN

    # 1. Model receives the *truncated* model_payload on its second call.
    second_msgs = client.calls[1]["messages"]
    tr_block = second_msgs[-1]["content"][0]
    assert tr_block["type"] == "tool_result"
    assert tr_block["is_error"] is False
    # content is the serialized model_payload; it must be short and carry the
    # truncation marker produced by Tool.dispatch.
    content_str = tr_block["content"]
    assert '"truncated": true' in content_str
    # Full 10 000-char blob must NOT be in the wire payload.
    assert ("x" * 10_000) not in content_str

    # 2. Trace's output_preview on the tool_call is the (short) redacted text,
    # not a 10 000-char dump.
    tool_step = next(s for s in result.trace.steps if s.kind == "tool_call")
    assert tool_step.output_preview is not None
    assert len(tool_step.output_preview) <= 501  # 500 + ellipsis
