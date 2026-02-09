"""
Prediction models for the outcome prediction engine.

Includes the PredictionResult with reasoning trace and citations.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class OutcomeType(str, Enum):
    """Possible outcomes of a tribunal decision."""
    TENANT_WIN = "tenant_win"
    LANDLORD_WIN = "landlord_win"
    SPLIT = "split"
    UNCERTAIN = "uncertain"


class Citation(BaseModel):
    """Citation to a specific tribunal case."""
    case_reference: str
    year: int
    region: Optional[str] = None
    paragraph: Optional[str] = None
    quote: str
    relevance: str  # Why this case is relevant
    similarity_score: float = Field(default=0.0, ge=0, le=1)


class ReasoningStep(BaseModel):
    """A single step in the reasoning trace."""
    step_number: int
    category: str  # issue_analysis, evidence_review, precedent_comparison, legal_principle, conclusion
    title: str
    content: str
    citations: List[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)


class IssuePrediction(BaseModel):
    """Prediction for a single dispute issue."""
    issue_type: str
    issue_description: str
    predicted_outcome: OutcomeType
    predicted_amount: Optional[float] = None
    amount_range: Optional[Tuple[float, float]] = None
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str
    key_factors: List[str] = Field(default_factory=list)
    supporting_cases: List[Citation] = Field(default_factory=list)


class PredictionResult(BaseModel):
    """
    Complete prediction with reasoning trace.

    This is the main output of the prediction engine,
    providing transparent, cited predictions.
    """
    case_id: str
    prediction_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Overall outcome
    overall_outcome: OutcomeType
    overall_confidence: float = Field(..., ge=0, le=1)
    outcome_summary: str = ""

    # Amount predictions
    tenant_recovery_amount: Optional[float] = None
    landlord_recovery_amount: Optional[float] = None
    predicted_settlement_range: Optional[Tuple[float, float]] = None
    deposit_at_stake: Optional[float] = None

    # Per-issue breakdown
    issue_predictions: List[IssuePrediction] = Field(default_factory=list)

    # Reasoning trace (for transparency)
    reasoning_trace: List[ReasoningStep] = Field(default_factory=list)

    # Key findings
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)

    # Uncertainties and caveats
    uncertainties: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    assumptions_made: List[str] = Field(default_factory=list)

    # Sources used
    retrieved_cases: List[str] = Field(default_factory=list)
    total_cases_analyzed: int = 0

    # Legal disclaimer
    disclaimer: str = Field(
        default=(
            "This prediction is based on analysis of similar First-tier Tribunal "
            "(Property Chamber) decisions and is provided for informational purposes "
            "only. It does not constitute legal advice. Actual tribunal outcomes may "
            "differ based on specific circumstances, evidence presented, and judicial "
            "discretion. We recommend seeking professional legal advice for your "
            "specific situation."
        )
    )

    # Calibration metadata
    model_version: str = "1.0.0"
    rag_confidence: float = Field(default=0.0, ge=0, le=1)
    retrieval_quality: str = "good"  # good, limited, poor

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_reasoning_step(
        self,
        category: str,
        title: str,
        content: str,
        citations: Optional[List[Citation]] = None,
        confidence: float = 0.8,
    ) -> ReasoningStep:
        """Add a step to the reasoning trace."""
        step = ReasoningStep(
            step_number=len(self.reasoning_trace) + 1,
            category=category,
            title=title,
            content=content,
            citations=citations or [],
            confidence=confidence,
        )
        self.reasoning_trace.append(step)
        return step

    def add_issue_prediction(
        self,
        issue_type: str,
        outcome: OutcomeType,
        confidence: float,
        reasoning: str,
        **kwargs,
    ) -> IssuePrediction:
        """Add an issue-level prediction."""
        prediction = IssuePrediction(
            issue_type=issue_type,
            issue_description=kwargs.get("issue_description", issue_type),
            predicted_outcome=outcome,
            confidence=confidence,
            reasoning=reasoning,
            **{k: v for k, v in kwargs.items() if k != "issue_description"},
        )
        self.issue_predictions.append(prediction)
        return prediction

    def get_citation_count(self) -> int:
        """Get total number of unique citations."""
        citations = set()
        for step in self.reasoning_trace:
            for c in step.citations:
                citations.add(c.case_reference)
        for pred in self.issue_predictions:
            for c in pred.supporting_cases:
                citations.add(c.case_reference)
        return len(citations)

    def to_summary(self) -> str:
        """Generate a human-readable summary of the prediction."""
        lines = [
            f"Prediction for Case {self.case_id}",
            f"=" * 40,
            f"",
            f"Overall Outcome: {self.overall_outcome.value.replace('_', ' ').title()}",
            f"Confidence: {self.overall_confidence:.0%}",
            f"",
        ]

        if self.outcome_summary:
            lines.append(self.outcome_summary)
            lines.append("")

        if self.predicted_settlement_range:
            low, high = self.predicted_settlement_range
            lines.append(f"Suggested Settlement Range: £{low:.2f} - £{high:.2f}")
            lines.append("")

        if self.issue_predictions:
            lines.append("Issue Breakdown:")
            for pred in self.issue_predictions:
                lines.append(
                    f"  - {pred.issue_type}: {pred.predicted_outcome.value} "
                    f"({pred.confidence:.0%} confidence)"
                )
            lines.append("")

        if self.key_strengths:
            lines.append("Key Strengths:")
            for s in self.key_strengths:
                lines.append(f"  + {s}")
            lines.append("")

        if self.key_weaknesses:
            lines.append("Key Weaknesses:")
            for w in self.key_weaknesses:
                lines.append(f"  - {w}")
            lines.append("")

        if self.uncertainties:
            lines.append("Uncertainties:")
            for u in self.uncertainties:
                lines.append(f"  ? {u}")
            lines.append("")

        lines.append(f"Based on analysis of {self.total_cases_analyzed} similar cases")
        lines.append(f"({self.get_citation_count()} directly cited)")
        lines.append("")
        lines.append("DISCLAIMER: " + self.disclaimer[:100] + "...")

        return "\n".join(lines)

    @classmethod
    def create_uncertain(
        cls,
        case_id: str,
        reason: str,
        missing_info: Optional[List[str]] = None,
    ) -> "PredictionResult":
        """Create an uncertain prediction when cite-or-abstain triggers."""
        return cls(
            case_id=case_id,
            overall_outcome=OutcomeType.UNCERTAIN,
            overall_confidence=0.0,
            outcome_summary=f"Unable to make a confident prediction: {reason}",
            reasoning_trace=[
                ReasoningStep(
                    step_number=1,
                    category="uncertainty",
                    title="Insufficient Information",
                    content=reason,
                    citations=[],
                    confidence=0.0,
                )
            ],
            uncertainties=[reason],
            missing_information=missing_info or [],
            retrieval_quality="poor",
        )
