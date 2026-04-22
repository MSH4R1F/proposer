"""Tests for ClaudeClient.run_agent_turn (step 5).

Validates that the AgentLoop-facing adapter method on ClaudeClient:
- forwards ``tools=`` and other kwargs to ``messages.create``
- preserves every content block in order (including multiple ``tool_use``)
- increments usage stats
- surfaces ``stop_reason``
- honours a per-call ``model`` override

Retry / fallback behaviour is already exercised by the ``generate()`` tests,
so it is not re-validated here.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from ..agent_loop.loop import AgentTurnResponse
from ..clients.claude_client import ClaudeClient


# ---------------------------------------------------------------------------
# Fake SDK response builders
# ---------------------------------------------------------------------------


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(
    *, id: str, name: str, input: Dict[str, Any]
) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _fake_response(
    *,
    content: List[SimpleNamespace],
    stop_reason: str = "end_turn",
    tokens_in: int = 100,
    tokens_out: int = 50,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out),
    )


def _make_client() -> ClaudeClient:
    """Fresh client with clean stats for each test."""
    return ClaudeClient(api_key="test-key")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_turn_forwards_tools_kwarg() -> None:
    client = _make_client()
    fake = _fake_response(
        content=[_text_block("hi")],
        stop_reason="end_turn",
    )
    create_mock = AsyncMock(return_value=fake)
    client.client.messages.create = create_mock

    messages = [{"role": "user", "content": "hello"}]
    tool_schemas = [
        {
            "name": "add",
            "description": "Add two integers.",
            "input_schema": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            },
        }
    ]
    system_prompt = "You are a helpful assistant."

    await client.run_agent_turn(
        system_prompt=system_prompt,
        messages=messages,
        tool_schemas=tool_schemas,
    )

    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["tools"] == tool_schemas
    assert kwargs["system"] == system_prompt
    assert kwargs["messages"] == messages
    assert kwargs["max_tokens"] == 1024
    assert kwargs["model"] == client.model


@pytest.mark.asyncio
async def test_run_agent_turn_preserves_multiple_tool_use_blocks() -> None:
    client = _make_client()
    fake = _fake_response(
        content=[
            _text_block("I'll run two tools."),
            _tool_use_block(id="toolu_01", name="add", input={"a": 1, "b": 2}),
            _tool_use_block(
                id="toolu_02", name="add", input={"a": 10, "b": 20}
            ),
        ],
        stop_reason="tool_use",
    )
    client.client.messages.create = AsyncMock(return_value=fake)

    result = await client.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "do math"}],
        tool_schemas=[],
    )

    assert isinstance(result, AgentTurnResponse)
    assert len(result.content_blocks) == 3

    # Order preserved
    assert result.content_blocks[0] == {"type": "text", "text": "I'll run two tools."}
    assert result.content_blocks[1] == {
        "type": "tool_use",
        "id": "toolu_01",
        "name": "add",
        "input": {"a": 1, "b": 2},
    }
    assert result.content_blocks[2] == {
        "type": "tool_use",
        "id": "toolu_02",
        "name": "add",
        "input": {"a": 10, "b": 20},
    }

    # Both tool_use blocks are distinct entries (not collapsed).
    tool_use_blocks = [
        b for b in result.content_blocks if b["type"] == "tool_use"
    ]
    assert len(tool_use_blocks) == 2
    assert {b["id"] for b in tool_use_blocks} == {"toolu_01", "toolu_02"}


@pytest.mark.asyncio
async def test_run_agent_turn_increments_stats() -> None:
    client = _make_client()
    # Pre-condition: fresh stats.
    assert client.get_stats()["calls"] == 0
    assert client.get_stats()["tokens_in"] == 0
    assert client.get_stats()["tokens_out"] == 0

    fake = _fake_response(
        content=[_text_block("done")],
        stop_reason="end_turn",
        tokens_in=100,
        tokens_out=50,
    )
    client.client.messages.create = AsyncMock(return_value=fake)

    await client.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )

    stats = client.get_stats()
    assert stats["calls"] == 1
    assert stats["tokens_in"] == 100
    assert stats["tokens_out"] == 50
    assert stats["errors"] == 0
    assert stats["fallback_uses"] == 0


@pytest.mark.asyncio
async def test_run_agent_turn_surfaces_stop_reason() -> None:
    client = _make_client()
    fake = _fake_response(
        content=[_tool_use_block(id="toolu_1", name="foo", input={})],
        stop_reason="tool_use",
    )
    client.client.messages.create = AsyncMock(return_value=fake)

    result = await client.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )

    assert result.stop_reason == "tool_use"


@pytest.mark.asyncio
async def test_run_agent_turn_respects_model_override() -> None:
    client = _make_client()
    fake = _fake_response(content=[_text_block("ok")])
    create_mock = AsyncMock(return_value=fake)
    client.client.messages.create = create_mock

    override = "claude-some-override"
    result = await client.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
        model=override,
    )

    kwargs = create_mock.await_args.kwargs
    assert kwargs["model"] == override
    assert kwargs["model"] != client.model
    assert result.model_used == override


@pytest.mark.asyncio
async def test_run_agent_turn_returns_model_used() -> None:
    # No override -> model_used == self.model
    client = _make_client()
    fake = _fake_response(content=[_text_block("ok")])
    client.client.messages.create = AsyncMock(return_value=fake)

    result = await client.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )
    assert result.model_used == client.model

    # With override -> model_used reflects override
    client2 = _make_client()
    client2.client.messages.create = AsyncMock(return_value=fake)
    override = "claude-other-override"
    result2 = await client2.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
        model=override,
    )
    assert result2.model_used == override
