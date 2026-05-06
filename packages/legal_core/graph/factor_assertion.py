"""FactorAssertion: central predictive node type (spec section 4).

A FactorAssertion is an evidence-grounded, typed legal factor extracted
from a case. It is the unit of analogical retrieval and predictive
reasoning. Every persisted factor must have at least one evidence span
unless the assertion was produced deterministically.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from legal_core.graph.factor_value import FactorValue, FactorValueType


class FactorPolarity(str, Enum):
    """Abstract polarity; domain packs render surface party labels."""

    PRO_CLAIMANT = "pro_claimant"
    PRO_RESPONDENT = "pro_respondent"
    NEUTRAL = "neutral"


class ExtractionMethod(str, Enum):
    """How the factor assertion was produced."""

    DETERMINISTIC = "deterministic"
    LLM_EXTRACTED = "llm_extracted"
    LLM_VERIFIED = "llm_verified"
    MANUAL_GOLD = "manual_gold"


class FactorAssertion(BaseModel):
    """Evidence-grounded legal factor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor_assertion_id: str
    factor_id: str
    domain_id: str
    claim_head_id: str

    value: FactorValue
    value_type: FactorValueType
    confidence: float = Field(ge=0.0, le=1.0)
    polarity: FactorPolarity

    expected_effects: List[str] = Field(default_factory=list)
    maps_to_outcomes: List[str] = Field(default_factory=list)
    maps_to_remedies: List[str] = Field(default_factory=list)

    supported_by: List[str] = Field(default_factory=list)
    refuted_by: List[str] = Field(default_factory=list)
    linked_events: List[str] = Field(default_factory=list)
    linked_issues: List[str] = Field(default_factory=list)
    source_span_refs: List[str] = Field(default_factory=list)

    extraction_method: ExtractionMethod
    extractor_version: str
    verifier_version: Optional[str] = None
    requires_human_review: bool = False

    @model_validator(mode="after")
    def _validate_consistency(self) -> "FactorAssertion":
        if self.value.value_type != self.value_type:
            raise ValueError(
                f"value_type={self.value_type.value!r} does not match "
                f"value.value_type={self.value.value_type.value!r}"
            )

        if (
            self.extraction_method is not ExtractionMethod.DETERMINISTIC
            and not self.supported_by
        ):
            raise ValueError(
                "non-deterministic factor assertions must have at least "
                "one EvidenceSpan id in supported_by"
            )

        if (
            self.extraction_method is ExtractionMethod.LLM_VERIFIED
            and not self.verifier_version
        ):
            raise ValueError(
                "extraction_method=llm_verified requires verifier_version"
            )

        return self
