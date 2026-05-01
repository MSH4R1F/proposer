"""Tests for ``OpenAIClient.run_agent_turn`` (SHA-114 Task 4).

Validates:
- Internal content_blocks ⇄ Responses Items conversion (esp. function_call /
  function_call_output ``call_id`` plumbing and ``arguments`` JSON-string
  encoding).
- Stop-reason normalisation (``tool_use`` wins over ``end_turn``;
  ``incomplete`` maps to ``"max_tokens"`` rather than raising).
- Refusal during agent_turn raises (no fallback) and ``failed`` raises
  ``LLMAPIError``.
- Tools kwarg is forwarded; ``store=False`` and no ``previous_response_id``
  are preserved.
- ``isinstance(client, AgentTurnClient)`` succeeds.
- Golden mediator-tool contract: ClaudeClient and OpenAIClient produce
  semantically equivalent ``AgentTurnResponse`` shapes for the same
  scripted prompt + ``MEDIATOR_TOOLS``.

All SDK calls are mocked at the ``client.responses.create`` boundary —
no live API calls.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from ..agent_loop.loop import AgentTurnClient, AgentTurnResponse
from ..clients.claude_client import ClaudeClient
from ..clients.exceptions import (
    LLMAPIError,
    LLMRefusalError,
    LLMStructuredOutputError,
)
from ..clients.openai_client import OpenAIClient
from ..tools.mediator import MEDIATOR_TOOLS


# ---------------------------------------------------------------------------
# Fake Responses-API object builders
# ---------------------------------------------------------------------------


def _text_part(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="output_text", text=text)


def _refusal_part(refusal: str) -> SimpleNamespace:
    return SimpleNamespace(type="refusal", refusal=refusal)


def _output_message(parts: List[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(type="message", role="assistant", content=parts)


def _function_call_item(
    *, call_id: str, name: str, arguments: str
) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def _usage(
    *,
    tokens_in: int = 100,
    tokens_out: int = 50,
) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        input_tokens_details=None,
        output_tokens_details=None,
    )


def _response(
    *,
    output: List[SimpleNamespace],
    status: str = "completed",
    incomplete_details: Optional[SimpleNamespace] = None,
    usage: Optional[SimpleNamespace] = None,
    model: Optional[str] = "gpt-5.5",
) -> SimpleNamespace:
    return SimpleNamespace(
        output=output,
        status=status,
        incomplete_details=incomplete_details,
        error=None,
        usage=usage if usage is not None else _usage(),
        output_text=None,
        model=model,
    )


def _make_client(**overrides: Any) -> OpenAIClient:
    fake_responses = SimpleNamespace(
        create=AsyncMock(),
        parse=AsyncMock(),
    )
    fake_sdk = SimpleNamespace(responses=fake_responses)

    defaults: Dict[str, Any] = dict(
        api_key="test-key",
        model="gpt-5.5",
        client=fake_sdk,
        retry_base_delay=0.0,
    )
    defaults.update(overrides)
    return OpenAIClient(**defaults)


# ---------------------------------------------------------------------------
# 1. Plain text response (no tools) → end_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_text_response_returns_end_turn() -> None:
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("hello world")])],
        usage=_usage(tokens_in=42, tokens_out=7),
    )
    client.client.responses.create.return_value = fake

    result = await client.run_agent_turn(
        system_prompt="be helpful",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )

    assert isinstance(result, AgentTurnResponse)
    assert result.stop_reason == "end_turn"
    assert result.content_blocks == [{"type": "text", "text": "hello world"}]
    assert result.tokens_in == 42
    assert result.tokens_out == 7
    assert result.model_used == "gpt-5.5"


# ---------------------------------------------------------------------------
# 2. Single function call → tool_use
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_function_call_becomes_tool_use_block() -> None:
    client = _make_client()
    args = {"tenant_min": 100, "tenant_max": 500, "landlord_min": 200}
    fake = _response(
        output=[
            _function_call_item(
                call_id="call_X",
                name="calculate_zopa",
                arguments=json.dumps(args),
            )
        ],
    )
    client.client.responses.create.return_value = fake

    result = await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "compute zopa"}],
        tool_schemas=[],
    )

    assert result.stop_reason == "tool_use"
    assert len(result.content_blocks) == 1
    block = result.content_blocks[0]
    assert block["type"] == "tool_use"
    assert block["id"] == "call_X"
    assert block["name"] == "calculate_zopa"
    # ``input`` must be a parsed dict, NOT a JSON string.
    assert block["input"] == args
    assert isinstance(block["input"], dict)


# ---------------------------------------------------------------------------
# 3. Multiple parallel function calls preserved in order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_parallel_function_calls_preserve_order() -> None:
    client = _make_client()
    fake = _response(
        output=[
            _function_call_item(
                call_id="call_A", name="alpha", arguments='{"x":1}'
            ),
            _function_call_item(
                call_id="call_B", name="beta", arguments='{"y":2}'
            ),
            _function_call_item(
                call_id="call_C", name="gamma", arguments='{"z":3}'
            ),
        ],
    )
    client.client.responses.create.return_value = fake

    result = await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )

    assert result.stop_reason == "tool_use"
    assert len(result.content_blocks) == 3
    assert [b["id"] for b in result.content_blocks] == [
        "call_A",
        "call_B",
        "call_C",
    ]
    assert [b["name"] for b in result.content_blocks] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert result.content_blocks[0]["input"] == {"x": 1}
    assert result.content_blocks[1]["input"] == {"y": 2}
    assert result.content_blocks[2]["input"] == {"z": 3}


# ---------------------------------------------------------------------------
# 4. Mixed text + function calls → tool_use wins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_text_and_function_call_stops_with_tool_use() -> None:
    client = _make_client()
    fake = _response(
        output=[
            _output_message([_text_part("Let me think...")]),
            _function_call_item(
                call_id="call_1",
                name="calculate_zopa",
                arguments='{"a":1}',
            ),
        ],
    )
    client.client.responses.create.return_value = fake

    result = await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )

    # Presence of a function_call wins regardless of text or status.
    assert result.stop_reason == "tool_use"
    types = [b["type"] for b in result.content_blocks]
    assert types == ["text", "tool_use"]
    assert result.content_blocks[0]["text"] == "Let me think..."
    assert result.content_blocks[1]["id"] == "call_1"


# ---------------------------------------------------------------------------
# 5. Tool-use round-trip: replay assistant tool_use + user tool_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_use_round_trip_emits_function_call_and_output_items() -> None:
    """The critical contract test: simulate the loop's behaviour where the
    second turn replays the assistant's tool_use plus a tool_result, and
    assert the OpenAI input items contain ``function_call`` and
    ``function_call_output`` Items in the right order with matching call_ids.
    """
    client = _make_client()

    # Turn 1: tool_use response.
    turn1 = _response(
        output=[
            _function_call_item(
                call_id="call_99",
                name="calculate_zopa",
                arguments='{"tenant_min":0,"tenant_max":500}',
            )
        ],
    )
    # Turn 2: end_turn after seeing the tool_result.
    turn2 = _response(output=[_output_message([_text_part("Final answer.")])])
    client.client.responses.create.side_effect = [turn1, turn2]

    # Turn 1 call.
    result1 = await client.run_agent_turn(
        system_prompt="sys",
        messages=[{"role": "user", "content": "do X"}],
        tool_schemas=[{"type": "function", "name": "calculate_zopa"}],
    )
    assert result1.stop_reason == "tool_use"
    tool_block = result1.content_blocks[0]
    assert tool_block["id"] == "call_99"

    # Turn 2 call — caller now appends the assistant tool_use replay and
    # the user's tool_result, exactly as ``AgentLoop.run`` does.
    messages_turn2 = [
        {"role": "user", "content": "do X"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_99",
                    "name": "calculate_zopa",
                    "input": {"tenant_min": 0, "tenant_max": 500},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_99",
                    "content": '{"zopa":[200,400]}',
                }
            ],
        },
    ]
    result2 = await client.run_agent_turn(
        system_prompt="sys",
        messages=messages_turn2,
        tool_schemas=[{"type": "function", "name": "calculate_zopa"}],
    )
    assert result2.stop_reason == "end_turn"

    # Inspect the second create call's ``input`` kwarg.
    second_kwargs = client.client.responses.create.call_args_list[1].kwargs
    items = second_kwargs["input"]
    # Expected: user message, function_call Item, function_call_output Item.
    assert len(items) == 3
    assert items[0] == {"role": "user", "content": "do X"}

    fc = items[1]
    assert fc["type"] == "function_call"
    assert fc["call_id"] == "call_99"
    assert fc["name"] == "calculate_zopa"
    # arguments MUST be a JSON string, not a dict.
    assert isinstance(fc["arguments"], str)
    assert json.loads(fc["arguments"]) == {
        "tenant_min": 0,
        "tenant_max": 500,
    }

    fco = items[2]
    assert fco["type"] == "function_call_output"
    assert fco["call_id"] == "call_99"
    assert fco["output"] == '{"zopa":[200,400]}'
    assert isinstance(fco["output"], str)


# ---------------------------------------------------------------------------
# 6. function_call_output Item shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_with_dict_content_serialised_to_string() -> None:
    """If tool_result.content is a dict (defensive — agent loop emits a
    string today), it must still be serialised to a JSON string so the
    Responses API gets a valid Item.
    """
    client = _make_client()
    fake = _response(output=[_output_message([_text_part("ok")])])
    client.client.responses.create.return_value = fake

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_Z",
                    "content": {"foo": "bar"},
                }
            ],
        }
    ]
    await client.run_agent_turn(
        system_prompt="s",
        messages=messages,
        tool_schemas=[],
    )

    items = client.client.responses.create.call_args.kwargs["input"]
    fco = items[0]
    assert fco["type"] == "function_call_output"
    assert fco["call_id"] == "call_Z"
    assert isinstance(fco["output"], str)
    assert json.loads(fco["output"]) == {"foo": "bar"}


# ---------------------------------------------------------------------------
# 7. function_call Item shape on assistant replay (arguments is JSON string)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assistant_tool_use_replay_arguments_is_json_string() -> None:
    client = _make_client()
    fake = _response(output=[_output_message([_text_part("ok")])])
    client.client.responses.create.return_value = fake

    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_PP",
                    "name": "do_thing",
                    "input": {"a": 1, "b": [2, 3]},
                }
            ],
        }
    ]
    await client.run_agent_turn(
        system_prompt="s",
        messages=messages,
        tool_schemas=[],
    )

    items = client.client.responses.create.call_args.kwargs["input"]
    assert len(items) == 1
    fc = items[0]
    assert fc["type"] == "function_call"
    assert fc["call_id"] == "call_PP"
    assert fc["name"] == "do_thing"
    # MUST be a JSON-encoded string.
    assert isinstance(fc["arguments"], str)
    assert json.loads(fc["arguments"]) == {"a": 1, "b": [2, 3]}


# ---------------------------------------------------------------------------
# 8. Malformed arguments JSON raises LLMStructuredOutputError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_function_call_arguments_raises_structured_error() -> None:
    client = _make_client()
    fake = _response(
        output=[
            _function_call_item(
                call_id="call_BAD",
                name="foo",
                arguments="{ broken json",
            )
        ],
    )
    client.client.responses.create.return_value = fake

    with pytest.raises(LLMStructuredOutputError) as exc_info:
        await client.run_agent_turn(
            system_prompt="s",
            messages=[{"role": "user", "content": "hi"}],
            tool_schemas=[],
        )
    assert "call_BAD" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 9. Incomplete (max_output_tokens) → graceful stop_reason="max_tokens"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incomplete_response_returns_max_tokens_stop_reason() -> None:
    """Unlike ``generate``, ``run_agent_turn`` must NOT raise on incomplete
    responses — the agent loop owns termination policy and should be allowed
    to surface whatever partial text the model produced.
    """
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("partial...")])],
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        usage=_usage(tokens_in=10, tokens_out=4096),
    )
    client.client.responses.create.return_value = fake

    result = await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )
    assert result.stop_reason == "max_tokens"
    assert result.content_blocks == [{"type": "text", "text": "partial..."}]


# ---------------------------------------------------------------------------
# 10. Failed status → LLMAPIError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_status_raises_llm_api_error() -> None:
    client = _make_client()
    fake = _response(
        output=[],
        status="failed",
    )
    fake.error = SimpleNamespace(message="something exploded")
    client.client.responses.create.return_value = fake

    with pytest.raises(LLMAPIError, match="something exploded"):
        await client.run_agent_turn(
            system_prompt="s",
            messages=[{"role": "user", "content": "hi"}],
            tool_schemas=[],
        )


# ---------------------------------------------------------------------------
# 11. Refusal during agent_turn raises (no fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refusal_raises_and_does_not_fall_back() -> None:
    client = _make_client(fallback_model="gpt-5.4")
    fake = _response(
        output=[_output_message([_refusal_part("I cannot help.")])],
    )
    client.client.responses.create.return_value = fake

    with pytest.raises(LLMRefusalError, match="I cannot help"):
        await client.run_agent_turn(
            system_prompt="s",
            messages=[{"role": "user", "content": "hi"}],
            tool_schemas=[],
        )

    assert client.client.responses.create.await_count == 1
    stats = client.get_stats()
    assert stats["fallback_uses"] == 0


# ---------------------------------------------------------------------------
# 12. Tools kwarg forwarded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_kwarg_forwarded_verbatim() -> None:
    client = _make_client()
    fake = _response(output=[_output_message([_text_part("ok")])])
    client.client.responses.create.return_value = fake

    schemas = [
        {
            "type": "function",
            "name": "do_thing",
            "description": "test",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=schemas,
    )
    kwargs = client.client.responses.create.call_args.kwargs
    assert kwargs["tools"] == schemas


# ---------------------------------------------------------------------------
# 13. Privacy invariants: store=False and no previous_response_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_privacy_invariants_preserved_in_agent_turn() -> None:
    client = _make_client()
    fake = _response(output=[_output_message([_text_part("ok")])])
    client.client.responses.create.return_value = fake

    await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )
    kwargs = client.client.responses.create.call_args.kwargs
    assert kwargs["store"] is False
    assert "previous_response_id" not in kwargs


# ---------------------------------------------------------------------------
# 14. Stats updated after a single run_agent_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_updated_after_single_agent_turn() -> None:
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("ok")])],
        usage=_usage(tokens_in=33, tokens_out=11),
    )
    client.client.responses.create.return_value = fake

    pre = client.get_stats()
    assert pre["calls"] == 0
    assert pre["tokens_in"] == 0

    result = await client.run_agent_turn(
        system_prompt="s",
        messages=[{"role": "user", "content": "hi"}],
        tool_schemas=[],
    )
    assert result.model_used == "gpt-5.5"

    post = client.get_stats()
    assert post["calls"] == 1
    assert post["tokens_in"] == 33
    assert post["tokens_out"] == 11
    assert post["errors"] == 0


# ---------------------------------------------------------------------------
# 15. isinstance(client, AgentTurnClient) — runtime_checkable Protocol
# ---------------------------------------------------------------------------


def test_openai_client_implements_agent_turn_client_protocol() -> None:
    client = _make_client()
    assert isinstance(client, AgentTurnClient)


# ---------------------------------------------------------------------------
# 16. Golden mediator-tool contract: ClaudeClient ≅ OpenAIClient
# ---------------------------------------------------------------------------


def _claude_text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _claude_tool_use_block(
    *, id: str, name: str, input: Dict[str, Any]
) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _claude_fake_response(
    *,
    content: List[SimpleNamespace],
    stop_reason: str = "tool_use",
    tokens_in: int = 100,
    tokens_out: int = 50,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out),
    )


@pytest.mark.asyncio
async def test_golden_mediator_tool_contract_parity_between_providers() -> None:
    """Same scripted mediator prompt + MEDIATOR_TOOLS → semantically
    equivalent AgentTurnResponse from both providers.

    We assert the *set* of (name, input) tuples matches and that
    stop_reason is identical. Block ordering may diverge between providers
    on parallel tool calls in the wild — the agent loop dispatches each
    block sequentially anyway — so set-equality is the right invariant.
    """
    system_prompt = "You are a mediator."
    messages = [{"role": "user", "content": "Compute the ZOPA and counter range."}]

    # Tool calls both providers will surface this turn.
    expected_calls = [
        (
            "calculate_zopa",
            {
                "tenant_min_acceptable_gbp": 100,
                "tenant_max_acceptable_gbp": 500,
                "landlord_min_acceptable_gbp": 200,
                "landlord_max_acceptable_gbp": 600,
            },
        ),
        (
            "calculate_counter_range",
            {
                "current_offer_gbp": 300,
                "predicted_award_gbp": 350,
                "predicted_award_low_gbp": 250,
                "predicted_award_high_gbp": 450,
                "moving_toward": "midpoint",
            },
        ),
    ]

    # ---- ClaudeClient leg --------------------------------------------------
    claude = ClaudeClient(api_key="test-key")
    claude_fake = _claude_fake_response(
        content=[
            _claude_text_block("Running tools."),
            _claude_tool_use_block(
                id="toolu_a", name=expected_calls[0][0], input=expected_calls[0][1]
            ),
            _claude_tool_use_block(
                id="toolu_b", name=expected_calls[1][0], input=expected_calls[1][1]
            ),
        ],
        stop_reason="tool_use",
    )
    claude.client.messages.create = AsyncMock(return_value=claude_fake)
    claude_result = await claude.run_agent_turn(
        system_prompt=system_prompt,
        messages=messages,
        tool_schemas=MEDIATOR_TOOLS.anthropic_schemas(),
    )

    # ---- OpenAIClient leg --------------------------------------------------
    openai_client = _make_client()
    # Note: OpenAI emits parallel function_calls in (potentially) different
    # order. We deliberately use a different order here to prove the parity
    # check is robust to that.
    openai_fake = _response(
        output=[
            _function_call_item(
                call_id="call_b",
                name=expected_calls[1][0],
                arguments=json.dumps(expected_calls[1][1]),
            ),
            _function_call_item(
                call_id="call_a",
                name=expected_calls[0][0],
                arguments=json.dumps(expected_calls[0][1]),
            ),
        ],
    )
    openai_client.client.responses.create.return_value = openai_fake
    openai_result = await openai_client.run_agent_turn(
        system_prompt=system_prompt,
        messages=messages,
        tool_schemas=MEDIATOR_TOOLS.openai_response_tools(),
    )

    # ---- Parity assertions -------------------------------------------------
    assert claude_result.stop_reason == openai_result.stop_reason == "tool_use"

    def _tool_use_set(blocks: List[Dict[str, Any]]) -> set:
        return {
            (b["name"], json.dumps(b["input"], sort_keys=True))
            for b in blocks
            if b.get("type") == "tool_use"
        }

    claude_calls = _tool_use_set(claude_result.content_blocks)
    openai_calls = _tool_use_set(openai_result.content_blocks)
    assert claude_calls == openai_calls
    # And the expected set, just to anchor the test against drift.
    expected_set = {
        (name, json.dumps(args, sort_keys=True))
        for name, args in expected_calls
    }
    assert claude_calls == expected_set
