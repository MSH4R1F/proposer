"""Audit D3: matter_type-aware deposit-protection routing in OutputAssembler.

Before Phase 6, every IssueType.DEPOSIT_PROTECTION outcome routed through the
1x-3x penalty branch. That bundled deposit_deduction (deposit-scheme
adjudication: issue-by-issue recovery) and deposit_non_protection (county
court statutory penalty) into one numeric path, which hid the audit-D3 split.

These tests exercise both branches end-to-end through ``OutputAssembler``.
"""

from __future__ import annotations

from llm_orchestrator.models.case_file import CaseFile, DisputeIssue, PartyRole
from llm_orchestrator.models.prediction_v2 import (
    EvidenceStrength,
    IssueContext,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
    PipelineMetadata,
    VerificationResult,
)
from llm_orchestrator.pipeline.output_assembler import OutputAssembler


def _make_case_file(*, deposit: float | None, matter_type: str | None) -> CaseFile:
    cf = CaseFile(user_role=PartyRole.TENANT)
    cf.tenancy.deposit_amount = deposit
    if matter_type is not None:
        cf.matter_types = [matter_type]
    return cf


def _make_issue(issue_type: IssueType, claimed: float | None = None) -> IssueContext:
    return IssueContext(
        issue_type=issue_type,
        issue_description=issue_type.value,
        claimed_amount=claimed,
        data_completeness=0.8,
    )


def _make_prediction(
    issue_type: IssueType,
    outcome: IssueOutcome,
    amount: float | None,
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


def _empty_metadata() -> PipelineMetadata:
    return PipelineMetadata(mode="hybrid")


# ---------------------------------------------------------------------------
# deposit_non_protection — penalty branch.
# ---------------------------------------------------------------------------


def test_deposit_non_protection_routes_through_penalty_branch():
    cf = _make_case_file(deposit=1000.0, matter_type="deposit_non_protection")
    issues = [_make_issue(IssueType.DEPOSIT_PROTECTION)]
    predictions = [
        _make_prediction(
            IssueType.DEPOSIT_PROTECTION, IssueOutcome.TENANT_WINS, 3000.0
        )
    ]
    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
    )
    assert result.metadata["matter_type"] == "deposit_non_protection"
    # Penalty was added on top of the deposit cap → tenant_recovery > deposit.
    assert result.metadata["penalty_recovery"] == 3000.0
    assert result.tenant_recovery_amount >= 3000.0


# ---------------------------------------------------------------------------
# deposit_deduction — standard recovery branch (NO penalty).
# ---------------------------------------------------------------------------


def test_deposit_deduction_does_not_route_through_penalty_branch():
    """Audit D3: a deposit_deduction prediction must not produce penalty_recovery > 0.

    Even if the LLM produced a DEPOSIT_PROTECTION-typed issue prediction with
    a £3,000 amount, the matter_type signal must keep us on the standard
    issue-by-issue recovery branch (capped at the deposit).
    """
    cf = _make_case_file(deposit=1000.0, matter_type="deposit_deduction")
    issues = [_make_issue(IssueType.DEPOSIT_PROTECTION)]
    predictions = [
        _make_prediction(
            IssueType.DEPOSIT_PROTECTION, IssueOutcome.TENANT_WINS, 3000.0
        )
    ]
    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
    )
    assert result.metadata["matter_type"] == "deposit_deduction"
    assert result.metadata["penalty_recovery"] == 0.0
    # Recovery is capped at the deposit (no penalty stacked on top).
    assert result.tenant_recovery_amount <= 1000.0


# ---------------------------------------------------------------------------
# Backwards compat: missing matter_type defaults to deposit_deduction.
# ---------------------------------------------------------------------------


def test_missing_matter_type_defaults_to_deposit_deduction():
    cf = _make_case_file(deposit=1000.0, matter_type=None)
    issues = [
        _make_issue(IssueType.CLEANING, claimed=200.0),
        _make_issue(IssueType.DEPOSIT_PROTECTION),
    ]
    predictions = [
        _make_prediction(IssueType.CLEANING, IssueOutcome.TENANT_WINS, 200.0),
        _make_prediction(
            IssueType.DEPOSIT_PROTECTION, IssueOutcome.TENANT_WINS, 3000.0
        ),
    ]
    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
    )
    assert result.metadata["matter_type"] == "deposit_deduction"
    assert result.metadata["penalty_recovery"] == 0.0


