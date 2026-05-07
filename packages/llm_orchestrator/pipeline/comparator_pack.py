"""ComparatorPack and supporting Pydantic v2 models.

Implements Cross-PR Contract C2 (output type for the new factor-constrained
retrieval path) per spec
``docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md``
section 9.3.

These models are the canonical interface returned by the factor retrieval
pipeline (Task 5.3) and consumed downstream by the prediction path. All models
are frozen and forbid extra fields to keep the contract immutable across PR
boundaries.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RankedProposition(BaseModel):
    """A proposition with its retrieval score and provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposition_id: str
    case_reference: str
    text: str
    source_passage: str  # verbatim quote
    authority_level: Literal[
        "statute",
        "regulation",
        "official_guidance",
        "binding_precedent",
        "persuasive",
        "comparator",
    ]
    proposition_role: Literal[
        "legal_test",
        "factual_finding",
        "fact_comparator",
        "remedy_rationale",
    ]
    score: float = Field(ge=0.0, le=1.0)
    score_breakdown: Dict[str, float]


class ComparatorPassMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    n_retrieved: int
    weights_used: Dict[str, float]  # comparator_weights snapshot
    fallback_reason: Optional[str] = None  # set if factor_retrieval falls back


class CounterexamplePassMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    n_retrieved: int
    k_overlap_min: int
    abstention_recommended: bool


class ComparatorPack(BaseModel):
    """Output of factor-constrained retrieval per spec section 9.3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    comparators: List[RankedProposition]  # positive analogues
    counterexamples: List[RankedProposition]  # differential analogues
    comparator_pass_metadata: ComparatorPassMetadata
    counterexample_pass_metadata: CounterexamplePassMetadata
