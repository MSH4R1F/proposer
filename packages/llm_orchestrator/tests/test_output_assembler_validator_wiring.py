"""Tests wiring EvidencePathValidator into output_assembler.assemble()
(Stream C PR 6 Task 6.2 / Cross-PR Contract C5)."""

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
# Fixtures (mirroring test_output_assembler_matter_split.py)
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
    issue_type: IssueType = IssueType.CLEANING,
    outcome: IssueOutcome = IssueOutcome.TENANT_WINS,
    amount: float | None = 200.0,
) -> IssuePrediction:
    return IssuePrediction(
        issue_type=issue_type,
        issue_description=issue_type.value,
        outcome=outcome,
        raw_confidence=0.7,
        predicted_amount=amount,
        reasoning="...",
        evidence_strength=EvidenceStrength.MODERATE,
        data_completeness_impact="OK",
    )


def _attach_outcome_components(
    pred: IssuePrediction, components: List[OutcomeComponent]
) -> None:
    """IssuePrediction's pydantic model doesn't have an outcome_components
    field yet; the validator reads it via getattr. Attach via
    object.__setattr__ to bypass Pydantic's attribute guard."""
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
# 1. Audit mode: results recorded but outcome unchanged
# ---------------------------------------------------------------------------


def test_audit_mode_records_results_no_outcome_change(monkeypatch):
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "0")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS)
    # OC references a factor that doesn't exist on any FA → rejected.
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

    # Validator results recorded.
    epr = result.pipeline_metadata.evidence_path_results
    assert len(epr) == 1
    assert epr[0]["outcome_component_id"] == "oc_bad"
    assert epr[0]["is_supported"] is False
    assert epr[0]["abstention_required"] is False  # audit mode
    # Outcome NOT forced uncertain.
    assert result.issue_predictions[0].outcome == IssueOutcome.TENANT_WINS


# ---------------------------------------------------------------------------
# 2. Strict mode: forces outcome to UNCERTAIN when chain rejected
# ---------------------------------------------------------------------------


def test_strict_mode_forces_uncertain_outcome_when_rejected(monkeypatch):
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "1")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS)
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

    epr = result.pipeline_metadata.evidence_path_results
    assert len(epr) == 1
    assert epr[0]["abstention_required"] is True
    # Outcome forced to UNCERTAIN.
    assert result.issue_predictions[0].outcome == IssueOutcome.UNCERTAIN


# ---------------------------------------------------------------------------
# 3. No case_graph → validator skipped, empty list emitted
# ---------------------------------------------------------------------------


def test_no_case_graph_skips_validator_emits_empty_list():
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS)
    # Even with outcome_components attached, no case_graph → validator skipped.
    oc = _make_outcome_component(
        oc_id="oc_x", supporting=["f"], supported_props=["p"]
    )
    _attach_outcome_components(pred, [oc])

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=[pred],
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="hybrid"),
        # case_graph not passed
    )

    assert result.pipeline_metadata.evidence_path_results == []
    assert result.issue_predictions[0].outcome == IssueOutcome.TENANT_WINS


# ---------------------------------------------------------------------------
# 4. Round-trip: evidence_path_results survives PredictionResult → dict
# ---------------------------------------------------------------------------


def test_evidence_path_results_round_trip_in_artifact(monkeypatch):
    monkeypatch.setenv("STREAM_C_EVIDENCE_PATH_STRICT", "0")
    cf = _make_case_file()
    issues = [_make_issue()]
    pred = _make_prediction(outcome=IssueOutcome.TENANT_WINS)
    # Wire a fully-supported OC so the recorded result is is_supported=True.
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

    # Direct access.
    epr = result.pipeline_metadata.evidence_path_results
    assert len(epr) == 1
    assert epr[0]["outcome_component_id"] == "oc_ok"
    assert epr[0]["is_supported"] is True

    # JSON round-trip preserves the field.
    payload = result.model_dump(mode="json")
    pmeta = payload["pipeline_metadata"]
    assert "evidence_path_results" in pmeta
    assert len(pmeta["evidence_path_results"]) == 1
    assert pmeta["evidence_path_results"][0]["is_supported"] is True
    assert pmeta["evidence_path_results"][0]["outcome_component_id"] == "oc_ok"
