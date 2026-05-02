"""
Prediction models for the outcome prediction engine.

V2 models with backwards-compatible field aliases and import paths.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from .case_file import DisputeIssue

DateType = date


class OutcomeType(str, Enum):
    TENANT_WIN = "tenant_win"
    LANDLORD_WIN = "landlord_win"
    SPLIT = "split"
    UNCERTAIN = "uncertain"


class PredictionMode(str, Enum):
    """Ablation mode for PredictionEngineV2 (SHA-33).

    HYBRID — KG-aware retrieval + KG fact card in prompt (default production).
    RAG_ONLY — IssueDecomposer ignores KG; retrieval has no KG filter; no fact card.
    KG_ONLY — Skip RAG; LLM reasons from KG fact card + kg_constraints alone.
    LLM_ONLY — Skip both KG and RAG; bare CaseFile prompt (control baseline for SHA-68).
    """

    RAG_ONLY = "rag_only"
    KG_ONLY = "kg_only"
    HYBRID = "hybrid"
    LLM_ONLY = "llm_only"


class RetrievalStrategy(str, Enum):
    """Precedent retrieval strategy for PredictionEngineV2.

    Kept separate from PredictionMode so KG/RAG ablations do not turn into a
    combinatorial enum once proposition retrieval is evaluated.
    """

    CHUNK_RAG = "chunk_rag"
    PROPOSITION_DIRECT = "proposition_direct"
    PROPOSITION_PAGERANK = "proposition_pagerank"
    HYBRID_CHUNK_PROPOSITION = "hybrid_chunk_proposition"


IssueType = DisputeIssue


class IssueOutcome(str, Enum):
    TENANT_WINS = "tenant_wins"
    LANDLORD_WINS = "landlord_wins"
    SPLIT = "split"
    UNCERTAIN = "uncertain"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


def map_str_to_issue_type(value: str) -> IssueType:
    try:
        return IssueType(value)
    except ValueError:
        COMPAT_MAP = {
            "inventory_dispute": IssueType.INVENTORY,
            "decoration": IssueType.REDECORATION,
        }
        return COMPAT_MAP.get(value, IssueType.OTHER)


map_dispute_issue_to_issue_type = map_str_to_issue_type


class Citation(BaseModel):
    case_reference: str
    year: int
    region: Optional[str] = None
    paragraph: Optional[str] = None
    proposition_id: Optional[str] = None
    quote: str
    relevance: str
    similarity_score: float = Field(default=0.0, ge=0, le=1)
    verified: bool = False
    source_url: Optional[str] = None


class ReasoningStep(BaseModel):
    step_number: int
    category: str
    title: str
    content: str
    citations: List[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)


class Counterfactual(BaseModel):
    condition: str
    alternative_outcome: str
    confidence_shift: float


class IssuePrediction(BaseModel):
    """V2 per-issue prediction. REPLACES V1.
    Key changes: predicted_outcome→outcome, confidence→raw_confidence, issue_type is IssueType enum.
    Uses field aliases for backwards compat with V1 serialized JSON."""

    issue_type: IssueType
    issue_description: str = ""
    outcome: IssueOutcome = Field(..., validation_alias="predicted_outcome")
    raw_confidence: float = Field(..., ge=0, le=1, validation_alias="confidence")
    calibrated_confidence: Optional[float] = None
    predicted_amount: Optional[float] = None
    amount_range: Optional[Tuple[float, float]] = None
    reasoning: str = ""
    key_factors: List[str] = Field(default_factory=list)
    supporting_cases: List[Citation] = Field(default_factory=list)
    counterfactuals: List[Counterfactual] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.MODERATE
    data_completeness_impact: str = ""

    model_config = {"populate_by_name": True}


class ClaimDetail(BaseModel):
    party: str
    issue_type: IssueType
    claimed_amount: Optional[float] = None
    description: str = ""
    supporting_evidence_ids: List[str] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    date: Optional[DateType] = None
    description: str = ""
    source: str = ""
    relevance_to_issue: str = ""


class EvidenceConflict(BaseModel):
    issue_type: IssueType
    tenant_position: str = ""
    landlord_position: str = ""
    tenant_evidence_ids: List[str] = Field(default_factory=list)
    landlord_evidence_ids: List[str] = Field(default_factory=list)


class IssueContext(BaseModel):
    """Complete context for a single disputed issue."""

    issue_type: IssueType
    issue_description: str = ""
    tenant_claim: Optional[ClaimDetail] = None
    landlord_claim: Optional[ClaimDetail] = None
    supporting_evidence: List[Any] = Field(default_factory=list)
    timeline_events: List[TimelineEvent] = Field(default_factory=list)
    kg_constraints: List[str] = Field(default_factory=list)
    evidence_conflicts: List[EvidenceConflict] = Field(default_factory=list)
    claimed_amount: Optional[float] = None
    data_completeness: float = Field(default=0.0, ge=0, le=1)


class IssueRetrievalResult(BaseModel):
    issue_type: IssueType
    query_used: str = ""
    results: List[Any] = Field(default_factory=list)
    rag_confidence: float = 0.0
    temporal_distribution: Dict[int, int] = Field(default_factory=dict)
    legislative_regime: str = "current"
    is_sufficient: bool = False


class VerificationResult(BaseModel):
    verified_citations: List[Citation] = Field(default_factory=list)
    removed_citations: List[Citation] = Field(default_factory=list)
    removal_rate: float = 0.0
    needs_reprediction: bool = False
    all_citations_valid: bool = True


class PipelineMetadata(BaseModel):
    total_llm_calls: int = 0
    total_tokens_used: int = 0
    estimated_cost_gbp: float = 0.0
    total_latency_ms: int = 0
    steps_executed: List[str] = Field(default_factory=list)
    issues_decomposed: int = 0
    issues_with_sufficient_cases: int = 0
    fallbacks_used: List[str] = Field(default_factory=list)
    mode: str = "hybrid"  # PredictionMode value — surfaced in trace for SHA-68
    retrieval_strategy: str = RetrievalStrategy.CHUNK_RAG.value


class PredictionResult(BaseModel):
    case_id: str
    prediction_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    overall_outcome: OutcomeType
    overall_confidence: float = Field(..., ge=0, le=1)
    outcome_summary: str = ""

    tenant_recovery_amount: Optional[float] = None
    landlord_recovery_amount: Optional[float] = None
    predicted_settlement_range: Optional[Tuple[float, float]] = None
    deposit_at_stake: Optional[float] = None

    issue_predictions: List[IssuePrediction] = Field(default_factory=list)
    reasoning_trace: List[ReasoningStep] = Field(default_factory=list)

    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    assumptions_made: List[str] = Field(default_factory=list)

    retrieved_cases: List[str] = Field(default_factory=list)
    total_cases_analyzed: int = 0

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

    model_version: str = "2.0.0"
    rag_confidence: float = Field(default=0.0, ge=0, le=1)
    retrieval_quality: str = "good"

    pipeline_version: str = "v2"
    calibrated_confidence: Optional[float] = None
    confidence_calibrated: bool = False
    citation_verification: Optional[VerificationResult] = None
    temporal_distribution: Optional[Dict[int, int]] = None
    pipeline_metadata: Optional[PipelineMetadata] = None

    # SHA-20 Phase 3: domain routing metadata + reproducibility hashes.
    # These complement (and are repeated in) ``metadata["domain"]`` so that
    # the projection columns and the canonical payload stay in lock-step.
    domain_id: str = "housing.deposit.v1"
    domain_version: str = "v1"
    forum: Optional[str] = None
    matter_types: List[str] = Field(default_factory=list)
    routing_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    routing_metadata: Dict[str, Any] = Field(default_factory=dict)
    domain_spec_hash: Optional[str] = None
    prompt_pack_hash: Optional[str] = None
    ontology_hash: Optional[str] = None
    corpus_version: Optional[str] = None

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
        issue_type_enum = map_str_to_issue_type(issue_type)

        outcome_map = {
            OutcomeType.TENANT_WIN: IssueOutcome.TENANT_WINS,
            OutcomeType.LANDLORD_WIN: IssueOutcome.LANDLORD_WINS,
            OutcomeType.SPLIT: IssueOutcome.SPLIT,
            OutcomeType.UNCERTAIN: IssueOutcome.UNCERTAIN,
        }

        prediction = IssuePrediction(
            issue_type=issue_type_enum,
            issue_description=kwargs.get("issue_description", issue_type),
            outcome=outcome_map.get(outcome, IssueOutcome.UNCERTAIN),
            raw_confidence=confidence,
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
                    f"  - {pred.issue_type}: {pred.outcome.value} "
                    f"({pred.raw_confidence:.0%} confidence)"
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
