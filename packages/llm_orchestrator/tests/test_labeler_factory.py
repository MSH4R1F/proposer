"""Unit tests for ``labeler_factory`` (SHA-28 LLM labeling pipeline, Phase 4).

Covers ``LabelerModelSpec`` validation invariants and the
``build_labeler_client`` dispatcher that constructs the right concrete
``BaseLLMClient`` per provider.

The test patterns mirror ``test_openai_client.py``: mock the SDK at the
``client.responses.create`` / ``client.responses.parse`` boundary and
inject a pre-built ``AsyncOpenAI`` shim via the ``OpenAIClient(client=...)``
back door. Anthropic tests poke at the ``ClaudeClient.client`` attribute
directly since the constructor builds an ``AsyncAnthropic`` whose presence
we don't actually need to exercise.

Provider independence (Codex finding [4]): the dispatcher must not delegate
to ``get_llm_client(LLMRole.EXTRACTION)`` — that role is configured via env
vars and cannot prove provider independence at construction time. We assert
this indirectly by feeding two specs in the same call sequence and checking
the concrete types differ.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ValidationError

from ..clients._schema import strict_json_schema
from ..clients.base import BaseLLMClient
from ..clients.claude_client import ClaudeClient
from ..clients.labeler_factory import LabelerModelSpec, build_labeler_client
from ..clients.openai_client import OpenAIClient


# ---------------------------------------------------------------------------
# LabelerModelSpec
# ---------------------------------------------------------------------------


class TestLabelerModelSpec:
    def test_anthropic_spec_round_trips(self) -> None:
        spec = LabelerModelSpec(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        assert spec.provider == "anthropic"
        assert spec.model == "claude-sonnet-4-20250514"
        assert spec.api_version is None
        # OpenAI-only fields default to None / False on Anthropic specs.
        assert spec.reasoning_effort is None
        assert spec.text_verbosity is None
        assert spec.store is False

        # Round-trip through model_dump / model_validate.
        round_tripped = LabelerModelSpec.model_validate(spec.model_dump())
        assert round_tripped == spec

    def test_openai_spec_round_trips_with_optional_controls(self) -> None:
        spec = LabelerModelSpec(
            provider="openai",
            model="gpt-5.5",
            api_version="2026-04-01",
            reasoning_effort="medium",
            text_verbosity="low",
        )
        assert spec.provider == "openai"
        assert spec.model == "gpt-5.5"
        assert spec.api_version == "2026-04-01"
        assert spec.reasoning_effort == "medium"
        assert spec.text_verbosity == "low"
        assert spec.store is False

        round_tripped = LabelerModelSpec.model_validate(spec.model_dump())
        assert round_tripped == spec

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValidationError):
            LabelerModelSpec(provider="palm", model="bison-001")  # type: ignore[arg-type]

    def test_rejects_store_true_at_construction(self) -> None:
        # Privacy invariant — mirrors the OpenAIClient.__init__ rule. Reject
        # at the spec layer too so a misconfigured run sheet fails fast,
        # before any client is built.
        with pytest.raises(ValidationError, match="store"):
            LabelerModelSpec(provider="openai", model="gpt-5.5", store=True)

    def test_rejects_empty_model(self) -> None:
        with pytest.raises(ValidationError):
            LabelerModelSpec(provider="anthropic", model="")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            LabelerModelSpec(  # type: ignore[call-arg]
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                unknown_field="oops",
            )


# ---------------------------------------------------------------------------
# build_labeler_client
# ---------------------------------------------------------------------------


def _api_keys() -> Dict[str, str]:
    return {"anthropic": "test-anthropic-key", "openai": "test-openai-key"}


class TestBuildLabelerClient:
    def test_anthropic_spec_returns_claude_client(self) -> None:
        spec = LabelerModelSpec(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        client = build_labeler_client(spec, api_keys=_api_keys())

        assert isinstance(client, ClaudeClient)
        assert isinstance(client, BaseLLMClient)
        assert client.model == "claude-sonnet-4-20250514"

    def test_openai_spec_returns_openai_client_with_store_false(self) -> None:
        spec = LabelerModelSpec(
            provider="openai",
            model="gpt-5.5",
            reasoning_effort="medium",
            text_verbosity="low",
        )
        client = build_labeler_client(spec, api_keys=_api_keys())

        assert isinstance(client, OpenAIClient)
        assert isinstance(client, BaseLLMClient)
        assert client.model == "gpt-5.5"
        # Privacy invariant flows through to the constructed client.
        assert client.store is False
        assert client.reasoning_effort == "medium"
        assert client.text_verbosity == "low"

    def test_dual_provider_independence(self) -> None:
        """Two specs with different providers in one call sequence yield
        distinct concrete types, distinct instances, and no shared state.

        This is the core Codex finding [4] guard — the role-keyed factory
        cannot prove provider independence because it reads from a single
        ``LLMConfig`` instance whose env vars resolve to one provider per
        role at boot time.
        """
        spec_a = LabelerModelSpec(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        spec_b = LabelerModelSpec(provider="openai", model="gpt-5.5")

        client_a = build_labeler_client(spec_a, api_keys=_api_keys())
        client_b = build_labeler_client(spec_b, api_keys=_api_keys())

        assert type(client_a) is not type(client_b)
        assert client_a is not client_b
        assert isinstance(client_a, ClaudeClient)
        assert isinstance(client_b, OpenAIClient)
        # Distinct underlying SDK clients (no shared mutable state).
        assert client_a.client is not client_b.client

    def test_missing_api_key_raises(self) -> None:
        spec = LabelerModelSpec(provider="openai", model="gpt-5.5")
        with pytest.raises(KeyError):
            build_labeler_client(spec, api_keys={"anthropic": "x"})


# ---------------------------------------------------------------------------
# Integration: OpenAIClient.generate_structured through _schema.strict_json_schema
# ---------------------------------------------------------------------------


class _Person(BaseModel):
    """Minimal model for the strict-schema rewrite happy path.

    Mirrors ``Person`` in test_openai_client.py — no ``Field(ge=...)``
    constraints because strict mode rejects ``minimum``.
    """

    name: str
    age: int


def _text_part(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="output_text", text=text)


def _output_message(parts: List[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(type="message", role="assistant", content=parts)


def _usage(*, tokens_in: int = 50, tokens_out: int = 25) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        input_tokens_details=None,
        output_tokens_details=None,
    )


def _response(*, output: List[SimpleNamespace], output_parsed: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        output=output,
        status="completed",
        incomplete_details=None,
        error=None,
        usage=_usage(),
        output_parsed=output_parsed,
        output_text=None,
    )


@pytest.mark.asyncio
async def test_openai_labeler_generate_structured_through_strict_schema() -> None:
    """End-to-end exercise: a built OpenAI labeler client runs
    ``generate_structured`` with a Pydantic model, and the strict-schema
    rewriter accepts it on the manual-fallback path.

    We force the ``responses.parse`` call to fail with a "text_format not
    supported" error so the manual ``responses.create`` + JSON-schema
    fallback fires, which is the path that calls ``strict_json_schema``.
    """
    spec = LabelerModelSpec(provider="openai", model="gpt-5.5")
    client = build_labeler_client(spec, api_keys=_api_keys())

    # Sanity-check the rewriter directly first — gives a clearer failure
    # if the schema shape changes upstream.
    schema = strict_json_schema(_Person)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"].keys()) == {"name", "age"}
    assert sorted(schema["required"]) == ["age", "name"]

    # Now wire fake SDK methods. Replace the live AsyncOpenAI instance with
    # a SimpleNamespace shim — same trick OpenAIClient tests use.
    fake_responses = SimpleNamespace(
        create=AsyncMock(),
        parse=AsyncMock(),
    )
    client.client = SimpleNamespace(responses=fake_responses)  # type: ignore[assignment]

    # Force fallback to manual json_schema path by raising a 400 from parse.
    import httpx
    from openai import APIStatusError

    response_400 = httpx.Response(
        status_code=400,
        request=httpx.Request("POST", "https://api.openai.com/x"),
    )
    parse_err = APIStatusError(
        "Model gpt-5.5 does not support text_format / structured outputs",
        response=response_400,
        body=None,
    )
    parse_err.status_code = 400  # type: ignore[attr-defined]
    fake_responses.parse.side_effect = parse_err

    fake_responses.create.return_value = _response(
        output=[_output_message([_text_part('{"name":"Ada","age":36}')])],
    )

    result = await client.generate_structured(
        [{"role": "user", "content": "extract"}],
        system_prompt="parse",
        response_model=_Person,
        max_tokens=128,
    )

    assert isinstance(result, _Person)
    assert result.name == "Ada"
    assert result.age == 36

    # The manual fallback path embeds the strict-rewritten schema in the
    # request — assert the rewriter actually ran end-to-end.
    fake_responses.create.assert_awaited_once()
    create_kwargs = fake_responses.create.call_args.kwargs
    text_block = create_kwargs["text"]
    assert text_block["format"]["type"] == "json_schema"
    assert text_block["format"]["strict"] is True
    sent_schema = text_block["format"]["schema"]
    assert sent_schema["type"] == "object"
    assert sent_schema["additionalProperties"] is False
    assert set(sent_schema["properties"].keys()) == {"name", "age"}
