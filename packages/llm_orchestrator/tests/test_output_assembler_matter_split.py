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
    IssueType,
    PipelineMetadata,
    VerificationResult,
)
from llm_orchestrator.pipeline.output_assembler import OutputAssembler


def _make_case_file(*, deposit: float, matter_type: str | None) -> CaseFile:
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
    amount: float,
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
