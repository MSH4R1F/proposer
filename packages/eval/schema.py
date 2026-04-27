"""Gold-case schema for the evaluation harness.

See docs/eval/gold-schema.md for a human-readable description of fields,
allowed enum values, and the cross-field invariants enforced on GoldCase.
"""
from __future__ import annotations

from datetime import date  # noqa: F401  -- referenced when GoldCase lands
from decimal import Decimal  # noqa: F401  -- referenced by sub-models
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SchemaVersion(str, Enum):
    V1 = "v1"


class ClaimType(str, Enum):
    CLEANING = "cleaning"
    DAMAGES = "damages"
    DEPOSIT_NON_PROTECTION = "deposit_non_protection"
    DISREPAIR = "disrepair"
    END_OF_TENANCY = "end_of_tenancy"


class CaseSize(str, Enum):
    SMALL = "small"
    LARGE = "large"


class PartyRole(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    AGENT = "agent"


class Winner(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    SPLIT = "split"


class Party(BaseModel):
    role: PartyRole
    represented: bool


class Evidence(BaseModel):
    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)
    paragraph_ref: Optional[str] = None


class StatutoryReference(BaseModel):
    statute: str = Field(min_length=1)
    section: str = Field(min_length=1)
    paragraph_ref: Optional[str] = None


class ClaimedAmount(BaseModel):
    issue: str = Field(min_length=1)
    amount_gbp: Decimal = Field(ge=0)
    by_party: PartyRole


class IssueOutcome(BaseModel):
    issue: str = Field(min_length=1)
    winner: Winner
    awarded_gbp: Decimal = Field(ge=0)


class ReasoningQuote(BaseModel):
    text: str = Field(min_length=1)
    paragraph_ref: str = Field(min_length=1)


class GroundTruthOutcome(BaseModel):
    overall_winner: Winner
    total_awarded_gbp: Decimal = Field(ge=0)
    per_issue: list[IssueOutcome] = Field(min_length=1)

    @model_validator(mode="after")
    def _total_matches_sum(self) -> "GroundTruthOutcome":
        s = sum((io.awarded_gbp for io in self.per_issue), start=Decimal("0"))
        if s != self.total_awarded_gbp:
            raise ValueError(
                f"total_awarded_gbp ({self.total_awarded_gbp}) "
                f"!= sum(per_issue.awarded_gbp) ({s})"
            )
        return self
