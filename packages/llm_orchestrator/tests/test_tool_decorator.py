"""Tests for @tool decorator, Tool, ToolSet, and ToolResult (step 3)."""
from __future__ import annotations

import asyncio
from typing import Optional

import pytest
from pydantic import BaseModel

from ..agent_loop.context import ToolContext
from ..agent_loop.tool import (
    Tool,
    ToolResult,
    ToolSet,
    UnknownToolError,
    tool,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ctx() -> ToolContext:
    return ToolContext()


# ---------------------------------------------------------------------------
# 1. Sync tool builds correct schema
# ---------------------------------------------------------------------------

class AddArgs(BaseModel):
    x: int
    y: int
    label: Optional[str] = None  # has default → not in required


@tool(name="add", description="Add two integers.")
def add(ctx: ToolContext, args: AddArgs) -> dict:
    return {"sum": args.x + args.y}


def test_to_anthropic_schema_sync_tool() -> None:
    schema = add.to_anthropic_schema()
    assert schema["name"] == "add"
    assert schema["description"] == "Add two integers."
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    assert "x" in input_schema["properties"]
    assert "y" in input_schema["properties"]
    # 'label' has a default so it should NOT appear in required
    assert "x" in input_schema["required"]
    assert "y" in input_schema["required"]
    assert "label" not in input_schema.get("required", [])
    # top-level title and $defs must be absent
    assert "title" not in input_schema
    assert "$defs" not in input_schema


# ---------------------------------------------------------------------------
# 3. Bad signatures raise TypeError at decoration time
# ---------------------------------------------------------------------------

def test_wrong_arg_count_raises_type_error() -> None:
    with pytest.raises(TypeError, match="exactly 2 parameters"):
        @tool(description="bad")
        def one_param(ctx: ToolContext) -> dict:
            return {}


def test_wrong_first_param_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="first parameter must be annotated as ToolContext"):
        @tool(description="bad")
        def wrong_first(ctx: str, args: AddArgs) -> dict:
            return {}


def test_second_param_not_basemodel_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"pydantic\.BaseModel subclass"):
        @tool(description="bad")
        def wrong_second(ctx: ToolContext, args: dict) -> dict:
            return {}


def test_missing_annotation_on_second_param_raises_type_error() -> None:
    with pytest.raises(TypeError, match=r"pydantic\.BaseModel subclass"):
        @tool(description="bad")
        def no_annotation(ctx: ToolContext, args) -> dict:  # type: ignore[no-untyped-def]
            return {}


# ---------------------------------------------------------------------------
# 4. Sync tool dispatches successfully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_tool_dispatch_success() -> None:
    result = await add.dispatch(_ctx(), {"x": 3, "y": 4})
    assert isinstance(result, ToolResult)
    assert result.is_error is False
    assert result.model_payload == {"sum": 7}


# ---------------------------------------------------------------------------
# 5. Async tool dispatches successfully
# ---------------------------------------------------------------------------

class SleepArgs(BaseModel):
    value: str


@tool(description="Async echo tool.")
async def async_echo(ctx: ToolContext, args: SleepArgs) -> dict:
    await asyncio.sleep(0)
    return {"echoed": args.value}


@pytest.mark.asyncio
async def test_async_tool_dispatch_success() -> None:
    assert async_echo.is_async is True
    result = await async_echo.dispatch(_ctx(), {"value": "hello"})
    assert result.is_error is False
    assert result.model_payload == {"echoed": "hello"}


