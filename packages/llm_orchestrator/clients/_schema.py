"""Strict JSON Schema rewriter for OpenAI Structured Outputs.

OpenAI's Responses API in strict mode (Structured Outputs) accepts only a
small subset of JSON Schema. The constraints that bite us:

- every object schema must declare ``additionalProperties: false``
- every property must appear in ``required`` (genuinely optional fields
  must be modelled as nullable unions instead)
- supported keywords are limited to: ``type``, ``properties``,
  ``required``, ``additionalProperties``, ``items``, ``anyOf``, ``enum``,
  ``description``, plus root-level ``$defs``/``definitions`` and ``$ref``
- ``minimum``/``maximum``/``minLength``/``maxLength``/``pattern``/
  ``format``/``minItems``/``maxItems``/``multipleOf`` are NOT enforced in
  strict mode — silently dropping them would loosen the contract and hide
  bugs, so this module raises ``LLMStructuredOutputError`` instead.

Pydantic v2's ``BaseModel.model_json_schema()`` produces a draft-2020
schema with ``$defs`` and ``$ref``s for nested models. ``strict_json_schema``
walks the whole tree (top-level + every entry in ``$defs``) and returns a
plain-dict schema that OpenAI strict mode will accept.

See SHA-114 spec §6.2 / §14.2.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple, Type

from pydantic import BaseModel

from .exceptions import LLMStructuredOutputError

__all__ = ["strict_json_schema"]


# Keywords that are tolerated by some OpenAI surfaces but NOT enforced by
# strict mode. We refuse to emit them — silently stripping would loosen the
# contract without telling the team.
_UNSUPPORTED_KEYWORDS: Tuple[str, ...] = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "multipleOf",
    "minProperties",
    "maxProperties",
    "oneOf",
    "allOf",
    "not",
    "const",
)

# Keywords that are part of the strict-mode subset and should be left alone
# during the walk (we still recurse into them for nested objects).
_PASSTHROUGH_CONTAINERS: Tuple[str, ...] = (
    "properties",
    "items",
    "anyOf",
    "$defs",
    "definitions",
)


def strict_json_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Rewrite a Pydantic model's JSON schema for OpenAI Structured Outputs.

    Args:
        model: A subclass of ``pydantic.BaseModel``.

    Returns:
        A plain dict schema where every object has
        ``additionalProperties: false`` and every property is in
        ``required`` (with optionals rewritten as nullable unions).

    Raises:
        LLMStructuredOutputError: if the model's schema contains any
            keyword that strict mode does not enforce. The error message
            names the offending field path and keyword so the team can
            fix the source model.
    """
    raw = model.model_json_schema()
    # Walk every $defs entry first so the top-level walk sees rewritten
    # nested objects via $ref (the $ref itself stays inline).
    defs = raw.get("$defs") or raw.get("definitions") or {}
    rewritten_defs: Dict[str, Any] = {}
    for name, sub in defs.items():
        rewritten_defs[name] = _walk(sub, path=f"$defs.{name}")

    rewritten = _walk(raw, path="")
    if rewritten_defs:
        # Preserve the original key Pydantic used.
        defs_key = "$defs" if "$defs" in raw else "definitions"
        rewritten[defs_key] = rewritten_defs

    return rewritten


def _walk(node: Any, *, path: str) -> Any:
    """Recursively rewrite ``node`` to satisfy strict mode.

    ``path`` is the dotted JSON-pointer-ish location used in error messages
    so a developer can trace which field violates the constraint.
    """
    if isinstance(node, dict):
        return _walk_dict(node, path=path)
    if isinstance(node, list):
        return [_walk(item, path=f"{path}[{i}]") for i, item in enumerate(node)]
    return node


