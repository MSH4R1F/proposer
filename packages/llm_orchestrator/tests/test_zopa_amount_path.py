"""RQ2 review point 3: a non-uncertain predicted_amount must flow through the
OutputAssembler into the top-level recovery/settlement-range fields that
``compute_zopa`` reads, yielding a NON-degenerate ZOPA — for a repairs case
with no deposit (the domain where it currently collapses).
"""
from __future__ import annotations

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
from llm_orchestrator.tools.mediator._calculations import compute_zopa


def _assemble(outcome: IssueOutcome, amount: float | None):
    cf = CaseFile(user_role=PartyRole.TENANT)
    cf.tenancy.deposit_amount = None  # repairs: no deposit anchor
    cf.matter_types = ["repairs_damp_mould"]
    issues = [
        IssueContext(
            issue_type=IssueType.REPAIRS_DAMP_MOULD,
            issue_description="damp and mould",
            data_completeness=0.8,
        )
    ]
    predictions = [
        IssuePrediction(
            issue_type=IssueType.REPAIRS_DAMP_MOULD,
            issue_description="damp and mould",
            outcome=outcome,
            raw_confidence=0.7,
            predicted_amount=amount,
            reasoning="...",
            evidence_strength=EvidenceStrength.MODERATE,
        )
    ]
    return OutputAssembler().assemble(
        case_file=cf,
        issues=issues,
        issue_predictions=predictions,
        retrieval_results={},
        verification=VerificationResult(),
        pipeline_metadata=PipelineMetadata(mode="rag_only"),
    )


def test_non_uncertain_amount_yields_nondegenerate_zopa():
    result = _assemble(IssueOutcome.TENANT_WINS, 500.0)

    # The per-issue amount propagates to the top-level fields compute_zopa reads.
    assert result.tenant_recovery_amount == 500.0
    assert result.predicted_settlement_range == (425.0, 575.0)

    zopa = compute_zopa(result)
    assert zopa["center"] == 500.0
    assert zopa["max"] > zopa["min"] > 0  # NON-degenerate


def test_uncertain_amount_is_skipped_and_zopa_collapses():
    # Documents the caveat: an UNCERTAIN issue's amount is dropped by the
    # assembler, so the ZOPA still collapses even with predicted_amount set.
    result = _assemble(IssueOutcome.UNCERTAIN, 500.0)

    assert result.predicted_settlement_range is None
    assert result.tenant_recovery_amount is None

    zopa = compute_zopa(result)
    assert zopa == {"min": 0.0, "max": 0.0, "center": 0.0}
