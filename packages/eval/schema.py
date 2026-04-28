"""Gold-case schema for the evaluation harness.

See docs/eval/gold-schema.md for a human-readable description of fields,
allowed enum values, and the cross-field invariants enforced on GoldCase.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MIN_DECISION_DATE = date(2019, 1, 1)
_MAX_DECISION_DATE = date(2024, 12, 31)
_SMALL_CASE_THRESHOLD_GBP = Decimal("1500")


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


class GoldCase(BaseModel):
    """A single annotated tribunal case in the gold-standard evaluation set.

    Field-level constraints are declared inline. Cross-field invariants are
    enforced by `_validate_invariants` and documented in docs/eval/gold-schema.md
    as INV-1 through INV-8.
    """

    schema_version: SchemaVersion
    case_id: str = Field(min_length=1)
    decision_date: date
    region: str = Field(min_length=1)
    case_size: CaseSize
    claim_types: list[ClaimType] = Field(min_length=1)
    source_pdf_sha256: str
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    parties: list[Party] = Field(min_length=2)
    facts: str = Field(min_length=50)
    evidence: list[Evidence]
    statutory_basis: list[StatutoryReference]
    claimed_amounts: list[ClaimedAmount] = Field(min_length=1)
    ground_truth_outcome: GroundTruthOutcome
    key_reasoning_quotes: list[ReasoningQuote] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_invariants(self) -> "GoldCase":
        # INV-1: decision_date in PILOT-permitted window
        if not (_MIN_DECISION_DATE <= self.decision_date <= _MAX_DECISION_DATE):
            raise ValueError(
                f"decision_date {self.decision_date} outside permitted "
                f"window [{_MIN_DECISION_DATE}, {_MAX_DECISION_DATE}]"
            )
        # INV-2: at least one tenant and one landlord
        roles = {p.role for p in self.parties}
        if PartyRole.TENANT not in roles or PartyRole.LANDLORD not in roles:
            raise ValueError(
                "parties must include at least one tenant and one landlord; "
                f"got roles={sorted(r.value for r in roles)}"
            )
        # INV-4: source_pdf_sha256 is 64 lowercase hex chars
        if not _SHA256_RE.match(self.source_pdf_sha256):
            raise ValueError(
                "source_pdf_sha256 must be 64 lowercase hex chars; "
                f"got {self.source_pdf_sha256!r}"
            )
        # INV-5: every per_issue.issue must appear in claimed_amounts
        claimed_issues = {ca.issue for ca in self.claimed_amounts}
        for io in self.ground_truth_outcome.per_issue:
            if io.issue not in claimed_issues:
                raise ValueError(
                    f"ground_truth_outcome refers to issue {io.issue!r} "
                    f"not present in claimed_amounts {sorted(claimed_issues)}"
                )
        # INV-7: case_size consistent with sum of claimed amounts
        total_claimed = sum(
            (ca.amount_gbp for ca in self.claimed_amounts), start=Decimal("0")
        )
        expected_size = (
            CaseSize.SMALL
            if total_claimed <= _SMALL_CASE_THRESHOLD_GBP
            else CaseSize.LARGE
        )
        if self.case_size != expected_size:
            raise ValueError(
                f"case_size {self.case_size.value!r} inconsistent with "
                f"total_claimed=GBP{total_claimed} (expected {expected_size.value!r})"
            )
        return self
