from __future__ import annotations

import asyncio
import inspect
import json
import typing
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union

from pydantic import BaseModel

from ..clients._schema import strict_json_schema
from ..clients.types import LLMProvider
from .context import ToolContext

JSONValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]

_REF_PREFIX = "#/$defs/"


def _inline_refs(
    node: Any,
    defs: Dict[str, Any],
    _seen: Optional[frozenset] = None,
) -> Any:
    """Recursively replace JSON-Schema ``$ref``s against ``$defs`` with inline definitions.

    Anthropic's tool ``input_schema`` does not accept ``$ref`` / ``$defs``; Pydantic
    emits them for nested BaseModel fields. We walk the tree and substitute each
    ref with a copy of its definition, guarding against cycles.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_REF_PREFIX):
            key = ref[len(_REF_PREFIX):]
            seen = _seen or frozenset()
            if key in seen or key not in defs:
                # Cyclic or dangling ref — strip the $ref rather than emit an invalid schema.
                return {k: v for k, v in node.items() if k != "$ref"}
            resolved = _inline_refs(defs[key], defs, seen | {key})
            # Merge sibling keys (e.g. description) onto the resolved definition.
            merged = dict(resolved) if isinstance(resolved, dict) else {}
            for k, v in node.items():
                if k == "$ref":
                    continue
                merged[k] = _inline_refs(v, defs, _seen)
            return merged
        return {k: _inline_refs(v, defs, _seen) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(item, defs, _seen) for item in node]
    return node


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
        defs = raw_schema.get("$defs", {}) or {}

        # Normalize: keep type, properties, required only; ensure type == "object".
        # Anthropic's input_schema doesn't accept $ref/$defs, so inline any refs
        # that nested BaseModel fields emit.
        input_schema: Dict[str, Any] = {"type": "object"}
        if "properties" in raw_schema:
            input_schema["properties"] = _inline_refs(raw_schema["properties"], defs)
        if "required" in raw_schema:
            input_schema["required"] = raw_schema["required"]

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": input_schema,
        }

    def to_openai_response_tool(self) -> Dict[str, Any]:
        """Emit the OpenAI Responses API ``function`` tool envelope.

        Differs from ``to_anthropic_schema`` in two ways (per SHA-114
        spec §6.3):
          1. Top-level is tagged with ``"type": "function"``.
          2. Args schema is under ``"parameters"`` (not ``"input_schema"``)
             and is rewritten via ``strict_json_schema`` to satisfy
             Structured Outputs strict mode.
        """
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": strict_json_schema(self.args_model),
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

        # 4. Check size. No default= fallback — tools must return JSON-native
        # values. Silent str-coercion would hide real bugs.
        try:
            serialized = json.dumps(normalized, ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError):
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
        seen: Dict[str, int] = {}
        duplicates: List[str] = []
        for t in self.tools:
            if t.name in seen:
                if seen[t.name] == 1:
                    duplicates.append(t.name)
                seen[t.name] += 1
            else:
                seen[t.name] = 1
        if duplicates:
            raise ValueError(
                f"Duplicate tool names in ToolSet '{name}': {sorted(duplicates)}"
            )
        self._by_name: Dict[str, Tool] = {t.name: t for t in self.tools}

    def anthropic_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self.tools]

    def openai_response_tools(self) -> List[Dict[str, Any]]:
        """Map the toolset to OpenAI Responses ``function`` envelopes.

        Mirrors ``anthropic_schemas`` but produces the OpenAI shape (see
        ``Tool.to_openai_response_tool``). Both methods coexist — neither
        replaces the other (SHA-114 spec §16.5).
        """
        return [t.to_openai_response_tool() for t in self.tools]

    def schemas_for(self, provider: LLMProvider) -> List[Dict[str, Any]]:
        """Return tool schemas in the right shape for ``provider``.

        Provider-aware dispatch so the AgentLoop can hand each adapter the
        envelope it actually accepts: Anthropic's ``input_schema`` shape vs
        OpenAI Responses' ``function`` envelope. Added in SHA-114 step 5 so
        OpenAI agent turns no longer receive Anthropic-shaped schemas.
        """
        if provider == LLMProvider.ANTHROPIC:
            return self.anthropic_schemas()
        if provider == LLMProvider.OPENAI:
            return self.openai_response_tools()
        raise ValueError(f"Unsupported provider: {provider}")

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
        except Exception as exc:
            raise TypeError(
                f"@tool function '{fn.__name__}': could not resolve type hints. "
                f"Ensure all annotations are importable at runtime (not TYPE_CHECKING-only). "
                f"Original error: {exc}"
            ) from exc

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
