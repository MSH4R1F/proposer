"""Tests for EvidencePathValidator (Stream C PR 6 Task 6.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List
from uuid import uuid4

import pytest

from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from legal_core.graph.outcome_component import OutcomeComponent
from kg_builder.propositions.models import Proposition, PropositionType

from llm_orchestrator.pipeline.evidence_path_validator import (
    EvidencePathResult,
    EvidencePathValidator,
)


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeKG:
    """Stand-in for case_graph carrying the three node-type collections the
    validator reads. Mirrors the shape used in test_pr4_integration.py."""

    factor_assertions: List[Any] = field(default_factory=list)
    propositions: List[Any] = field(default_factory=list)
    evidence_spans: List[Any] = field(default_factory=list)


def _make_factor_assertion(
    *,
    factor_assertion_id: str,
    factor_id: str,
    supported_by: List[str] | None = None,
) -> FactorAssertion:
    return FactorAssertion(
        factor_assertion_id=factor_assertion_id,
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="ch_1",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.9,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=list(supported_by) if supported_by is not None else ["span_1"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="test_extractor_v1",
        verifier_version="test_verifier_v1",
    )


def _make_proposition(
    *,
    factor_ids: List[str],
    case_reference: str = "test-case-1",
    text: str = "Some atomic legal proposition.",
    source_passage: str = "Some atomic legal proposition appears in the text.",
) -> Proposition:
    """Build a Proposition with deterministic-but-unique ids."""
    return Proposition(
        proposition_id=uuid4(),
        document_id=uuid4(),
        case_reference=case_reference,
        text=text,
        source_passage=source_passage,
        proposition_type=PropositionType.fact,
        confidence=0.85,
        factor_ids=list(factor_ids),
    )


def _make_outcome_component(
    *,
    outcome_component_id: str = "oc_1",
    supporting_factor_ids: List[str] | None = None,
    supported_by_propositions: List[str] | None = None,
) -> OutcomeComponent:
    return OutcomeComponent(
        outcome_component_id=outcome_component_id,
        outcome_id="fault_finding",
        domain_id="housing.repairs_social.v1",
        claim_head_id="ch_1",
        confidence=0.8,
        supporting_factor_ids=list(supporting_factor_ids or []),
        supported_by_propositions=list(supported_by_propositions or []),
    )


@pytest.fixture(autouse=True)
def _clean_strict_env(monkeypatch):
    """Default to audit mode in every test; tests opt into strict mode
    explicitly via monkeypatch.setenv."""
    monkeypatch.delenv("STREAM_C_EVIDENCE_PATH_STRICT", raising=False)
    yield


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_complete_chain_validates():
    fa = _make_factor_assertion(
        factor_assertion_id="fa_1",
        factor_id="repair_responsibility_established",
        supported_by=["span_resp_1"],
    )
    prop = _make_proposition(factor_ids=["repair_responsibility_established"])
    oc = _make_outcome_component(
        outcome_component_id="oc_repair",
        supporting_factor_ids=["repair_responsibility_established"],
        supported_by_propositions=[str(prop.proposition_id)],
    )
    kg = _FakeKG(
        factor_assertions=[fa],
        propositions=[prop],
        evidence_spans=["span_resp_1"],
    )

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert isinstance(result, EvidencePathResult)
    assert result.is_supported is True
    assert result.rejection_reason is None
    assert result.abstention_required is False
    assert len(result.chain) == 4
    assert result.chain[0] == "span_resp_1"
    assert result.chain[1] == "fa_1"
    assert result.chain[2] == str(prop.proposition_id)
    assert result.chain[3] == "oc_repair"


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


def test_missing_factor_assertion_rejects():
    """OC's supporting_factor_ids reference a factor_id no FA has."""
    fa = _make_factor_assertion(
        factor_assertion_id="fa_1",
        factor_id="some_other_factor",
        supported_by=["span_1"],
    )
    prop = _make_proposition(factor_ids=["missing_factor"])
    oc = _make_outcome_component(
        outcome_component_id="oc_1",
        supporting_factor_ids=["missing_factor"],
        supported_by_propositions=[str(prop.proposition_id)],
    )
    kg = _FakeKG(factor_assertions=[fa], propositions=[prop], evidence_spans=["span_1"])

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert "oc_1" in (result.rejection_reason or "")
    assert result.chain == []


def test_missing_proposition_rejects():
    """OC's supported_by_propositions references a prop_id no proposition has."""
    fa = _make_factor_assertion(
        factor_assertion_id="fa_1",
        factor_id="f_1",
        supported_by=["span_1"],
    )
    oc = _make_outcome_component(
        outcome_component_id="oc_orphan",
        supporting_factor_ids=["f_1"],
        supported_by_propositions=["00000000-0000-0000-0000-000000000000"],
    )
    kg = _FakeKG(factor_assertions=[fa], propositions=[], evidence_spans=["span_1"])

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert result.rejection_reason is not None
    assert "oc_orphan" in result.rejection_reason


def test_factor_assertion_without_evidence_rejects():
    """FactorAssertion with empty supported_by must NOT yield a valid chain.

    Constructing a FactorAssertion with empty supported_by requires the
    DETERMINISTIC extraction method (the model rejects empty supported_by
    for non-deterministic methods)."""
    fa = FactorAssertion(
        factor_assertion_id="fa_no_ev",
        factor_id="f_1",
        domain_id="d",
        claim_head_id="ch",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.9,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=[],  # ← no evidence
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extractor_version="test",
    )
    prop = _make_proposition(factor_ids=["f_1"])
    oc = _make_outcome_component(
        outcome_component_id="oc_no_ev",
        supporting_factor_ids=["f_1"],
        supported_by_propositions=[str(prop.proposition_id)],
    )
    kg = _FakeKG(factor_assertions=[fa], propositions=[prop], evidence_spans=[])

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert result.chain == []


