"""Tests for ``Tool.to_openai_response_tool`` and
``ToolSet.openai_response_tools`` (SHA-114 step 2 / spec §6.3).

The OpenAI Responses API expects a different tool envelope than Anthropic.
This module asserts:

- Tool emits the exact OpenAI Responses ``function`` shape.
- ToolSet emits a list of those shapes.
- The Anthropic schema methods are still present and produce a different
  shape — both providers coexist (per spec §16.5).
- ``MEDIATOR_TOOLS`` round-trips cleanly through both methods.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel

from llm_orchestrator.agent_loop.context import ToolContext
from llm_orchestrator.agent_loop.tool import Tool, tool
from llm_orchestrator.tools.mediator import MEDIATOR_TOOLS


# ---------------------------------------------------------------------------
# A minimal tool fixture defined locally so the test does not depend on the
# mediator suite's internals.
# ---------------------------------------------------------------------------


class _AddArgs(BaseModel):
    a: int
    b: int


@tool(description="Add two integers and return the sum.")
def _add(ctx: ToolContext, args: _AddArgs) -> Dict[str, int]:
    return {"sum": args.a + args.b}


def test_to_openai_response_tool_top_level_shape() -> None:
    payload = _add.to_openai_response_tool()

    # Exact top-level keys — no Anthropic-isms.
    assert payload["type"] == "function"
    assert payload["name"] == "_add"
    assert payload["description"] == "Add two integers and return the sum."
    assert "parameters" in payload
    assert "input_schema" not in payload  # That's Anthropic.

    parameters: Dict[str, Any] = payload["parameters"]
    assert parameters["type"] == "object"
    assert parameters["additionalProperties"] is False
    assert set(parameters["required"]) == {"a", "b"}


def test_to_openai_response_tool_does_not_mutate_anthropic_shape() -> None:
    """Calling the OpenAI shape getter must NOT alter the Anthropic shape."""
    anthropic_before = _add.to_anthropic_schema()
    _ = _add.to_openai_response_tool()
    anthropic_after = _add.to_anthropic_schema()
    assert anthropic_before == anthropic_after
    # And the Anthropic schema is wrapped under input_schema, not parameters.
    assert "input_schema" in anthropic_before
    assert "parameters" not in anthropic_before


# ---------------------------------------------------------------------------
# ToolSet.openai_response_tools()
# ---------------------------------------------------------------------------


def test_toolset_openai_response_tools_emits_one_per_tool() -> None:
    schemas = MEDIATOR_TOOLS.openai_response_tools()
    assert isinstance(schemas, list)
    assert len(schemas) == len(MEDIATOR_TOOLS.tools)
    names = {s["name"] for s in schemas}
    assert names == {t.name for t in MEDIATOR_TOOLS.tools}


def test_toolset_openai_response_tools_each_entry_is_function_typed() -> None:
    for entry in MEDIATOR_TOOLS.openai_response_tools():
        assert entry["type"] == "function"
        assert "name" in entry
        assert "description" in entry
        params = entry["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False


def test_toolset_anthropic_schemas_still_works_alongside_openai() -> None:
    """Both methods must coexist (spec §16.5: keep existing API)."""
    a = MEDIATOR_TOOLS.anthropic_schemas()
    o = MEDIATOR_TOOLS.openai_response_tools()
    assert len(a) == len(o)
    # Different shapes.
    for a_entry, o_entry in zip(a, o):
        assert a_entry["name"] == o_entry["name"]
        assert "input_schema" in a_entry
        assert "parameters" in o_entry
        assert "type" not in a_entry  # Anthropic doesn't tag with type.
        assert o_entry["type"] == "function"


# ---------------------------------------------------------------------------
# MEDIATOR_TOOLS args-model audit (none of these have constraints today, so
# strict_json_schema must not raise).
# ---------------------------------------------------------------------------


def test_mediator_tools_args_models_pass_strict_schema() -> None:
    """Each MEDIATOR_TOOLS args model must round-trip strict_json_schema
    cleanly. None of them currently use ge/le/min_length/etc., so this test
    asserts the helper succeeds (no LLMStructuredOutputError)."""
    from llm_orchestrator.clients._schema import strict_json_schema

    for t in MEDIATOR_TOOLS.tools:
        # Should not raise.
        schema = strict_json_schema(t.args_model)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
