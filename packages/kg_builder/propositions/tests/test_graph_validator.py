"""Tests for the graph validator (SHA-36 Task 7).

Pure-function tests; no LLM, no I/O. Validates semantic constraints on
typed edges given the proposition graph.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from kg_builder.propositions.graph_validator import (
    GraphValidationRejection,
    validate_graph,
)
from kg_builder.propositions.models import (
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    PropositionType,
    deterministic_document_id,
    deterministic_edge_id,
    deterministic_proposition_id,
    sha256_hex,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _document_id() -> UUID:
    return deterministic_document_id("test://validator", sha256_hex("content"))


def _make_proposition(
    document_id: UUID,
    text: str,
    *,
    proposition_type: PropositionType = PropositionType.fact,
    paragraph_ref: str = "1",
    source_passage: str = "Source passage.",
) -> Proposition:
    return Proposition(
        proposition_id=deterministic_proposition_id(
            document_id, paragraph_ref, source_passage, proposition_type, text,
        ),
        document_id=document_id,
        case_reference="X",
        text=text,
        source_passage=source_passage,
        paragraph_ref=paragraph_ref,
        proposition_type=proposition_type,
        confidence=0.9,
    )


def _make_edge(
    document_id: UUID,
    from_id: UUID,
    to_id: UUID,
    edge_type: PropositionEdgeType,
    *,
    confidence: float = 0.9,
) -> PropositionEdge:
    return PropositionEdge(
        edge_id=deterministic_edge_id(from_id, to_id, edge_type),
        from_proposition_id=from_id,
        to_proposition_id=to_id,
        document_id=document_id,
        edge_type=edge_type,
        rationale="r",
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validate_graph_accepts_supports_between_facts():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")
    edge = _make_edge(
        document_id, p1.proposition_id, p2.proposition_id,
        PropositionEdgeType.supports,
    )

    accepted, rejections = validate_graph(
        [edge], [p1, p2], expected_document_id=document_id,
    )

    assert accepted == [edge]
    assert rejections == []


def test_validate_graph_rejects_applies_rule_to_fact_with_wrong_types():
    """fact→fact applies_rule_to_fact: rejected."""
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")
    edge = _make_edge(
        document_id, p1.proposition_id, p2.proposition_id,
        PropositionEdgeType.applies_rule_to_fact,
    )

    accepted, rejections = validate_graph(
        [edge], [p1, p2], expected_document_id=document_id,
    )

    assert accepted == []
    assert len(rejections) == 1
    assert rejections[0].reason == "applies_rule_to_fact_endpoint_types"
    assert rejections[0].edge_id == edge.edge_id


def test_validate_graph_accepts_applies_rule_to_fact_correctly_typed():
    document_id = _document_id()
    rule = _make_proposition(
        document_id, "Section 213 requires deposit protection.",
        proposition_type=PropositionType.rule, paragraph_ref="r1",
    )
    fact = _make_proposition(
        document_id, "Deposit was not protected within 30 days.",
        proposition_type=PropositionType.fact, paragraph_ref="f1",
    )
    edge = _make_edge(
        document_id, rule.proposition_id, fact.proposition_id,
        PropositionEdgeType.applies_rule_to_fact,
    )

    accepted, rejections = validate_graph(
        [edge], [rule, fact], expected_document_id=document_id,
    )

    assert accepted == [edge]
    assert rejections == []


def test_validate_graph_rejects_cites_to_non_authority():
    """fact cites fact: rejected."""
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")
    edge = _make_edge(
        document_id, p1.proposition_id, p2.proposition_id,
        PropositionEdgeType.cites,
    )

    accepted, rejections = validate_graph(
        [edge], [p1, p2], expected_document_id=document_id,
    )

    assert accepted == []
    assert len(rejections) == 1
    assert rejections[0].reason == "cites_target_not_authority"


def test_validate_graph_accepts_cites_to_authority():
    document_id = _document_id()
    rule = _make_proposition(
        document_id, "Section 213 requires deposit protection.",
        proposition_type=PropositionType.rule, paragraph_ref="r1",
    )
    auth = _make_proposition(
        document_id, "Cited Superstrike Ltd v Rodrigues [2013] EWCA Civ 669.",
        proposition_type=PropositionType.authority, paragraph_ref="a1",
    )
    edge = _make_edge(
        document_id, rule.proposition_id, auth.proposition_id,
        PropositionEdgeType.cites,
    )

    accepted, rejections = validate_graph(
        [edge], [rule, auth], expected_document_id=document_id,
    )

    assert accepted == [edge]
    assert rejections == []


def test_validate_graph_rejects_temporal_before_with_rule_endpoint():
    document_id = _document_id()
    rule = _make_proposition(
        document_id, "Section 213 requires deposit protection.",
        proposition_type=PropositionType.rule, paragraph_ref="r1",
    )
    fact = _make_proposition(
        document_id, "Deposit was paid in February.",
        proposition_type=PropositionType.fact, paragraph_ref="f1",
    )
    edge = _make_edge(
        document_id, rule.proposition_id, fact.proposition_id,
        PropositionEdgeType.temporal_before,
    )

    accepted, rejections = validate_graph(
        [edge], [rule, fact], expected_document_id=document_id,
    )

    assert accepted == []
    assert len(rejections) == 1
    assert rejections[0].reason == "temporal_before_endpoint_types"


def test_validate_graph_accepts_temporal_before_between_fact_and_outcome():
    document_id = _document_id()
    fact = _make_proposition(
        document_id, "Tenant moved out on date X.",
        proposition_type=PropositionType.fact, paragraph_ref="f1",
    )
    outcome = _make_proposition(
        document_id, "Tribunal ordered repayment.",
        proposition_type=PropositionType.outcome, paragraph_ref="o1",
    )
    edge = _make_edge(
        document_id, fact.proposition_id, outcome.proposition_id,
        PropositionEdgeType.temporal_before,
    )

    accepted, rejections = validate_graph(
        [edge], [fact, outcome], expected_document_id=document_id,
    )

    assert accepted == [edge]
    assert rejections == []


def test_validate_graph_rejects_cross_document_edge():
    expected = _document_id()
    other = deterministic_document_id("test://other", sha256_hex("other"))
    p1 = _make_proposition(expected, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(expected, "Fact two.", paragraph_ref="2")
    # Edge has the WRONG document id
    edge = PropositionEdge(
        edge_id=deterministic_edge_id(
            p1.proposition_id, p2.proposition_id, PropositionEdgeType.supports,
        ),
        from_proposition_id=p1.proposition_id,
        to_proposition_id=p2.proposition_id,
        document_id=other,
        edge_type=PropositionEdgeType.supports,
        rationale=None,
        confidence=0.9,
    )

    accepted, rejections = validate_graph(
        [edge], [p1, p2], expected_document_id=expected,
    )

    assert accepted == []
    assert len(rejections) == 1
    assert rejections[0].reason == "cross_document"


def test_validate_graph_returns_empty_for_empty_input():
    document_id = _document_id()
    accepted, rejections = validate_graph(
        [], [], expected_document_id=document_id,
    )
    assert accepted == []
    assert rejections == []
