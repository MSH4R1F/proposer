"""Tests for proposition domain models (SHA-36 Task 1).

TDD: written before models.py exists. Tests should fail with ImportError
until the models module is implemented.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from kg_builder.propositions import (
    DecisionDocument,
    ExtractionRunStatus,
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    PropositionExtractionRun,
    PropositionType,
    deterministic_document_id,
    deterministic_edge_id,
    deterministic_proposition_id,
    normalize_for_matching,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_proposition_kwargs(**overrides):
    base = dict(
        proposition_id=uuid4(),
        document_id=uuid4(),
        case_reference="[2024] EWCC 1",
        text="Section 213 requires deposit protection.",
        source_passage="The landlord must protect the deposit under section 213.",
        proposition_type=PropositionType.rule,
        confidence=0.8,
    )
    base.update(overrides)
    return base


def _valid_document_kwargs(**overrides):
    base = dict(
        document_id=uuid4(),
        case_reference="[2024] EWCC 1",
        content_sha256="a" * 64,
        text_sha256="b" * 64,
        char_count=1234,
        extraction_method="pymupdf_pdf",
    )
    base.update(overrides)
    return base


def _valid_run_kwargs(**overrides):
    base = dict(
        document_id=uuid4(),
        extractor_version="0.1.0",
        prompt_version="2026-05-01",
        prompt_sha256="c" * 64,
        model="mock",
        status=ExtractionRunStatus.succeeded,
        input_chars=10000,
        chunk_count=3,
        proposition_count=12,
        edge_count=4,
        rejected_count=1,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Proposition validators
# ---------------------------------------------------------------------------


def test_proposition_text_max_length_500():
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(text="x" * 501))


def test_proposition_source_passage_max_length_1500():
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(source_passage="x" * 1501))


def test_proposition_confidence_range():
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(confidence=1.5))
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(confidence=-0.1))


def test_proposition_paragraph_ref_accepts_string_labels():
    for label in ["12", "12(3)", "A1", "Sch.1 para 4", None]:
        prop = Proposition(**_valid_proposition_kwargs(paragraph_ref=label))
        assert prop.paragraph_ref == label


def test_proposition_negative_offsets_rejected():
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(source_start_char=-1))


def test_proposition_inverted_span_rejected():
    with pytest.raises(ValidationError):
        Proposition(
            **_valid_proposition_kwargs(source_start_char=100, source_end_char=50)
        )


def test_proposition_page_span_1_based():
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(page_start=0))
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(page_start=2, page_end=1))


# ---------------------------------------------------------------------------
# Deterministic IDs
# ---------------------------------------------------------------------------


def test_proposition_id_stable_across_calls():
    doc_id = uuid4()
    a = deterministic_proposition_id(
        doc_id, "12", "passage text", PropositionType.fact, "claim text"
    )
    b = deterministic_proposition_id(
        doc_id, "12", "passage text", PropositionType.fact, "claim text"
    )
    assert a == b


def test_proposition_id_differs_for_distinct_source_passages():
    doc_id = uuid4()
    a = deterministic_proposition_id(
        doc_id, "12", "passage one", PropositionType.fact, "claim text"
    )
    b = deterministic_proposition_id(
        doc_id, "12", "passage two", PropositionType.fact, "claim text"
    )
    assert a != b


def test_proposition_id_differs_for_distinct_text():
    doc_id = uuid4()
    a = deterministic_proposition_id(
        doc_id, "12", "passage", PropositionType.fact, "claim one"
    )
    b = deterministic_proposition_id(
        doc_id, "12", "passage", PropositionType.fact, "claim two"
    )
    assert a != b


def test_proposition_id_uses_paragraph_ref_in_key():
    doc_id = uuid4()
    a = deterministic_proposition_id(
        doc_id, "12", "passage", PropositionType.fact, "claim"
    )
    b = deterministic_proposition_id(
        doc_id, "13", "passage", PropositionType.fact, "claim"
    )
    assert a != b


def test_deterministic_document_id_stable():
    a = deterministic_document_id("https://bailii.org/x.pdf", "a" * 64)
    b = deterministic_document_id("https://bailii.org/x.pdf", "a" * 64)
    assert a == b
    assert isinstance(a, UUID)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def test_edge_self_loop_rejected():
    same = uuid4()
    with pytest.raises(ValidationError):
        PropositionEdge(
            from_proposition_id=same,
            to_proposition_id=same,
            document_id=uuid4(),
            edge_type=PropositionEdgeType.supports,
            confidence=0.9,
        )


def test_edge_id_stable():
    a_id = uuid4()
    b_id = uuid4()
    a = deterministic_edge_id(a_id, b_id, PropositionEdgeType.supports)
    b = deterministic_edge_id(a_id, b_id, PropositionEdgeType.supports)
    assert a == b


# ---------------------------------------------------------------------------
# Enum allowlists
# ---------------------------------------------------------------------------


def test_proposition_type_allowlist():
    assert {t.value for t in PropositionType} == {
        "fact",
        "rule",
        "outcome",
        "authority",
    }


def test_proposition_edge_type_allowlist():
    assert {t.value for t in PropositionEdgeType} == {
        "supports",
        "contradicts",
        "cites",
        "temporal_before",
        "applies_rule_to_fact",
    }


def test_extraction_run_status_allowlist():
    assert {s.value for s in ExtractionRunStatus} == {
        "started",
        "succeeded",
        "failed",
        "skipped",
    }


# ---------------------------------------------------------------------------
# DecisionDocument
# ---------------------------------------------------------------------------


def test_decision_document_content_sha256_must_be_64_hex():
    with pytest.raises(ValidationError):
        DecisionDocument(**_valid_document_kwargs(content_sha256="not-a-hash"))
    # 64 hex passes
    doc = DecisionDocument(**_valid_document_kwargs(content_sha256="a" * 64))
    assert doc.content_sha256 == "a" * 64


def test_decision_document_char_count_non_negative():
    with pytest.raises(ValidationError):
        DecisionDocument(**_valid_document_kwargs(char_count=-1))


# ---------------------------------------------------------------------------
# ExtractionRun
# ---------------------------------------------------------------------------


def test_extraction_run_counts_non_negative():
    with pytest.raises(ValidationError):
        PropositionExtractionRun(**_valid_run_kwargs(proposition_count=-1))


# ---------------------------------------------------------------------------
# normalize_for_matching
# ---------------------------------------------------------------------------


def test_normalize_for_matching_collapses_whitespace():
    assert normalize_for_matching("foo   bar\n\nbaz") == "foo bar baz"


def test_normalize_for_matching_preserves_punctuation_and_case():
    assert normalize_for_matching("Section 213(3).") == "Section 213(3)."


# ---------------------------------------------------------------------------
# Stream C PR 5 — factor-constrained retrieval fields (Task 5.4)
# ---------------------------------------------------------------------------


def test_proposition_loads_existing_data_with_default_authority_level():
    """Existing Proposition payloads (no PR 5 fields) load with safe defaults."""
    prop = Proposition(**_valid_proposition_kwargs())
    assert prop.factor_ids == []
    assert prop.outcome_component_ids == []
    assert prop.remedy_component_ids == []
    assert prop.claim_head_ids == []
    assert prop.authority_level == "comparator"
    assert prop.proposition_role == "fact_comparator"


def test_proposition_populates_new_fields_when_provided():
    prop = Proposition(
        **_valid_proposition_kwargs(
            factor_ids=["repair_responsibility_established", "inspection_offered"],
            outcome_component_ids=["oc_1"],
            remedy_component_ids=["rc_1"],
            claim_head_ids=["ch_1"],
            authority_level="binding_precedent",
            proposition_role="legal_test",
        )
    )
    assert prop.factor_ids == [
        "repair_responsibility_established",
        "inspection_offered",
    ]
    assert prop.outcome_component_ids == ["oc_1"]
    assert prop.remedy_component_ids == ["rc_1"]
    assert prop.claim_head_ids == ["ch_1"]
    assert prop.authority_level == "binding_precedent"
    assert prop.proposition_role == "legal_test"


def test_proposition_authority_level_closed_literal():
    """Invalid authority_level values must raise ValidationError."""
    with pytest.raises(ValidationError):
        Proposition(
            **_valid_proposition_kwargs(authority_level="not_a_valid_level")
        )


def test_proposition_authority_level_accepts_all_allowed_values():
    allowed = [
        "statute",
        "regulation",
        "official_guidance",
        "binding_precedent",
        "persuasive",
        "comparator",
    ]
    for value in allowed:
        prop = Proposition(**_valid_proposition_kwargs(authority_level=value))
        assert prop.authority_level == value


def test_proposition_role_closed_literal():
    """Invalid proposition_role values must raise ValidationError."""
    with pytest.raises(ValidationError):
        Proposition(**_valid_proposition_kwargs(proposition_role="invalid_role"))


def test_proposition_role_accepts_all_allowed_values():
    allowed = [
        "legal_test",
        "factual_finding",
        "fact_comparator",
        "remedy_rationale",
    ]
    for value in allowed:
        prop = Proposition(**_valid_proposition_kwargs(proposition_role=value))
        assert prop.proposition_role == value


def test_proposition_round_trip_with_new_fields_via_json():
    """Full JSON round-trip including the new fields preserves equality."""
    original = Proposition(
        **_valid_proposition_kwargs(
            factor_ids=["repair_responsibility_established"],
            outcome_component_ids=["oc_alpha"],
            remedy_component_ids=["rc_beta"],
            claim_head_ids=["ch_gamma"],
            authority_level="statute",
            proposition_role="legal_test",
        )
    )
    restored = Proposition.model_validate_json(original.model_dump_json())
    assert original == restored
    assert restored.factor_ids == ["repair_responsibility_established"]
    assert restored.authority_level == "statute"
    assert restored.proposition_role == "legal_test"
