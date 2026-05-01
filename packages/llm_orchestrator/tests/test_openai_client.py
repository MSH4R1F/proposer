"""Unit tests for :class:`OpenAIClient` (SHA-114 Task 3).

Covers ``generate`` + ``generate_structured`` against the OpenAI Responses
API. All tests mock the SDK at the ``client.responses.create`` /
``client.responses.parse`` boundary — no live API calls.

Test plan mirrors the 16 cases in the Task 3 prompt (happy path, multi-text
extraction, structured-parse path, manual JSON-schema fallback, refusal,
incomplete, rate-limit + fallback, transient 5xx + retry, persistent error,
structured validation retry, structured validation persistent failure,
cached/reasoning token tracking, tiered cost calc, flat cost calc, unknown
model cost = None, reset_stats).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field

from ..clients import _pricing
from ..clients.exceptions import (
    LLMAPIError,
    LLMIncompleteResponseError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMStructuredOutputError,
)
from ..clients.openai_client import OpenAIClient


# ---------------------------------------------------------------------------
# Fake Responses-API object builders
# ---------------------------------------------------------------------------


def _text_part(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="output_text", text=text)


def _refusal_part(refusal: str) -> SimpleNamespace:
    return SimpleNamespace(type="refusal", refusal=refusal)


def _output_message(parts: List[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(type="message", role="assistant", content=parts)


def _usage(
    *,
    tokens_in: int = 100,
    tokens_out: int = 50,
    cached: Optional[int] = None,
    reasoning: Optional[int] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        input_tokens_details=(
            SimpleNamespace(cached_tokens=cached) if cached is not None else None
        ),
        output_tokens_details=(
            SimpleNamespace(reasoning_tokens=reasoning) if reasoning is not None else None
        ),
    )


def _response(
    *,
    output: List[SimpleNamespace],
    status: str = "completed",
    incomplete_details: Optional[SimpleNamespace] = None,
    usage: Optional[SimpleNamespace] = None,
    output_parsed: Any = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        output=output,
        status=status,
        incomplete_details=incomplete_details,
        error=None,
        usage=usage if usage is not None else _usage(),
        output_parsed=output_parsed,
        output_text=None,
    )


def _make_client(**overrides: Any) -> OpenAIClient:
    """Build an OpenAIClient whose SDK methods are AsyncMocks ready to override.

    ``client.responses.create`` and ``client.responses.parse`` are
    pre-installed as ``AsyncMock`` so individual tests just assign
    ``return_value``/``side_effect``.
    """
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


def _fake_rate_limit_error() -> RateLimitError:
    """Construct a minimal ``RateLimitError`` (its ctor wants an httpx.Response)."""
    response = httpx.Response(
        status_code=429, request=httpx.Request("POST", "https://api.openai.com/x")
    )
    return RateLimitError("rate limited", response=response, body=None)


def _fake_5xx_error(status: int = 503) -> APIStatusError:
    response = httpx.Response(
        status_code=status, request=httpx.Request("POST", "https://api.openai.com/x")
    )
    return APIStatusError("server error", response=response, body=None)


# ---------------------------------------------------------------------------
# 1. generate happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_happy_path_forwards_kwargs() -> None:
    client = _make_client(reasoning_effort="medium", text_verbosity="low")
    fake = _response(output=[_output_message([_text_part("hello world")])])
    client.client.responses.create.return_value = fake

    messages = [{"role": "user", "content": "hi"}]
    text = await client.generate(messages, system_prompt="be helpful", max_tokens=512)

    assert text == "hello world"
    client.client.responses.create.assert_awaited_once()
    kwargs = client.client.responses.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["instructions"] == "be helpful"
    assert kwargs["input"] == [{"role": "user", "content": "hi"}]
    assert kwargs["max_output_tokens"] == 512
    assert kwargs["store"] is False
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert kwargs["text"] == {"verbosity": "low"}
    # Privacy invariant.
    assert "previous_response_id" not in kwargs


@pytest.mark.asyncio
async def test_generate_omits_reasoning_and_text_when_unset() -> None:
    client = _make_client()  # reasoning_effort=None, text_verbosity=None
    fake = _response(output=[_output_message([_text_part("ok")])])
    client.client.responses.create.return_value = fake

    await client.generate([{"role": "user", "content": "hi"}], system_prompt="sys")

    kwargs = client.client.responses.create.call_args.kwargs
    assert "reasoning" not in kwargs
    assert "text" not in kwargs


# ---------------------------------------------------------------------------
# 2. generate extracts text from multi-part output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_concatenates_multiple_text_parts() -> None:
    client = _make_client()
    fake = _response(
        output=[
            _output_message([_text_part("part one "), _text_part("part two")]),
        ],
    )
    client.client.responses.create.return_value = fake

    text = await client.generate([{"role": "user", "content": "x"}], system_prompt="s")
    assert text == "part one part two"


# ---------------------------------------------------------------------------
# 3. generate_structured via responses.parse (SDK path)
# ---------------------------------------------------------------------------


class Person(BaseModel):
    """Test model — kept simple so ``strict_json_schema`` accepts it.

    ``Field(ge=...)`` is intentionally avoided because strict mode rejects
    ``minimum`` (see ``clients/_schema.py`` whitelist).
    """

    name: str
    age: int


@pytest.mark.asyncio
async def test_generate_structured_uses_responses_parse() -> None:
    client = _make_client()
    parsed = Person(name="Ada", age=36)
    fake = _response(
        output=[_output_message([_text_part('{"name":"Ada","age":36}')])],
        output_parsed=parsed,
    )
    client.client.responses.parse.return_value = fake

    result = await client.generate_structured(
        [{"role": "user", "content": "extract"}],
        system_prompt="parse",
        response_model=Person,
        max_tokens=256,
    )
    assert isinstance(result, Person)
    assert result.name == "Ada"
    assert result.age == 36

    client.client.responses.parse.assert_awaited_once()
    kwargs = client.client.responses.parse.call_args.kwargs
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["instructions"] == "parse"
    assert kwargs["input"] == [{"role": "user", "content": "extract"}]
    assert kwargs["text_format"] is Person
    assert kwargs["max_output_tokens"] == 256
    assert kwargs["store"] is False


# ---------------------------------------------------------------------------
# 4. generate_structured fallback to manual text.format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_structured_falls_back_to_manual_json_schema() -> None:
    """When ``responses.parse`` reports the model rejects ``text_format``,
    the client falls back to ``responses.create`` with a strict json_schema.
    """
    client = _make_client()
    # Simulate a 400 from parse with a hint that text_format is unsupported.
    response_400 = httpx.Response(
        status_code=400,
        request=httpx.Request("POST", "https://api.openai.com/x"),
    )
    parse_err = APIStatusError(
        "Model gpt-foo does not support text_format / structured outputs",
        response=response_400,
        body=None,
    )
    # Override status_code so it isn't caught as 5xx.
    parse_err.status_code = 400
    client.client.responses.parse.side_effect = parse_err

    fake_create = _response(
        output=[_output_message([_text_part('{"name":"Grace","age":85}')])],
    )
    client.client.responses.create.return_value = fake_create

    result = await client.generate_structured(
        [{"role": "user", "content": "extract"}],
        system_prompt="parse",
        response_model=Person,
        max_tokens=256,
    )
    assert isinstance(result, Person)
    assert result.name == "Grace"
    assert result.age == 85

    client.client.responses.create.assert_awaited_once()
    kwargs = client.client.responses.create.call_args.kwargs
    text_block = kwargs["text"]
    assert text_block["format"]["type"] == "json_schema"
    assert text_block["format"]["strict"] is True
    assert text_block["format"]["name"] == "Person"
    schema = text_block["format"]["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"].keys()) == {"name", "age"}


# ---------------------------------------------------------------------------
# 5. Refusal handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_raises_on_refusal_and_does_not_fall_back() -> None:
    client = _make_client(fallback_model="gpt-5.4")
    fake = _response(
        output=[_output_message([_refusal_part("I cannot help with that.")])],
    )
    client.client.responses.create.return_value = fake

    with pytest.raises(LLMRefusalError, match="I cannot help"):
        await client.generate([{"role": "user", "content": "x"}], system_prompt="s")

    # Exactly one call — no fallback attempted on refusal.
    assert client.client.responses.create.await_count == 1
    stats = client.get_stats()
    assert stats["errors"] == 1
    assert stats["fallback_uses"] == 0


# ---------------------------------------------------------------------------
# 6. Incomplete handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_raises_on_incomplete_response_with_token_hint() -> None:
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("partial...")])],
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        usage=_usage(tokens_in=42, tokens_out=4096),
    )
    client.client.responses.create.return_value = fake

    with pytest.raises(LLMIncompleteResponseError) as exc_info:
        await client.generate([{"role": "user", "content": "x"}], system_prompt="s")

    msg = str(exc_info.value)
    assert "max_output_tokens" in msg
    # Caller should be able to see tokens_out so they can retune.
    assert "4096" in msg


# ---------------------------------------------------------------------------
# 7. Rate-limit + fallback model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_triggers_fallback_model() -> None:
    client = _make_client(fallback_model="gpt-5.4")

    fallback_response = _response(output=[_output_message([_text_part("from fallback")])])
    client.client.responses.create.side_effect = [
        _fake_rate_limit_error(),
        fallback_response,
    ]

    text = await client.generate(
        [{"role": "user", "content": "x"}], system_prompt="s"
    )

    assert text == "from fallback"
    assert client.client.responses.create.await_count == 2
    # Second call must use the fallback model.
    second_kwargs = client.client.responses.create.call_args_list[1].kwargs
    assert second_kwargs["model"] == "gpt-5.4"
    stats = client.get_stats()
    assert stats["fallback_uses"] == 1
    # No error counted because the fallback succeeded.
    assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_rate_limit_without_fallback_raises_neutral_error() -> None:
    client = _make_client(fallback_model=None)
    client.client.responses.create.side_effect = _fake_rate_limit_error()

    with pytest.raises(LLMRateLimitError):
        await client.generate(
            [{"role": "user", "content": "x"}], system_prompt="s"
        )
    stats = client.get_stats()
    assert stats["errors"] == 1
    assert stats["fallback_uses"] == 0


# ---------------------------------------------------------------------------
# 8. Transient 5xx + retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5xx_retried_with_backoff_eventual_success() -> None:
    client = _make_client(max_retries=3)
    success = _response(output=[_output_message([_text_part("ok-eventually")])])
    client.client.responses.create.side_effect = [
        _fake_5xx_error(503),
        _fake_5xx_error(502),
        success,
    ]

    text = await client.generate(
        [{"role": "user", "content": "x"}], system_prompt="s"
    )
    assert text == "ok-eventually"
    assert client.client.responses.create.await_count == 3
    # No errors counted because we recovered.
    assert client.get_stats()["errors"] == 0


# ---------------------------------------------------------------------------
# 9. Persistent error after retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_5xx_raises_llm_api_error() -> None:
    client = _make_client(max_retries=3)
    client.client.responses.create.side_effect = [
        _fake_5xx_error(503),
        _fake_5xx_error(503),
        _fake_5xx_error(503),
        _fake_5xx_error(503),
    ]

    with pytest.raises(LLMAPIError):
        await client.generate(
            [{"role": "user", "content": "x"}], system_prompt="s"
        )
    assert client.client.responses.create.await_count == 3
    stats = client.get_stats()
    assert stats["errors"] == 1


# ---------------------------------------------------------------------------
# 10. Structured output validation failure → ONE retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_validation_failure_retries_once_and_succeeds() -> None:
    client = _make_client()
    bad_response = _response(
        output=[_output_message([_text_part("not json at all")])],
        output_parsed=None,
    )
    good_parsed = Person(name="Linus", age=54)
    good_response = _response(
        output=[_output_message([_text_part('{"name":"Linus","age":54}')])],
        output_parsed=good_parsed,
    )
    client.client.responses.parse.side_effect = [bad_response, good_response]

    result = await client.generate_structured(
        [{"role": "user", "content": "extract"}],
        system_prompt="parse",
        response_model=Person,
    )
    assert result.name == "Linus"
    # Two parse calls — one to fail, one to succeed after the repair message.
    assert client.client.responses.parse.await_count == 2

    # Second call should include an extra user message with repair text.
    second_kwargs = client.client.responses.parse.call_args_list[1].kwargs
    second_input = second_kwargs["input"]
    assert len(second_input) == 2
    assert second_input[-1]["role"] == "user"
    assert "schema validation" in second_input[-1]["content"].lower()


# ---------------------------------------------------------------------------
# 11. Structured persistent validation failure → typed error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_persistent_validation_failure_raises_typed() -> None:
    client = _make_client()
    bad = _response(
        output=[_output_message([_text_part("still not json")])],
        output_parsed=None,
    )
    client.client.responses.parse.side_effect = [bad, bad]

    with pytest.raises(LLMStructuredOutputError):
        await client.generate_structured(
            [{"role": "user", "content": "extract"}],
            system_prompt="parse",
            response_model=Person,
        )
    assert client.client.responses.parse.await_count == 2
    assert client.get_stats()["errors"] == 1


# ---------------------------------------------------------------------------
# 12. Stats: cached + reasoning tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_records_cached_and_reasoning_tokens() -> None:
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("hi")])],
        usage=_usage(tokens_in=200, tokens_out=80, cached=120, reasoning=40),
    )
    client.client.responses.create.return_value = fake

    await client.generate([{"role": "user", "content": "x"}], system_prompt="s")
    stats = client.get_stats()
    assert stats["tokens_in"] == 200
    assert stats["tokens_out"] == 80
    assert stats["cached_tokens_in"] == 120
    assert stats["reasoning_tokens_out"] == 40


@pytest.mark.asyncio
async def test_stats_defaults_cached_reasoning_to_zero_when_absent() -> None:
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("hi")])],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            input_tokens_details=None,
            output_tokens_details=None,
        ),
    )
    client.client.responses.create.return_value = fake

    await client.generate([{"role": "user", "content": "x"}], system_prompt="s")
    stats = client.get_stats()
    assert stats["cached_tokens_in"] == 0
    assert stats["reasoning_tokens_out"] == 0


# ---------------------------------------------------------------------------
# 13. Cost calc — tiered (gpt-5.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_calc_tiered_model_uses_short_context_rates() -> None:
    client = _make_client(model="gpt-5.5")
    fake = _response(
        output=[_output_message([_text_part("hi")])],
        usage=_usage(tokens_in=1000, tokens_out=500),
    )
    client.client.responses.create.return_value = fake

    await client.generate([{"role": "user", "content": "x"}], system_prompt="s")
    stats = client.get_stats()
    expected = (1000 * 2.5 + 500 * 15.0) / 1_000_000
    assert stats["estimated_cost_usd"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 14. Cost calc — flat (gpt-5.4-mini)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_calc_flat_model() -> None:
    client = _make_client(model="gpt-5.4-mini")
    fake = _response(
        output=[_output_message([_text_part("hi")])],
        usage=_usage(tokens_in=1000, tokens_out=500),
    )
    client.client.responses.create.return_value = fake

    await client.generate([{"role": "user", "content": "x"}], system_prompt="s")
    stats = client.get_stats()
    expected = (1000 * 0.375 + 500 * 2.25) / 1_000_000
    assert stats["estimated_cost_usd"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 15. Cost calc — unknown model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_calc_unknown_model_returns_none() -> None:
    # Reset dedupe set so the warning side-effect doesn't get suppressed
    # by an earlier test run in the same session (defensive).
    _pricing._warned_missing_pricing.clear()

    client = _make_client(model="totally-fake-model-xyz")
    fake = _response(output=[_output_message([_text_part("hi")])])
    client.client.responses.create.return_value = fake

    await client.generate([{"role": "user", "content": "x"}], system_prompt="s")
    stats = client.get_stats()
    assert stats["estimated_cost_usd"] is None
    # Other fields still populated.
    assert stats["provider"] == "openai"
    assert stats["model"] == "totally-fake-model-xyz"


# ---------------------------------------------------------------------------
# 16. Reset stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_stats_zeros_every_field() -> None:
    client = _make_client()
    fake = _response(
        output=[_output_message([_text_part("hi")])],
        usage=_usage(tokens_in=100, tokens_out=50, cached=30, reasoning=10),
    )
    client.client.responses.create.return_value = fake
    await client.generate([{"role": "user", "content": "x"}], system_prompt="s")

    pre = client.get_stats()
    assert pre["calls"] == 1
    assert pre["tokens_in"] == 100

    client.reset_stats()
    post = client.get_stats()
    for key in (
        "calls",
        "tokens_in",
        "tokens_out",
        "cached_tokens_in",
        "reasoning_tokens_out",
        "errors",
        "fallback_uses",
    ):
        assert post[key] == 0, f"{key} not zeroed: {post[key]}"
    # Provider/model are not reset.
    assert post["provider"] == "openai"
    assert post["model"] == "gpt-5.5"


# ---------------------------------------------------------------------------
# Bonus: BaseLLMClient subclassing contract
# ---------------------------------------------------------------------------


def test_openai_client_implements_base_llm_client() -> None:
    """Sanity: every abstract method is implemented (instantiation would fail otherwise)."""
    from ..clients.base import BaseLLMClient

    client = _make_client()
    assert isinstance(client, BaseLLMClient)