def test_cycle_detection_doesnt_loop():
    """Visited tracking prevents infinite loops if the OC declares the same
    proposition id twice in supported_by_propositions."""
    fa = _make_factor_assertion(
        factor_assertion_id="fa_1",
        factor_id="f_no_match",
        supported_by=["span_1"],
    )
    # Proposition's factor_ids does NOT include any of OC's supporting_factor_ids,
    # so each visit fails to find a chain and we walk to the next prop.
    prop = _make_proposition(factor_ids=["unrelated_factor"])
    pid = str(prop.proposition_id)
    oc = _make_outcome_component(
        outcome_component_id="oc_cycle",
        supporting_factor_ids=["f_target"],
        supported_by_propositions=[pid, pid, pid],  # repeated ids
    )
    kg = _FakeKG(factor_assertions=[fa], propositions=[prop], evidence_spans=["span_1"])

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    # Should reject (no chain found) without spinning forever.
    assert result.is_supported is False
    assert result.rejection_reason is not None


# ---------------------------------------------------------------------------
# Audit vs. strict mode
# ---------------------------------------------------------------------------


def test_audit_mode_abstention_required_false_when_rejected(monkeypatch):
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "0")
    oc = _make_outcome_component(
        outcome_component_id="oc_x",
        supporting_factor_ids=["f"],
        supported_by_propositions=["bad-prop-id"],
    )
    kg = _FakeKG(
        factor_assertions=[_make_factor_assertion(
            factor_assertion_id="fa_1", factor_id="other", supported_by=["s"]
        )],
        propositions=[],
        evidence_spans=["s"],
    )

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert result.abstention_required is False


def test_strict_mode_abstention_required_true_when_rejected(monkeypatch):
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "1")
    oc = _make_outcome_component(
        outcome_component_id="oc_x",
        supporting_factor_ids=["f"],
        supported_by_propositions=["bad-prop-id"],
    )
    kg = _FakeKG(
        factor_assertions=[_make_factor_assertion(
            factor_assertion_id="fa_1", factor_id="other", supported_by=["s"]
        )],
        propositions=[],
        evidence_spans=["s"],
    )

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert result.abstention_required is True


def test_strict_mode_abstention_required_false_when_supported(monkeypatch):
    """Even in strict mode, a successful chain → abstention_required=False."""
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "1")
    fa = _make_factor_assertion(
        factor_assertion_id="fa_1", factor_id="f_1", supported_by=["span_x"]
    )
    prop = _make_proposition(factor_ids=["f_1"])
    oc = _make_outcome_component(
        outcome_component_id="oc_ok",
        supporting_factor_ids=["f_1"],
        supported_by_propositions=[str(prop.proposition_id)],
    )
    kg = _FakeKG(
        factor_assertions=[fa], propositions=[prop], evidence_spans=["span_x"]
    )

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is True
    assert result.abstention_required is False


# ---------------------------------------------------------------------------
# Empty / missing case graph
# ---------------------------------------------------------------------------


def test_empty_case_graph_rejects_with_reason():
    oc = _make_outcome_component(
        outcome_component_id="oc_e",
        supporting_factor_ids=["f"],
        supported_by_propositions=["p"],
    )
    kg = _FakeKG()

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert "case_graph is empty" in (result.rejection_reason or "")


def test_none_case_graph_rejects_with_reason():
    oc = _make_outcome_component(
        outcome_component_id="oc_n",
        supporting_factor_ids=["f"],
        supported_by_propositions=["p"],
    )

    result = EvidencePathValidator(case_graph=None).validate_outcome_component(oc)

    assert result.is_supported is False
    assert "case_graph is None" in (result.rejection_reason or "")


def test_oc_with_no_factors_or_props_rejects():
    fa = _make_factor_assertion(
        factor_assertion_id="fa_1", factor_id="f", supported_by=["s"]
    )
    kg = _FakeKG(factor_assertions=[fa], propositions=[], evidence_spans=["s"])
    oc = _make_outcome_component(
        outcome_component_id="oc_empty",
        supporting_factor_ids=[],
        supported_by_propositions=[],
    )

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is False
    assert "neither" in (result.rejection_reason or "")


def test_validator_uses_first_supporting_evidence_span():
    """When the FA has multiple supported_by spans, the chain takes the first."""
    fa = _make_factor_assertion(
        factor_assertion_id="fa_multi",
        factor_id="f_1",
        supported_by=["span_first", "span_second", "span_third"],
    )
    prop = _make_proposition(factor_ids=["f_1"])
    oc = _make_outcome_component(
        outcome_component_id="oc_multi",
        supporting_factor_ids=["f_1"],
        supported_by_propositions=[str(prop.proposition_id)],
    )
    kg = _FakeKG(
        factor_assertions=[fa],
        propositions=[prop],
        evidence_spans=["span_first", "span_second", "span_third"],
    )

    result = EvidencePathValidator(case_graph=kg).validate_outcome_component(oc)

    assert result.is_supported is True
    assert result.chain[0] == "span_first"


def test_evidence_path_result_is_frozen():
    result = EvidencePathResult(
        outcome_component_id="oc_x",
        is_supported=True,
        chain=["a", "b", "c", "d"],
    )
    with pytest.raises(Exception):
        result.is_supported = False  # type: ignore[misc]
