"""Unit tests for ``llm_orchestrator.clients._schema.strict_json_schema``.

The helper rewrites a Pydantic model's JSON schema into the OpenAI
Structured Outputs strict-mode subset:

- every object has ``additionalProperties: false``
- every property is listed in ``required`` (optionals become nullable
  unions instead)
- nested ``$defs`` definitions are walked the same way
- unsupported keywords (``minimum``/``maximum``/``minLength``/etc.)
  raise ``LLMStructuredOutputError`` rather than being silently dropped

See SHA-114 spec §6.2.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest
from pydantic import BaseModel, Field

from llm_orchestrator.clients._schema import _walk, strict_json_schema
from llm_orchestrator.clients.exceptions import LLMStructuredOutputError


# ---------------------------------------------------------------------------
# Basic shape: required + optional + additionalProperties
# ---------------------------------------------------------------------------


class _SimpleModel(BaseModel):
    name: str
    age: int
    nickname: Optional[str] = None


def test_strict_schema_sets_additional_properties_false() -> None:
    schema = strict_json_schema(_SimpleModel)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False


def test_strict_schema_lists_every_property_in_required() -> None:
    """OpenAI strict mode requires every property to appear in ``required``."""
    schema = strict_json_schema(_SimpleModel)
    assert set(schema["required"]) == {"name", "age", "nickname"}


def test_strict_schema_makes_optional_fields_nullable() -> None:
    """Optional[str] → ``anyOf`` containing ``{"type": "null"}``.

    The original ``default: null`` should be stripped (strict mode does not
    care about defaults, and Pydantic emits them for nullable fields).
    """
    schema = strict_json_schema(_SimpleModel)
    nickname = schema["properties"]["nickname"]
    # Either an anyOf union including null, or a type list containing "null".
    if "anyOf" in nickname:
        types = {entry.get("type") for entry in nickname["anyOf"]}
        assert "null" in types
        assert "string" in types
    else:
        # Type-list shape.
        assert "null" in nickname.get("type", [])
        assert "string" in nickname.get("type", [])


def test_strict_schema_required_only_fields_remain_non_nullable() -> None:
    """Fields that are already required must NOT be rewritten as nullable."""
    schema = strict_json_schema(_SimpleModel)
    name = schema["properties"]["name"]
    assert name == {"type": "string", "title": "Name"} or name["type"] == "string"
    # No null in the type.
    if "anyOf" in name:
        types = {entry.get("type") for entry in name["anyOf"]}
        assert "null" not in types
    else:
        assert name.get("type") != "null"
        if isinstance(name.get("type"), list):
            assert "null" not in name["type"]


# ---------------------------------------------------------------------------
# Unsupported keywords must raise (not silently drop)
# ---------------------------------------------------------------------------


class _ModelWithMinimum(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)


def test_strict_schema_rejects_minimum_maximum() -> None:
    """``Field(ge=..., le=...)`` emits ``minimum``/``maximum``; strict mode
    does not enforce them. Raise loudly so the team rewrites the constraint
    rather than shipping a silently-loosened schema."""
    with pytest.raises(LLMStructuredOutputError) as excinfo:
        strict_json_schema(_ModelWithMinimum)
    msg = str(excinfo.value)
    assert "score" in msg
    # The offending keyword should be named.
    assert "minimum" in msg or "maximum" in msg


class _ModelWithMinLength(BaseModel):
    code: str = Field(..., min_length=5)


def test_strict_schema_rejects_min_length() -> None:
    with pytest.raises(LLMStructuredOutputError) as excinfo:
        strict_json_schema(_ModelWithMinLength)
    assert "code" in str(excinfo.value)
    assert "minLength" in str(excinfo.value)


class _ModelWithPattern(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z]+$")


def test_strict_schema_rejects_pattern() -> None:
    with pytest.raises(LLMStructuredOutputError) as excinfo:
        strict_json_schema(_ModelWithPattern)
    assert "pattern" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Nested $defs handling
# ---------------------------------------------------------------------------


class _Inner(BaseModel):
    label: str
    note: Optional[str] = None


class _Outer(BaseModel):
    title: str
    items: List[_Inner]
    primary: Optional[_Inner] = None


def test_strict_schema_walks_nested_defs() -> None:
    schema = strict_json_schema(_Outer)
    # The outer object is closed.
    assert schema["additionalProperties"] is False
    # Every $def must also be closed and have all-fields-required.
    defs = schema.get("$defs", {})
    assert defs, "expected $defs to be preserved for nested models"
    inner = defs["_Inner"]
    assert inner["additionalProperties"] is False
    assert set(inner["required"]) == {"label", "note"}
    # The optional inner field becomes nullable.
    note = inner["properties"]["note"]
    if "anyOf" in note:
        types = {entry.get("type") for entry in note["anyOf"]}
        assert "null" in types and "string" in types
    else:
        assert "null" in note.get("type", [])


def test_strict_schema_outer_required_includes_optional_nested() -> None:
    """The outer model's optional ``primary: Optional[_Inner]`` must be in
    ``required`` and rewritten as ``anyOf`` of (ref-to-_Inner, null)."""
    schema = strict_json_schema(_Outer)
    assert "primary" in schema["required"]
    primary = schema["properties"]["primary"]
    # Pydantic emits an anyOf for Optional[NestedModel].
    assert "anyOf" in primary
    # One of the branches should be null; the other a $ref to _Inner.
    branches = primary["anyOf"]
    has_null = any(b.get("type") == "null" for b in branches)
    has_ref = any("$ref" in b for b in branches)
    assert has_null
    assert has_ref


# ---------------------------------------------------------------------------
# Idempotence — running twice on the same model is a no-op semantically
# ---------------------------------------------------------------------------


def test_strict_schema_returns_plain_dict() -> None:
    schema = strict_json_schema(_SimpleModel)
    assert isinstance(schema, dict)
    # Top-level must declare type=object.
    assert schema["type"] == "object"


# ---------------------------------------------------------------------------
# Open-dict (Dict[str, V]) must be rejected, not silently flattened
# ---------------------------------------------------------------------------


class _ModelWithOpenDict(BaseModel):
    """``Dict[str, str]`` is an OPEN dict — Pydantic emits
    ``additionalProperties: {"type": "string"}``. If the rewriter naively
    forced ``additionalProperties: False``, the schema would silently flip
    from "string values allowed" to "no keys allowed at all". Must raise.
    """

    metadata: Dict[str, str]


def test_strict_schema_rejects_open_dict() -> None:
    """Regression for the silent-loosening bug where Dict[str, V] emitted
    ``additionalProperties: <schema>`` and the helper unconditionally
    overwrote it with ``False``. Must raise loudly so the developer
    converts to a closed Pydantic model or list-of-pairs."""
    with pytest.raises(LLMStructuredOutputError) as excinfo:
        strict_json_schema(_ModelWithOpenDict)
    msg = str(excinfo.value)
    assert "metadata" in msg, msg
    assert "open-dict" in msg, msg


# ---------------------------------------------------------------------------
# Self-referential root model (top-level $ref) must be rejected
# ---------------------------------------------------------------------------


class _Node(BaseModel):
    """Self-referential root: emits ``{"$defs": {...}, "$ref": "#/$defs/_Node"}``
    at the top level (Pydantic v2 behaviour). Strict mode requires the outer
    ``parameters`` to be ``type: object`` — bare ``$ref`` is rejected at the
    OpenAI API boundary."""

    label: str
    children: List["_Node"] = Field(default_factory=list)


_Node.model_rebuild()


def test_strict_schema_rejects_self_referential_root() -> None:
    with pytest.raises(LLMStructuredOutputError) as excinfo:
        strict_json_schema(_Node)
    msg = str(excinfo.value)
    assert "$ref" in msg or "recursive" in msg.lower() or "root" in msg.lower(), msg


# ---------------------------------------------------------------------------
# Whitelist enforcement — unknown keywords must raise (e.g. prefixItems)
# ---------------------------------------------------------------------------


def test_strict_schema_rejects_prefix_items() -> None:
    """``prefixItems`` is a JSON Schema 2020-12 keyword that future Pydantic
    versions might emit for tuple types. It is NOT supported by OpenAI strict
    mode. The whitelist must reject it loudly even though Pydantic does not
    emit it for the field shapes in this test suite today.

    We hand-construct the schema dict and feed it through ``_walk`` directly
    rather than rely on Pydantic emitting it naturally."""
    handcrafted = {
        "type": "object",
        "properties": {
            "pair": {
                "type": "array",
                "prefixItems": [{"type": "string"}, {"type": "number"}],
            }
        },
        "required": ["pair"],
    }
    with pytest.raises(LLMStructuredOutputError) as excinfo:
        _walk(handcrafted, path="")
    assert "prefixItems" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Production-model audit — the DoD-critical CI tripwire (spec §6.2 / §14.2).
#
# These models are the candidate ``response_model`` arguments for
# ``BaseLLMClient.generate_structured(...)`` once the OpenAI provider lands.
# Each one is exercised here so a future schema change surfaces in CI rather
# than at OpenAI's API boundary.
#
# We pin the EXACT field path + offending keyword that the strict-mode
# rewriter currently rejects, so:
#   1. When the production model is fixed (range constraint removed,
#      Tuple replaced, etc.), the corresponding test will fail with a
#      clear "unexpected match" error and force the next reviewer to
#      either delete the test (model now passes) or update the pin
#      (model still fails, but on a *different* keyword).
#   2. A future refactor that removes the originally-flagged constraint
#      AND introduces a *different* unsupported keyword will not silently
#      slip through (which is what bare ``xfail(strict=True)`` allowed).
#
# The pin uses ``pytest.raises(..., match=...)`` against the field-path
# fragment (e.g. ``$defs.Citation.similarity_score``) which is stable across
# Pydantic patch versions even if the surrounding error wording shifts.
# ---------------------------------------------------------------------------


def test_audit_issue_prediction_strict_schema() -> None:
    """Pinned: IssuePrediction nests Citation, which has
    ``similarity_score: Field(ge=0, le=1)`` → ``minimum``."""
    from llm_orchestrator.models.prediction_v2 import IssuePrediction

    with pytest.raises(
        LLMStructuredOutputError,
        match=r"\$defs\.Citation\.similarity_score",
    ):
        strict_json_schema(IssuePrediction)


def test_audit_prediction_result_strict_schema() -> None:
    """Pinned: PredictionResult inherits the same Citation tree, so it trips
    on the same ``$defs.Citation.similarity_score`` field first."""
    from llm_orchestrator.models.prediction_v2 import PredictionResult

    with pytest.raises(
        LLMStructuredOutputError,
        match=r"\$defs\.Citation\.similarity_score",
    ):
        strict_json_schema(PredictionResult)


def test_audit_extraction_result_strict_schema() -> None:
    """Pinned: ExtractionResult.updated_case_file embeds CaseFile whose
    ``events`` field is ``Dict[str, ...]`` — an open-dict that strict mode
    cannot represent. (Once events is closed, the next failure will be
    ``CaseFile.completeness_score`` from ``Field(ge=0, le=1)``.)"""
    from llm_orchestrator.extractors.fact_extractor import ExtractionResult

    with pytest.raises(
        LLMStructuredOutputError,
        match=r"\$defs\.CaseFile\.events\.items",
    ):
        strict_json_schema(ExtractionResult)


def test_audit_citation_strict_schema() -> None:
    """Pinned: Citation has ``similarity_score: Field(default=0.0, ge=0, le=1)``."""
    from llm_orchestrator.models.prediction_v2 import Citation

    with pytest.raises(
        LLMStructuredOutputError,
        match=r"similarity_score",
    ):
        strict_json_schema(Citation)


def test_audit_reasoning_step_strict_schema() -> None:
    """Pinned: ReasoningStep nests Citation, which trips first on
    ``similarity_score`` before any ReasoningStep-local field."""
    from llm_orchestrator.models.prediction_v2 import ReasoningStep

    with pytest.raises(
        LLMStructuredOutputError,
        match=r"\$defs\.Citation\.similarity_score",
    ):
        strict_json_schema(ReasoningStep)


# A clean baseline — DisputeIssue is a pure str-enum proxy via DisputeIssue
# itself but the lightweight mediation models ought to round-trip cleanly.
# If/when this ever fails, that's a real regression.
def test_audit_clean_models_pass() -> None:
    """Sanity check: at least one production-shaped model must round-trip
    successfully today, otherwise the helper is broken rather than the
    audited models."""

    class _Clean(BaseModel):
        a: str
        b: int
        c: Optional[str] = None

    # Should not raise.
    schema = strict_json_schema(_Clean)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"a", "b", "c"}
