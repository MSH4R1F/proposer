from __future__ import annotations

import asyncio
import inspect
import json
import typing
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union

from pydantic import BaseModel

from .context import ToolContext

JSONValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


class ToolResult(BaseModel):
    model_payload: JSONValue
    trace_payload: Optional[JSONValue] = None
    is_error: bool = False


class UnknownToolError(Exception):
    """Raised when ToolSet.dispatch is asked for a name not in the set."""


class Tool:
    """Immutable wrapper around a tool function. Built via @tool; not constructed directly by callers."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_model: Type[BaseModel],
        fn: Callable,
        is_async: bool,
        max_output_chars: int,
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.fn = fn
        self.is_async = is_async
        self.max_output_chars = max_output_chars

    def to_anthropic_schema(self) -> Dict[str, Any]:
        raw_schema = self.args_model.model_json_schema()

        # Normalize: keep type, properties, required only; ensure type == "object"
        input_schema: Dict[str, Any] = {"type": "object"}
        if "properties" in raw_schema:
            input_schema["properties"] = raw_schema["properties"]
        if "required" in raw_schema:
            input_schema["required"] = raw_schema["required"]

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": input_schema,
        }

    async def dispatch(self, ctx: ToolContext, raw_args: Dict[str, Any]) -> ToolResult:
        # 1. Validate args
        try:
            parsed_args = self.args_model.model_validate(raw_args)
        except Exception as exc:
            error_msg = f"Invalid arguments: {exc}"
            return ToolResult(
                is_error=True,
                model_payload={"error": error_msg[: self.max_output_chars]},
            )

        # 2. Call the function
        try:
            if self.is_async:
                result = await self.fn(ctx, parsed_args)
            else:
                result = await asyncio.to_thread(self.fn, ctx, parsed_args)
        except Exception as exc:
            return ToolResult(
                is_error=True,
                model_payload={"error": str(exc)[: self.max_output_chars]},
            )

        # 3. Normalize return value
        if isinstance(result, BaseModel):
            normalized: JSONValue = result.model_dump(mode="json")
        elif isinstance(result, (dict, list, str, int, float, bool)) or result is None:
            normalized = result
        else:
            return ToolResult(
                is_error=True,
                model_payload={"error": "Tool returned non-JSON-serializable value"},
            )

        # 4. Check size
        try:
            serialized = json.dumps(normalized, ensure_ascii=True, default=str)
        except Exception:
            return ToolResult(
                is_error=True,
                model_payload={"error": "Tool returned non-JSON-serializable value"},
            )

        if len(serialized) > self.max_output_chars:
            model_payload: JSONValue = {
                "truncated": True,
                "preview": serialized[: self.max_output_chars] + "\u2026",
                "original_chars": len(serialized),
            }
            return ToolResult(
                model_payload=model_payload,
                trace_payload=normalized,
                is_error=False,
            )

        return ToolResult(model_payload=normalized, trace_payload=normalized, is_error=False)


class ToolSet:
    def __init__(self, *, name: str, tools: Sequence[Tool]) -> None:
        self.name = name
        self.tools: Sequence[Tool] = tuple(tools)
        self._by_name: Dict[str, Tool] = {t.name: t for t in self.tools}

    def anthropic_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self.tools]

    async def dispatch(self, name: str, raw_args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        if name not in self._by_name:
            raise UnknownToolError(name)
        return await self._by_name[name].dispatch(ctx, raw_args)


def tool(
    *,
    name: Optional[str] = None,
    description: str,
    max_output_chars: int = 2000,
) -> Callable[[Callable], Tool]:
    def decorator(fn: Callable) -> Tool:
        # Inspect signature (use parameter count from inspect)
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())

        if len(params) != 2:
            raise TypeError(
                f"@tool function '{fn.__name__}' must have exactly 2 parameters "
                f"(ctx: ToolContext, args: <BaseModel subclass>), got {len(params)}."
            )

        # Resolve annotations — handles 'from __future__ import annotations' (PEP 563)
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}

        first_param_name = params[0].name
        second_param_name = params[1].name

        first_annotation = hints.get(first_param_name, inspect.Parameter.empty)
        second_annotation = hints.get(second_param_name, inspect.Parameter.empty)

        # Validate first param is ToolContext
        if first_annotation is inspect.Parameter.empty or first_annotation is not ToolContext:
            raise TypeError(
                f"@tool function '{fn.__name__}': first parameter must be annotated as ToolContext, "
                f"got {first_annotation!r}."
            )

        # Validate second param is a BaseModel subclass
        if (
            second_annotation is inspect.Parameter.empty
            or not (isinstance(second_annotation, type) and issubclass(second_annotation, BaseModel))
        ):
            raise TypeError(
                f"@tool function '{fn.__name__}': second parameter must be annotated as a "
                f"pydantic.BaseModel subclass, got {second_annotation!r}."
            )

        tool_name = name if name is not None else fn.__name__
        is_async = asyncio.iscoroutinefunction(fn)

        return Tool(
            name=tool_name,
            description=description,
            args_model=second_annotation,
            fn=fn,
            is_async=is_async,
            max_output_chars=max_output_chars,
        )

    return decorator
