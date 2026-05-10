"""Tests that the evidence-path validator audits without vetoing the
prediction's outcome (Stream C recovery plan Task 3).

The previous behaviour under STREAM_C_EVIDENCE_PATH_STRICT=1 was to set
issue_pred.outcome = IssueOutcome.UNCERTAIN whenever
EvidencePathResult.abstention_required=True. The recovery plan reverses
this: the validator is now AUDIT-ONLY and never changes outcome. Strict
mode caps raw_confidence at 0.60 instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List
from uuid import uuid4

import pytest

from kg_builder.propositions.models import Proposition, PropositionType
from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from legal_core.graph.outcome_component import OutcomeComponent

from llm_orchestrator.models.case_file import CaseFile, PartyRole
from llm_orchestrator.models.prediction_v2 import (
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
    IssueType,
    PipelineMetadata,
    VerificationResult,
)
from llm_orchestrator.pipeline.output_assembler import OutputAssembler


# ---------------------------------------------------------------------------
# Fixtures (mirror test_output_assembler_validator_wiring.py)
# ---------------------------------------------------------------------------


@dataclass
class _FakeKG:
    factor_assertions: List[Any] = field(default_factory=list)
    propositions: List[Any] = field(default_factory=list)
    evidence_spans: List[Any] = field(default_factory=list)


def _make_case_file() -> CaseFile:
    cf = CaseFile(user_role=PartyRole.TENANT)
    cf.tenancy.deposit_amount = 1000.0
    cf.matter_types = ["deposit_deduction"]
    return cf


def _make_issue(
    issue_type: IssueType = IssueType.CLEANING, claimed: float | None = 200.0
) -> IssueContext:
    return IssueContext(
        issue_type=issue_type,
        issue_description=issue_type.value,
        claimed_amount=claimed,
        data_completeness=0.8,
    )


def _make_prediction(
    *,
    issue_type: IssueType = IssueType.CLEANING,
    outcome: IssueOutcome = IssueOutcome.TENANT_WINS,
    amount: float | None = 200.0,
    raw_confidence: float = 0.85,
) -> IssuePrediction:
    return IssuePrediction(
        issue_type=issue_type,
        issue_description=issue_type.value,
        outcome=outcome,
        raw_confidence=raw_confidence,
        predicted_amount=amount,
        reasoning="...",
        evidence_strength=EvidenceStrength.MODERATE,
        data_completeness_impact="OK",
    )


def _attach_outcome_components(
    pred: IssuePrediction, components: List[OutcomeComponent]
) -> None:
    object.__setattr__(pred, "outcome_components", components)


def _make_factor_assertion(factor_id: str, fa_id: str = "fa_1") -> FactorAssertion:
    return FactorAssertion(
        factor_assertion_id=fa_id,
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="ch_1",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.9,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=["span_1"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="test_extractor_v1",
        verifier_version="test_verifier_v1",
    )


def _make_proposition(factor_ids: List[str]) -> Proposition:
    return Proposition(
        proposition_id=uuid4(),
        document_id=uuid4(),
        case_reference="test-case",
        text="A proposition.",
        source_passage="A proposition appears in the source.",
        proposition_type=PropositionType.fact,
        confidence=0.85,
        factor_ids=list(factor_ids),
    )


def _make_outcome_component(
    *, oc_id: str, supporting: List[str], supported_props: List[str]
) -> OutcomeComponent:
    return OutcomeComponent(
        outcome_component_id=oc_id,
        outcome_id="fault_finding",
        domain_id="housing.repairs_social.v1",
        claim_head_id="ch_1",
        confidence=0.8,
        supporting_factor_ids=list(supporting),
        supported_by_propositions=list(supported_props),
    )


@pytest.fixture(autouse=True)
def _clean_strict_env(monkeypatch):
    monkeypatch.delenv("STREAM_C_EVIDENCE_PATH_STRICT", raising=False)
    yield


# ---------------------------------------------------------------------------
# 1. Audit mode: validator records but does NOT veto
# ---------------------------------------------------------------------------


def test_audit_mode_does_not_veto_outcome(monkeypatch):
    """STREAM_C_EVIDENCE_PATH_STRICT=0 (default): the validator records
    rejected chains but the outcome stays as the LLM produced; raw
    confidence is unchanged."""
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "0")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS, raw_confidence=0.85)
    oc = _make_outcome_component(
        oc_id="oc_bad", supporting=["unknown_factor"], supported_props=["bad-prop"]
    )
    _attach_outcome_components(pred, [oc])
    kg = _FakeKG(
        factor_assertions=[_make_factor_assertion("other_factor")],
        propositions=[],
        evidence_spans=["span_1"],
    )

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=[pred],
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="hybrid"),
        case_graph=kg,
    )

    # Outcome unchanged.
    assert result.issue_predictions[0].outcome == IssueOutcome.TENANT_WINS
    # Confidence unchanged in audit mode.
    assert result.issue_predictions[0].raw_confidence == pytest.approx(0.85)
    # Audit metadata still recorded.
    assert result.pipeline_metadata.evidence_support == "weak"
    assert result.pipeline_metadata.unsupported_claim_count == 1


# ---------------------------------------------------------------------------
# 2. Strict mode: caps confidence but does NOT veto
# ---------------------------------------------------------------------------


def test_strict_mode_caps_confidence_but_does_not_veto(monkeypatch):
    """STREAM_C_EVIDENCE_PATH_STRICT=1: the validator caps raw_confidence at
    0.60 on rejected chains and emits "weak" support metadata, but never
    flips outcome to UNCERTAIN."""
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "1")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS, raw_confidence=0.85)
    oc = _make_outcome_component(
        oc_id="oc_bad", supporting=["unknown_factor"], supported_props=["bad-prop"]
    )
    _attach_outcome_components(pred, [oc])
    kg = _FakeKG(
        factor_assertions=[_make_factor_assertion("other_factor")],
        propositions=[],
        evidence_spans=["span_1"],
    )

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=[pred],
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="hybrid"),
        case_graph=kg,
    )

    assert result.issue_predictions[0].outcome == IssueOutcome.TENANT_WINS
    assert result.issue_predictions[0].raw_confidence == pytest.approx(0.60)
    assert result.pipeline_metadata.evidence_support == "weak"
    assert result.pipeline_metadata.unsupported_claim_count == 1


# ---------------------------------------------------------------------------
# 3. Strict mode + low confidence: cap is a ceiling, not a floor
# ---------------------------------------------------------------------------


def test_strict_mode_leaves_low_confidence_alone(monkeypatch):
    """The 0.60 cap must not raise low confidence values."""
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "1")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS, raw_confidence=0.40)
    oc = _make_outcome_component(
        oc_id="oc_bad", supporting=["unknown_factor"], supported_props=["bad-prop"]
    )
    _attach_outcome_components(pred, [oc])
    kg = _FakeKG(
        factor_assertions=[_make_factor_assertion("other_factor")],
        propositions=[],
        evidence_spans=["span_1"],
    )

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=[pred],
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="hybrid"),
        case_graph=kg,
    )

    assert result.issue_predictions[0].raw_confidence == pytest.approx(0.40)
    assert result.pipeline_metadata.evidence_support == "weak"


# ---------------------------------------------------------------------------
# 4. All chains supported → evidence_support="strong"
# ---------------------------------------------------------------------------


def test_no_unsupported_chains_emits_strong_support(monkeypatch):
    """When every validated outcome_component closes its chain, metadata
    must record evidence_support="strong" and unsupported_claim_count=0."""
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "0")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS, raw_confidence=0.85)
    fa = _make_factor_assertion("f_1")
    prop = _make_proposition(["f_1"])
    oc = _make_outcome_component(
        oc_id="oc_ok",
        supporting=["f_1"],
        supported_props=[str(prop.proposition_id)],
    )
    _attach_outcome_components(pred, [oc])
    kg = _FakeKG(
        factor_assertions=[fa],
        propositions=[prop],
        evidence_spans=["span_1"],
    )

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=[pred],
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="hybrid"),
        case_graph=kg,
    )

    assert result.pipeline_metadata.evidence_support == "strong"
    assert result.pipeline_metadata.unsupported_claim_count == 0
    assert result.issue_predictions[0].outcome == IssueOutcome.TENANT_WINS
    assert result.issue_predictions[0].raw_confidence == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# 5. No outcome_components → evidence_support left as None
# ---------------------------------------------------------------------------


def test_no_evidence_path_results_leaves_support_none():
    """When no outcome_components are attached (or no case_graph), the
    validator emits an empty list and evidence_support must remain None."""
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS, raw_confidence=0.85)
    # Intentionally NO _attach_outcome_components call.
    kg = _FakeKG()

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=[pred],
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="hybrid"),
        case_graph=kg,
    )

    assert result.pipeline_metadata.evidence_path_results == []
    assert result.pipeline_metadata.evidence_support is None
    assert result.pipeline_metadata.unsupported_claim_count == 0
    assert result.issue_predictions[0].outcome == IssueOutcome.TENANT_WINS
