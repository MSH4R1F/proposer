"""Data models for the LLM orchestrator."""

from .case_file import (
    CaseFile,
    PartyRole,
    DisputeIssue,
    EvidenceType,
    EvidenceItem,
    ClaimedAmount,
    PropertyDetails,
    TenancyDetails,
)
from .conversation import ConversationState, Message, IntakeStage
from .prediction import (
    PredictionResult,
    OutcomeType,
    IssuePrediction,
    ReasoningStep,
    Citation,
    IssueType,
    IssueOutcome,
    EvidenceStrength,
    VerificationResult,
    PipelineMetadata,
    Counterfactual,
    RetrievalStrategy,
)

__all__ = [
    # Case file
    "CaseFile",
    "PartyRole",
    "DisputeIssue",
    "EvidenceType",
    "EvidenceItem",
    "ClaimedAmount",
    "PropertyDetails",
    "TenancyDetails",
    # Conversation
    "ConversationState",
    "Message",
    "IntakeStage",
    # Prediction
    "PredictionResult",
    "OutcomeType",
    "IssuePrediction",
    "ReasoningStep",
    "Citation",
    "IssueType",
    "IssueOutcome",
    "EvidenceStrength",
    "VerificationResult",
    "PipelineMetadata",
    "Counterfactual",
    "RetrievalStrategy",
]
