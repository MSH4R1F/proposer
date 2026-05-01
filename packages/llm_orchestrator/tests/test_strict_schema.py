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

from typing import List, Optional

import pytest
from pydantic import BaseModel, Field

from llm_orchestrator.clients._schema import strict_json_schema
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
# Production-model audit — the DoD-critical CI tripwire (spec §6.2 / §14.2).
#
# These models are the candidate ``response_model`` arguments for
# ``BaseLLMClient.generate_structured(...)`` once the OpenAI provider lands.
# Each one is exercised here so a future schema change surfaces in CI rather
# than at OpenAI's API boundary.
#
# Today, every one of these models carries at least one strict-mode-
# unsupported keyword (``minimum``/``maximum`` from ``Field(ge=..., le=...)``,
# ``minItems``/``maxItems`` from tuple length, or ``format: date``). The
# task instructions are explicit: "do NOT modify the production model.
# Instead xfail/skip with a clear reason." See the status report on this
# task for the SHA-114 follow-up.
# ---------------------------------------------------------------------------


def _audit_model(model_cls: type[BaseModel]) -> None:
    """Helper: call strict_json_schema and re-raise with the model name."""
    try:
        strict_json_schema(model_cls)
    except LLMStructuredOutputError as exc:
        raise AssertionError(
            f"Strict-mode schema audit failed for {model_cls.__name__}: {exc}"
        ) from exc


@pytest.mark.xfail(
    reason="IssuePrediction uses Field(ge=0, le=1) and Tuple[float, float] "
    "which emit minimum/maximum/minItems/maxItems — needs SHA-114 follow-up "
    "to remove range constraints from the schema.",
    strict=True,
)
def test_audit_issue_prediction_strict_schema() -> None:
    from llm_orchestrator.models.prediction_v2 import IssuePrediction

    _audit_model(IssuePrediction)


@pytest.mark.xfail(
    reason="PredictionResult inherits all IssuePrediction/Citation/ReasoningStep "
    "ge/le constraints plus Tuple[float, float] settlement range — needs "
    "SHA-114 follow-up.",
    strict=True,
)
def test_audit_prediction_result_strict_schema() -> None:
    from llm_orchestrator.models.prediction_v2 import PredictionResult

    _audit_model(PredictionResult)


@pytest.mark.xfail(
    reason="ExtractionResult.updated_case_file embeds CaseFile, which uses "
    "Field(ge=0, le=1) on confidence/completeness fields and date format on "
    "tenancy dates — needs SHA-114 follow-up.",
    strict=True,
)
def test_audit_extraction_result_strict_schema() -> None:
    from llm_orchestrator.extractors.fact_extractor import ExtractionResult

    _audit_model(ExtractionResult)


@pytest.mark.xfail(
    reason="Citation has Field(default=0.0, ge=0, le=1) on similarity_score — "
    "needs SHA-114 follow-up.",
    strict=True,
)
def test_audit_citation_strict_schema() -> None:
    from llm_orchestrator.models.prediction_v2 import Citation

    _audit_model(Citation)


@pytest.mark.xfail(
    reason="ReasoningStep has Field(default=0.8, ge=0, le=1) on confidence — "
    "needs SHA-114 follow-up.",
    strict=True,
)
def test_audit_reasoning_step_strict_schema() -> None:
    from llm_orchestrator.models.prediction_v2 import ReasoningStep

    _audit_model(ReasoningStep)


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