def _walk_dict(node: Dict[str, Any], *, path: str) -> Dict[str, Any]:
    # Reject unsupported keywords up front so the developer sees ALL the
    # offending constraints, not just whichever one we'd hit during the
    # recursive descent.
    for kw in _UNSUPPORTED_KEYWORDS:
        if kw in node:
            field = path or "<root>"
            raise LLMStructuredOutputError(
                f"OpenAI strict-mode schema rewrite failed at {field!s}: "
                f"keyword {kw!r}={node[kw]!r} is not supported. "
                f"Remove the constraint from the Pydantic model or relax it "
                f"into a description, then re-run the audit."
            )

    # Detect object-shaped node (either explicit or implicit via properties).
    is_object = node.get("type") == "object" or "properties" in node

    out: Dict[str, Any] = {}

    properties = node.get("properties")
    rewritten_props: Dict[str, Any] = {}

    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            rewritten_props[prop_name] = _walk(
                prop_schema, path=f"{path}.{prop_name}" if path else prop_name
            )

    # Copy over everything except keys we'll rebuild ourselves.
    _SPECIAL = {
        "properties",
        "required",
        "additionalProperties",
        "default",
        "title",
    }
    for k, v in node.items():
        if k in _SPECIAL:
            continue
        if k in ("$defs", "definitions"):
            # Top-level $defs are handled by strict_json_schema itself; if a
            # nested node carries them (rare), recurse so we still rewrite.
            out[k] = {
                name: _walk(sub, path=f"{path}.{k}.{name}")
                for name, sub in v.items()
            }
            continue
        out[k] = _walk(v, path=f"{path}.{k}" if path else k)

    # Preserve title if present — strict mode tolerates it (it's metadata).
    if "title" in node:
        out["title"] = node["title"]

    if is_object:
        out["type"] = "object"
        out["additionalProperties"] = False
        if rewritten_props:
            out["properties"] = rewritten_props
            # Strict mode requires every property in `required`. Optional
            # fields are rewritten to nullable types below.
            existing_required: Set[str] = set(node.get("required") or [])
            new_required: List[str] = []
            for prop_name, prop_schema in rewritten_props.items():
                new_required.append(prop_name)
                if prop_name not in existing_required:
                    rewritten_props[prop_name] = _make_nullable(prop_schema)
            out["properties"] = rewritten_props
            out["required"] = new_required
        elif "required" in node:
            # Object with no properties but a stray `required` — drop it.
            pass

    return out


def _make_nullable(prop_schema: Any) -> Any:
    """Rewrite a property schema so ``null`` is an allowed type.

    Strategy:
      - If already an ``anyOf``, ensure one branch is ``{"type": "null"}``.
      - If a single-type schema, convert to ``anyOf`` of (original, null).
      - If a ``$ref``, wrap as ``anyOf`` of (ref, null).
    """
    if not isinstance(prop_schema, dict):
        # Non-dict schema (rare); leave untouched.
        return prop_schema

    if "anyOf" in prop_schema:
        branches = list(prop_schema["anyOf"])
        if not any(isinstance(b, dict) and b.get("type") == "null" for b in branches):
            branches.append({"type": "null"})
        new_schema = dict(prop_schema)
        new_schema["anyOf"] = branches
        return new_schema

    if "$ref" in prop_schema:
        # Pull description/title up to the wrapping anyOf for visibility.
        wrapper: Dict[str, Any] = {
            "anyOf": [prop_schema, {"type": "null"}],
        }
        for k in ("description", "title"):
            if k in prop_schema and k not in wrapper:
                # Leave on the inner ref to avoid cluttering the wrapper —
                # but description is more useful at the wrapper level.
                if k == "description":
                    wrapper["description"] = prop_schema["description"]
        return wrapper

    if "type" in prop_schema:
        type_val = prop_schema["type"]
        if isinstance(type_val, list):
            if "null" not in type_val:
                new_types = list(type_val) + ["null"]
                new_schema = dict(prop_schema)
                new_schema["type"] = new_types
                return new_schema
            return prop_schema
        # Scalar type — convert to anyOf for clarity (strict mode accepts both
        # type-list and anyOf forms; anyOf is friendlier for $ref siblings).
        wrapper = {"anyOf": [{"type": type_val}, {"type": "null"}]}
        for k in ("description", "title", "enum", "items"):
            if k in prop_schema:
                wrapper["anyOf"][0][k] = prop_schema[k]
        return wrapper

    # Schema with neither type nor anyOf nor $ref — leave it alone but warn
    # by adding a null branch.
    return {"anyOf": [prop_schema, {"type": "null"}]}
