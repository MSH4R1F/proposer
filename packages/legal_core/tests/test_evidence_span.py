"""Unit tests for EvidenceSpan."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_core.graph.evidence_span import EvidenceSpan, EvidenceSourceKind


def test_minimum_valid_span():
    span = EvidenceSpan(
        evidence_span_id="span_1",
        source_kind=EvidenceSourceKind.USER_NARRATIVE,
        source_reference="tenant_narrative.txt",
        quote_text="The roof leaked from January 2026.",
    )
    assert span.evidence_span_id == "span_1"
    assert span.source_kind is EvidenceSourceKind.USER_NARRATIVE
    assert span.paragraph_range is None


def test_paragraph_range_round_trip():
    span = EvidenceSpan(
        evidence_span_id="span_2",
        source_kind=EvidenceSourceKind.OMBUDSMAN_DETERMINATION,
        source_reference="housing-ombudsman-202402569.txt",
        quote_text="The Landlord did not respond within ten working days.",
        paragraph_range="¶12-¶14",
    )
    assert span.paragraph_range == "¶12-¶14"


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            evidence_span_id="span_3",
            source_kind=EvidenceSourceKind.USER_NARRATIVE,
            source_reference="x",
            quote_text="y",
            unexpected_field="oops",
        )


def test_frozen_after_construction():
    span = EvidenceSpan(
        evidence_span_id="span_4",
        source_kind=EvidenceSourceKind.USER_NARRATIVE,
        source_reference="x",
        quote_text="y",
    )
    with pytest.raises(ValidationError):
        span.quote_text = "modified"


def test_quote_text_must_be_non_empty():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            evidence_span_id="span_5",
            source_kind=EvidenceSourceKind.USER_NARRATIVE,
            source_reference="x",
            quote_text="",
        )


def test_source_kind_enum_closed():
    valid = {k.value for k in EvidenceSourceKind}
    assert valid == {
        "user_narrative",
        "user_uploaded_document",
        "ombudsman_determination",
        "tribunal_decision",
        "statute",
        "guidance",
        "calculator_trace",
    }
