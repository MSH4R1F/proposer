"""OutcomeComponent and RemedyComponent: per-issue prediction artifacts.

An ``OutcomeComponent`` links a per-issue outcome decision (e.g. the
``fault_finding`` outcome for the ``repairs_damp_mould`` claim head)
back to the supporting / mitigating factors and propositions that
justified that decision. The ``outcome_id`` references a single entry
in the domain pack's ``OutcomeSchema.outcomes[]`` (Stream B).

A ``RemedyComponent`` is the analogous artifact for a remedy decision.
In addition to the supporting-factor / proposition links, a remedy
component may carry a typed money value pair
(``money_minor_units`` + ``money_currency``). Per Hard Constraint #8
("money is a typed value, not a node"), the two money fields must be
set together — never one without the other. This invariant is enforced
by a Pydantic ``model_validator(mode="after")``.

Both models are leaf Pydantic v2 models with ``extra="forbid"`` and
``frozen=True`` to keep them safe to hash / cache and resistant to
accidental mutation downstream (e.g. while traversing the prediction
graph in PR 4 / PR 5 / PR 6).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §5 + §5.2
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OutcomeComponent(BaseModel):
    """Per-issue outcome decision linked to its supporting evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome_component_id: str
    outcome_id: str  # references OutcomeSchema.outcomes[].id from Stream B
    domain_id: str
    claim_head_id: str
    confidence: float = Field(ge=0.0, le=1.0)

    supporting_factor_ids: List[str] = Field(default_factory=list)
    mitigating_factor_ids: List[str] = Field(default_factory=list)
    supported_by_propositions: List[str] = Field(default_factory=list)


class RemedyComponent(BaseModel):
    """Per-issue remedy decision, optionally with a typed money amount."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    remedy_component_id: str
    remedy_id: str  # references RemedySchema.remedies[].id
    domain_id: str
    claim_head_id: str
    confidence: float = Field(ge=0.0, le=1.0)

    money_minor_units: Optional[int] = Field(default=None, ge=0)  # GBP pence
    money_currency: Optional[Literal["GBP"]] = None

    supporting_factor_ids: List[str] = Field(default_factory=list)
    supported_by_propositions: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_money_pair(self) -> "RemedyComponent":
        # Hard Constraint #8: money is a typed value, not a node.
        # Both money fields must be set together, or both omitted.
        units_set = self.money_minor_units is not None
        currency_set = self.money_currency is not None
        if units_set != currency_set:
            raise ValueError(
                "money_minor_units and money_currency must be set together "
                "(both present, or both omitted); "
                f"got money_minor_units={self.money_minor_units!r}, "
                f"money_currency={self.money_currency!r}"
            )
        return self
