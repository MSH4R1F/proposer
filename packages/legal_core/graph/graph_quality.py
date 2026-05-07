"""GraphQualityScore: per-case KG quality gate output (spec section 8).

Per-domain thresholds live on the domain pack, not in this module. This is
the shape of the score; the gate decision is computed elsewhere by the
domain pack's quality policy.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GraphQualityScore(BaseModel):
    """Per-case KG quality measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=0.0, le=1.0)

    evidence_backed_factor_count: int = Field(ge=0)
    dated_event_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    outcome_or_remedy_candidate_count: int = Field(ge=0)

    unsupported_factor_rate: float = Field(ge=0.0, le=1.0)
    source_span_coverage: float = Field(ge=0.0, le=1.0)
    contradiction_count: int = Field(ge=0)

    usable_for_prediction: bool
    failure_reasons: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_failure_reasons(self) -> "GraphQualityScore":
        if not self.usable_for_prediction and not self.failure_reasons:
            raise ValueError(
                "usable_for_prediction=False requires at least one entry in "
                "failure_reasons"
            )
        if self.usable_for_prediction and self.failure_reasons:
            raise ValueError(
                "usable_for_prediction=True forbids non-empty failure_reasons; "
                f"got {self.failure_reasons!r}"
            )
        return self