# ---------------------------------------------------------------------------
# 6. Invalid args caught by Pydantic → ToolResult with is_error=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_args_returns_error_tool_result() -> None:
    # x should be an int; passing a non-coercible string triggers ValidationError
    result = await add.dispatch(_ctx(), {"x": "not-an-int", "y": 4})
    assert result.is_error is True
    assert "error" in result.model_payload  # type: ignore[operator]
    assert "Invalid arguments" in result.model_payload["error"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# 7. Tool raising an exception → ToolResult with is_error=True
# ---------------------------------------------------------------------------

class BoomArgs(BaseModel):
    msg: str


@tool(description="Always raises.")
def boom(ctx: ToolContext, args: BoomArgs) -> dict:
    raise ValueError("boom")


@pytest.mark.asyncio
async def test_tool_exception_returns_error_tool_result() -> None:
    result = await boom.dispatch(_ctx(), {"msg": "ignored"})
    assert result.is_error is True
    assert result.model_payload == {"error": "boom"}  # type: ignore[comparison-overlap]


# ---------------------------------------------------------------------------
# 8. Oversized return value triggers truncation
# ---------------------------------------------------------------------------

class BigArgs(BaseModel):
    size: int


@tool(description="Returns a large string.", max_output_chars=100)
def big_tool(ctx: ToolContext, args: BigArgs) -> dict:
    return {"data": "x" * args.size}


@pytest.mark.asyncio
async def test_oversized_return_is_truncated() -> None:
    result = await big_tool.dispatch(_ctx(), {"size": 10_000})
    assert result.is_error is False
    assert isinstance(result.model_payload, dict)
    assert result.model_payload.get("truncated") is True  # type: ignore[union-attr]
    preview = result.model_payload["preview"]  # type: ignore[index]
    # preview must end with ellipsis and be no longer than max_output_chars + 1 (the ellipsis char)
    assert preview.endswith("\u2026")
    assert result.model_payload["original_chars"] > 100  # type: ignore[operator]
    # trace_payload retains full body
    assert isinstance(result.trace_payload, dict)
    assert len(result.trace_payload["data"]) == 10_000  # type: ignore[index]


# ---------------------------------------------------------------------------
# 9. ToolSet.dispatch with unknown name raises UnknownToolError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toolset_dispatch_unknown_raises() -> None:
    ts = ToolSet(name="my_set", tools=[add])
    with pytest.raises(UnknownToolError):
        await ts.dispatch("nonexistent", {}, _ctx())


# ---------------------------------------------------------------------------
# 10. ToolSet.anthropic_schemas returns one dict per tool
# ---------------------------------------------------------------------------

def test_toolset_anthropic_schemas_returns_all() -> None:
    ts = ToolSet(name="my_set", tools=[add, async_echo])
    schemas = ts.anthropic_schemas()
    assert len(schemas) == 2
    names = {s["name"] for s in schemas}
    assert "add" in names
    assert "async_echo" in names


# ---------------------------------------------------------------------------
# 11. Tool returning BaseModel → model_payload is model_dump(mode="json") dict
# ---------------------------------------------------------------------------

class OutputModel(BaseModel):
    result: int
    label: str


class PlusArgs(BaseModel):
    a: int
    b: int


@tool(description="Returns a BaseModel.")
def pydantic_returner(ctx: ToolContext, args: PlusArgs) -> OutputModel:
    return OutputModel(result=args.a + args.b, label="sum")


@pytest.mark.asyncio
async def test_tool_returning_basemodel_is_dumped() -> None:
    result = await pydantic_returner.dispatch(_ctx(), {"a": 10, "b": 5})
    assert result.is_error is False
    assert result.model_payload == {"result": 15, "label": "sum"}


# ---------------------------------------------------------------------------
# 12. Nested BaseModel args are inlined — no $ref / $defs in schema
#     (Anthropic's tool input_schema doesn't accept JSON-Schema refs.)
# ---------------------------------------------------------------------------

class _Address(BaseModel):
    line1: str
    postcode: str


class NestedArgs(BaseModel):
    address: _Address
    note: Optional[str] = None


@tool(description="Tool with nested BaseModel args.")
def nested_tool(ctx: ToolContext, args: NestedArgs) -> dict:
    return {"ok": True}


def test_nested_basemodel_args_emit_inline_schema() -> None:
    schema = nested_tool.to_anthropic_schema()
    input_schema = schema["input_schema"]
    assert "$defs" not in input_schema
    serialized = str(input_schema)
    assert "$ref" not in serialized
    assert "$defs" not in serialized

    address = input_schema["properties"]["address"]
    assert address["type"] == "object"
    assert set(address["properties"].keys()) == {"line1", "postcode"}


# ---------------------------------------------------------------------------
# 13. ToolSet rejects duplicate tool names
# ---------------------------------------------------------------------------

def test_toolset_rejects_duplicate_names() -> None:
    @tool(name="same", description="first")
    def first(ctx: ToolContext, args: AddArgs) -> dict:
        return {}

    @tool(name="same", description="second")
    def second(ctx: ToolContext, args: AddArgs) -> dict:
        return {}

    with pytest.raises(ValueError, match="Duplicate tool names"):
        ToolSet(name="clashy", tools=[first, second])
