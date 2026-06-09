"""Citation-cap must only fire when retrieval was attempted.

In kg_only / llm_only modes no RAG retrieval runs, so verified_citations is
always empty by construction. Applying the 0.4 cap in those modes manufactures
a degenerate Brier score and contradicts the design intent of cite-or-abstain.

Contract:
  _validate_prediction(prediction, verification, retrieval_attempted=False)
      → overall_confidence is NOT capped when has_non_uncertain_predictions
  _validate_prediction(prediction, verification, retrieval_attempted=True)
      → overall_confidence IS capped to 0.4  (existing behaviour)
"""
from __future__ import annotations

from llm_orchestrator.models.prediction_v2 import (
    EvidenceStrength,
    IssueOutcome,
    IssuePrediction,
    IssueType,
    OutcomeType,
    PipelineMetadata,
    PredictionResult,
    VerificationResult,
)
from llm_orchestrator.pipeline.output_assembler import OutputAssembler


def _make_prediction_result(overall_confidence: float = 0.85) -> PredictionResult:
    """A prediction with one confident non-uncertain issue."""
    issue_pred = IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="cleaning",
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=overall_confidence,
        reasoning="Strong evidence of cleaning.",
        evidence_strength=EvidenceStrength.STRONG,
        data_completeness_impact="OK",
    )
    return PredictionResult(
        case_id="test-cap-scope",
        overall_outcome=OutcomeType.TENANT_WIN,
        overall_confidence=overall_confidence,
        issue_predictions=[issue_pred],
        pipeline_metadata=PipelineMetadata(mode="kg_only"),
    )


def _make_empty_verification() -> VerificationResult:
    """No verified citations — simulates kg_only / llm_only modes."""
    return VerificationResult()


assembler = OutputAssembler()


def test_no_citation_cap_skipped_when_retrieval_not_attempted():
    """kg_only / llm_only: absence of citations must NOT cap overall_confidence."""
    prediction = _make_prediction_result(overall_confidence=0.85)
    verification = _make_empty_verification()
    assembler._validate_prediction(prediction, verification, retrieval_attempted=False)
    # Confidence must remain 0.85 — NOT capped to 0.4.
    assert prediction.overall_confidence == 0.85


def test_citation_cap_applies_when_retrieval_attempted():
    """hybrid / rag_only: absence of citations must cap overall_confidence to 0.4."""
    prediction = _make_prediction_result(overall_confidence=0.85)
    verification = _make_empty_verification()
    assembler._validate_prediction(prediction, verification, retrieval_attempted=True)
    # Confidence must be capped at 0.4.
    assert prediction.overall_confidence == 0.4


def _make_uncertain_prediction_result(overall_confidence: float = 0.75) -> PredictionResult:
    """A prediction whose only issue prediction is UNCERTAIN."""
    issue_pred = IssuePrediction(
        issue_type=IssueType.CLEANING,
        issue_description="cleaning",
        outcome=IssueOutcome.UNCERTAIN,
        raw_confidence=overall_confidence,
        reasoning="Insufficient evidence to determine outcome.",
        evidence_strength=EvidenceStrength.WEAK,
        data_completeness_impact="incomplete",
    )
    return PredictionResult(
        case_id="test-flip-uncertain-scope",
        overall_outcome=OutcomeType.UNCERTAIN,
        overall_confidence=overall_confidence,
        issue_predictions=[issue_pred],
        pipeline_metadata=PipelineMetadata(mode="kg_only"),
    )


def test_flip_to_uncertain_suppressed_when_retrieval_not_attempted():
    """kg_only / llm_only: all-UNCERTAIN predictions must NOT trigger the
    flip-to-UNCERTAIN branch when retrieval_attempted=False.

    The flip branch (lines 632-639 of output_assembler.py) is only meaningful
    in retrieval modes where an absence of citations is informative. In
    kg_only / llm_only modes it must be skipped so the prediction's outcome
    and confidence are left exactly as constructed.
    """
    prediction = _make_uncertain_prediction_result(overall_confidence=0.75)
    verification = _make_empty_verification()
    assembler._validate_prediction(prediction, verification, retrieval_attempted=False)
    # Both outcome and confidence must remain exactly as constructed.
    assert prediction.overall_outcome == OutcomeType.UNCERTAIN
    assert prediction.overall_confidence == 0.75