# ---------------------------------------------------------------------------
# Explicit matter_type kwarg wins over case_file metadata.
# ---------------------------------------------------------------------------


def test_explicit_matter_type_kwarg_overrides_case_file():
    cf = _make_case_file(deposit=1000.0, matter_type="deposit_deduction")
    issues = [_make_issue(IssueType.DEPOSIT_PROTECTION)]
    predictions = [
        _make_prediction(
            IssueType.DEPOSIT_PROTECTION, IssueOutcome.TENANT_WINS, 3000.0
        )
    ]
    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
        matter_type="deposit_non_protection",
    )
    assert result.metadata["matter_type"] == "deposit_non_protection"
    assert result.metadata["penalty_recovery"] == 3000.0


def test_missing_predicted_amount_preserves_unknown_recovery():
    cf = _make_case_file(deposit=None, matter_type="repairs_damp_mould")
    issues = [_make_issue(IssueType.REPAIRS_DAMP_MOULD)]
    predictions = [
        _make_prediction(IssueType.REPAIRS_DAMP_MOULD, IssueOutcome.TENANT_WINS, None)
    ]

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
    )

    assert result.tenant_recovery_amount is None
    assert result.landlord_recovery_amount is None
    assert result.predicted_settlement_range is None
    assert "Monetary remedy amount unknown" in result.outcome_summary


def test_explicit_zero_predicted_amount_remains_zero_not_unknown():
    cf = _make_case_file(deposit=None, matter_type="repairs_damp_mould")
    issues = [_make_issue(IssueType.REPAIRS_DAMP_MOULD)]
    predictions = [
        _make_prediction(IssueType.REPAIRS_DAMP_MOULD, IssueOutcome.TENANT_WINS, 0.0)
    ]

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
    )

    assert result.tenant_recovery_amount == 0.0
    assert result.landlord_recovery_amount == 0.0
    assert result.predicted_settlement_range == (0.0, 0.0)


def test_retrieval_evidence_is_persisted_on_prediction_result():
    cf = _make_case_file(deposit=None, matter_type="repairs_damp_mould")
    issues = [_make_issue(IssueType.REPAIRS_DAMP_MOULD)]
    predictions = [
        _make_prediction(IssueType.REPAIRS_DAMP_MOULD, IssueOutcome.TENANT_WINS, 250.0)
    ]
    retrieval = IssueRetrievalResult(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        query_used="damp mould | REMEDY PASS: ordered the landlord must pay",
        rag_confidence=0.8,
        temporal_distribution={2024: 1},
        legislative_regime="current",
        is_sufficient=True,
        results=[
            {
                "chunk_id": "chunk-123",
                "source_id": "source-123",
                "source_kind": "ombudsman_decision",
                "case_reference": "housing-ombudsman-202400001",
                "year": 2024,
                "paragraph": "42",
                "section_type": "orders",
                "combined_score": 0.77,
                "semantic_score": 0.66,
                "bm25_score": 2.5,
                "repairs_issue_match_score": 0.75,
                "ombudsman_outcome_signal_score": 1.0,
                "chunk_text": "What the landlord must do: pay £250 compensation.",
            }
        ],
    )

    result = OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={IssueType.REPAIRS_DAMP_MOULD: retrieval},
        verification=VerificationResult(),
        pipeline_metadata=_empty_metadata(),
    )

    evidence = result.retrieval_evidence["repairs_damp_mould"]
    assert evidence["query_used"].startswith("damp mould")
    assert evidence["is_sufficient"] is True
    assert evidence["results"][0]["chunk_id"] == "chunk-123"
    assert evidence["results"][0]["section_type"] == "orders"
    assert "£250 compensation" in evidence["results"][0]["text_preview"]
