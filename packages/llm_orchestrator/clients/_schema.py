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

from typing import Any, Dict, FrozenSet, List, Set, Type

from pydantic import BaseModel

from .exceptions import LLMStructuredOutputError

__all__ = ["strict_json_schema"]


# Whitelist of JSON-Schema keywords that OpenAI Structured Outputs strict mode
# accepts. We use a whitelist (rather than a blacklist of unsupported keywords)
# so that any new draft-2020-12 keyword Pydantic starts emitting — e.g.
# ``prefixItems`` for tuple-typed fields — surfaces as a loud failure rather
# than slipping through as a silently-loosened schema.
#
# Notes:
#   - ``discriminator`` is NOT included. OpenAI accepts it inside ``anyOf``
#     for tagged unions but not on bare object schemas; until we have a
#     concrete tagged-union model with tests, we fail loud.
#   - ``default`` is allowed because Pydantic emits it freely; strict mode
#     ignores it without complaint.
_ALLOWED_KEYWORDS: FrozenSet[str] = frozenset(
    {
        # Core type / shape
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "enum",
        # References / definitions
        "$ref",
        "$defs",
        "definitions",
        # Metadata / display
        "title",
        "description",
        "default",
    }
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

    # Self-referential root models (e.g. a tree node with children: List[Self])
    # cause Pydantic to emit ``{"$defs": {...}, "$ref": "#/$defs/Node"}`` at
    # the top level. OpenAI strict mode requires the outer ``parameters`` to
    # be ``type: object`` — a bare ``$ref`` is rejected at the API boundary.
    # Fail loud here rather than waste a request: the user must define a
    # non-recursive root wrapper.
    if (
        isinstance(rewritten, dict)
        and "$ref" in rewritten
        and rewritten.get("type") != "object"
        and "properties" not in rewritten
    ):
        raise LLMStructuredOutputError(
            f"OpenAI strict-mode schema rewrite failed at <root>: "
            f"top-level $ref ({rewritten['$ref']!r}) is not supported. "
            f"Self-referential root models are rejected by OpenAI Structured "
            f"Outputs — define a non-recursive wrapper model whose fields "
            f"reference the recursive type instead."
        )

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
    # Reject any keyword not on the strict-mode whitelist up front so the
    # developer sees ALL offending constraints in one pass. The whitelist
    # approach guards against new draft-2020-12 keywords (e.g. ``prefixItems``)
    # being silently emitted by future Pydantic versions.
    for kw in node:
        if kw not in _ALLOWED_KEYWORDS:
            field = path or "<root>"
            raise LLMStructuredOutputError(
                f"OpenAI strict-mode schema rewrite failed at {field!s}: "
                f"unsupported schema keyword {kw!r}={node[kw]!r}. "
                f"Remove the constraint from the Pydantic model or relax it "
                f"into a description, then re-run the audit."
            )

    # Detect object-shaped node (either explicit or implicit via properties).
    is_object = node.get("type") == "object" or "properties" in node

    # Catch open-dict objects (``Dict[str, V]``) before we overwrite
    # ``additionalProperties``. Pydantic emits these as
    # ``{"type": "object", "additionalProperties": {"type": "string"}}`` (a
    # SCHEMA, not ``False``). Forcing ``additionalProperties: False`` would
    # silently flip the contract from "string values allowed" to "no keys
    # allowed at all" — exactly the kind of silent-loosening this helper
    # exists to prevent. Fail loud and tell the user to model the dict as a
    # closed Pydantic class or a list-of-pairs.
    if is_object:
        ap = node.get("additionalProperties")
        if ap is not None and ap is not False:
            field = path or "<root>"
            raise LLMStructuredOutputError(
                f"OpenAI strict-mode schema rewrite failed at {field!s}: "
                f"open-dict objects (additionalProperties is a schema, not "
                f"False) are not supported by OpenAI Structured Outputs. "
                f"Replace Dict[str, V] with a closed Pydantic model or a "
                f"list of (key, value) pairs."
            )

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
        # Hoist ``description`` to the wrapper so users see it in the
        # combined union; strict mode ignores extra metadata anyway.
        wrapper: Dict[str, Any] = {
            "anyOf": [prop_schema, {"type": "null"}],
        }
        if "description" in prop_schema:
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
