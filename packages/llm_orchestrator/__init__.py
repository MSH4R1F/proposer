"""
LLM Orchestrator Package

Provides conversational intake agents and prediction engine
for the legal mediation system.
"""

from .config import LLMConfig
from .models.case_file import CaseFile, PartyRole, DisputeIssue
from .models.prediction import PredictionResult, OutcomeType, IssueType, IssueOutcome


def __getattr__(name: str):
    if name == "PredictionEngineV2":
        from .pipeline.prediction_engine_v2 import PredictionEngineV2

        return PredictionEngineV2
    raise AttributeError(name)

__all__ = [
    "LLMConfig",
    "CaseFile",
    "PartyRole",
    "DisputeIssue",
    "PredictionResult",
    "OutcomeType",
    "IssueType",
    "IssueOutcome",
    "PredictionEngineV2",
]
