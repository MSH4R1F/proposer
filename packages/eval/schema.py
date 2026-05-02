"""Gold-case schema for the evaluation harness.

See docs/eval/gold-schema.md for a human-readable description of fields,
allowed enum values, and the cross-field invariants enforced on GoldCase.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class RegionUK(str, Enum):
    """Closed enumeration of UK regions used by the stratification audit.

    Source PDF region strings vary ("London", "Greater London", "central
    London") so the schema stores the normalised enum value here and keeps
    the raw string in `GoldCase.region_source` for provenance.
    """

    LONDON = "london"
    SOUTH_EAST = "south_east"
    SOUTH_WEST = "south_west"
    EAST_OF_ENGLAND = "east_of_england"
    EAST_MIDLANDS = "east_midlands"
    WEST_MIDLANDS = "west_midlands"
    NORTH_WEST = "north_west"
    NORTH_EAST = "north_east"
    YORKSHIRE_AND_HUMBER = "yorkshire_and_humber"
    WALES = "wales"
    SCOTLAND = "scotland"
    NORTHERN_IRELAND = "northern_ireland"


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrictBaseModel):
    """Structured location of a quote, evidence item, or authority within
    the source PDF. Replaces the unstructured `paragraph_ref` strings that
    were unverifiable under noisy OCR (Codex finding [12] / SHA-100).

    `text_span` is `(char_start, char_end)` in the page's normalised text,
    optional because not every reference has a precise span.
    """

    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)
    text_span: Optional[Tuple[int, int]] = None

    @model_validator(mode="after")
    def _validate_text_span(self) -> "Provenance":
        if self.text_span is None:
            return self
        start, end = self.text_span
        if start < 0 or end < 0 or start >= end:
            raise ValueError(
                "text_span must be (char_start, char_end) with "
                "0 <= char_start < char_end"
            )
        return self


class Party(StrictBaseModel):
    role: PartyRole
    represented: bool


class Evidence(StrictBaseModel):
    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)
    provenance: Optional[Provenance] = None


class StatutoryReference(StrictBaseModel):
    statute: str = Field(min_length=1)
    section: str = Field(min_length=1)
    provenance: Optional[Provenance] = None


class Authority(StrictBaseModel):
    """A case-law authority cited by the tribunal in this decision.

    `cited_date` is the decision date of the *cited* authority (e.g. when
    the Supreme Court handed down `Howard de Walden Estates Ltd v Aggio`),
    not the date of the *current* case. The temporal-leakage audit
    (Phase 2 `dataset.audit()`) consumes this field: a training-set case
    must not cite any authority dated after the train-window cutoff.
    """

    name: str = Field(min_length=1)
    court: Optional[str] = None
    cited_date: date
    provenance: Optional[Provenance] = None


class ClaimedAmount(StrictBaseModel):
    issue: str = Field(min_length=1)
    amount_gbp: Decimal = Field(ge=0)
    by_party: PartyRole


class IssueOutcome(StrictBaseModel):
    issue: str = Field(min_length=1)
    winner: Winner
    awarded_gbp: Decimal = Field(ge=0)


class ReasoningQuote(StrictBaseModel):
    text: str = Field(min_length=1)
    provenance: Provenance


class GroundTruthOutcome(StrictBaseModel):
    """Ground-truth outcome of a tribunal decision.

    Two paths are permitted:

    * **Apportioned** (default): `per_issue` is non-empty, INV-6 enforces
      `total_awarded_gbp == sum(per_issue.awarded_gbp)` exactly.
    * **Unapportioned**: when `unapportioned_reason` is set, the tribunal
      gave a global figure with no per-issue breakdown. `per_issue` MUST
      be empty in this case; `total_awarded_gbp` is the only authoritative
      number; INV-5 (per-issue/claimed-amounts label match) is vacuously
      satisfied. Annotators must record *why* the decision is unapportioned
      so reviewers can re-check the source.
    """

    overall_winner: Winner
    total_awarded_gbp: Decimal = Field(ge=0)
    per_issue: list[IssueOutcome] = Field(default_factory=list)
    unapportioned_reason: Optional[str] = None

    @model_validator(mode="after")
    def _validate_apportionment(self) -> "GroundTruthOutcome":
        if self.unapportioned_reason is not None:
            if not self.unapportioned_reason.strip():
                raise ValueError("unapportioned_reason must be a non-empty string")
            if self.per_issue:
                raise ValueError(
                    "unapportioned_reason is set but per_issue is non-empty; "
                    "an unapportioned outcome must have per_issue=[]"
                )
            return self
        # Apportioned path
        if not self.per_issue:
            raise ValueError(
                "per_issue must contain >=1 item when unapportioned_reason is None"
            )
        s = sum((io.awarded_gbp for io in self.per_issue), start=Decimal("0"))
        if s != self.total_awarded_gbp:
            raise ValueError(
                f"total_awarded_gbp ({self.total_awarded_gbp}) "
                f"!= sum(per_issue.awarded_gbp) ({s})"
            )
        return self


class GoldCase(StrictBaseModel):
    """A single annotated tribunal case in the gold-standard evaluation set.

    Field-level constraints are declared inline. Cross-field invariants are
    enforced by `_validate_invariants` and documented in docs/eval/gold-schema.md
    as INV-1 through INV-8.
    """

    schema_version: SchemaVersion
    case_id: str = Field(min_length=1)
    decision_date: date
    region: RegionUK
    region_source: str = Field(default="", description="Verbatim region string from the source PDF; provenance only.")
    case_size: CaseSize
    disputed_amount_gbp: Decimal = Field(ge=0)
    claim_types: list[ClaimType] = Field(min_length=1)
    source_pdf_sha256: str
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    parties: list[Party] = Field(min_length=2)
    facts: str = Field(min_length=50)
    evidence: list[Evidence]
    evidence_unavailable_reason: Optional[str] = None
    statutory_basis: list[StatutoryReference]
    statutory_basis_unavailable_reason: Optional[str] = None
    cited_authorities: list[Authority] = Field(default_factory=list)
    claimed_amounts: list[ClaimedAmount] = Field(min_length=1)
    ground_truth_outcome: GroundTruthOutcome
    key_reasoning_quotes: list[ReasoningQuote] = Field(min_length=1)

    # ------------------------------------------------------------------
    # SHA-20 Phase 7 extensions. All fields are OPTIONAL/defaulted so
    # legacy ``housing_v1.jsonl`` rows continue to validate. New per-domain
    # gold sets populate them.
    #
    # See docs/eval/gold-schema.md and docs/eval/leakage_controls.md.
    # ------------------------------------------------------------------
    domain_id: Optional[str] = Field(
        default=None,
        description=(
            "DomainId of the gold case (e.g. 'housing.deposit.v1'). When "
            "set, leakage controls and per-domain metrics are activated."
        ),
    )
    forum: Optional[str] = Field(
        default=None,
        description="Forum value from domain_core.spec.Forum.",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Public URL of the source document, if known.",
    )
    source_license: Optional[str] = Field(
        default=None,
        description="License identifier (e.g. 'OGL-3.0', 'BAILII-terms').",
    )
    retrieval_namespace_id: Optional[str] = Field(
        default=None,
        description=(
            "Namespace_id from the domain spec; used by leakage controls "
            "to assert the gold case lines up with the chosen domain."
        ),
    )
    target_source_id: Optional[str] = Field(
        default=None,
        description=(
            "The source_id of the tribunal decision THIS gold case was "
            "derived from. MUST be excluded from retrieval at eval time."
        ),
    )
    excluded_source_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Additional source_ids that must be excluded (e.g. follow-up "
            "appeals, related cases sharing facts)."
        ),
    )
    law_effective_date: Optional[date] = Field(
        default=None,
        description=(
            "as_of_date for retrieval: only authorities with "
            "effective_date <= this date are admissible."
        ),
    )
    train_test_split: Optional[Literal["train", "test", "dev"]] = Field(
        default=None,
        description="Optional explicit split assignment.",
    )
    source_publisher: Optional[str] = Field(
        default=None,
        description="domain_core.spec.SourcePublisher value.",
    )
    source_kind: Optional[str] = Field(
        default=None,
        description="domain_core.spec.SourceKind value.",
    )
    corpus_version: Optional[str] = Field(
        default=None,
        description=(
            "Corpus version against which this gold case was annotated. "
            "Result hash captures this so reproducibility is auditable."
        ),
    )
    matter_type: Optional[str] = Field(
        default=None,
        description=(
            "SHA-20 audit D3 split (e.g. 'deposit_deduction' vs "
            "'deposit_non_protection'). Eval scores these separately."
        ),
    )
    negative_kind: Optional[str] = Field(
        default=None,
        description=(
            "When present, this row is part of a negative set "
            "(insufficient_evidence, wrong_forum, prompt_injection, "
            "temporal_leakage, pii_leakage, cross_domain_distractor, "
            "ambiguous_mixed). Engine should abstain or be tested for "
            "redaction; metrics treat the row specially."
        ),
    )
    expected_outcome: Optional[str] = Field(
        default=None,
        description=(
            "Free-form expected outcome label for negative-set rows "
            "(e.g. 'abstain', 'redact', 'select_correct_domain')."
        ),
    )
    expected_redactions: List[str] = Field(
        default_factory=list,
        description=(
            "For pii_leakage_v1 rows: identifiers that MUST be scrubbed "
            "from the model's trace and user-facing output."
        ),
    )
    expected_redacted_text: Optional[str] = Field(
        default=None,
        description=(
            "Optional verbatim expected redacted output for assertions."
        ),
    )

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
        if len(set(self.claim_types)) != len(self.claim_types):
            raise ValueError(
                "claim_types must not contain duplicates; each type should "
                "count at most once per case"
            )
        # INV-4: source_pdf_sha256 is 64 lowercase hex chars
        if not _SHA256_RE.match(self.source_pdf_sha256):
            raise ValueError(
                "source_pdf_sha256 must be 64 lowercase hex chars; "
                f"got {self.source_pdf_sha256!r}"
            )
        # INV-10: evidence and statutory_basis must each be non-empty OR carry
        # an explicit unavailability reason. Empty WITHOUT a reason is rejected
        # (silent omission risk per Codex finding [11] / SHA-99). Reason WITH
        # non-empty list is also rejected — reason is for empty lists only.
        if (
            self.evidence_unavailable_reason is not None
            and not self.evidence_unavailable_reason.strip()
        ):
            raise ValueError(
                "evidence_unavailable_reason must be a non-empty string"
            )
        if (
            self.statutory_basis_unavailable_reason is not None
            and not self.statutory_basis_unavailable_reason.strip()
        ):
            raise ValueError(
                "statutory_basis_unavailable_reason must be a non-empty string"
            )
        if self.evidence and self.evidence_unavailable_reason is not None:
            raise ValueError(
                "evidence is non-empty but evidence_unavailable_reason is set; "
                "the reason field is for empty lists only"
            )
        if not self.evidence and self.evidence_unavailable_reason is None:
            raise ValueError(
                "evidence is empty and no evidence_unavailable_reason given; "
                "annotators must record why evidence was not captured"
            )
        if self.statutory_basis and self.statutory_basis_unavailable_reason is not None:
            raise ValueError(
                "statutory_basis is non-empty but "
                "statutory_basis_unavailable_reason is set; "
                "the reason field is for empty lists only"
            )
        if not self.statutory_basis and self.statutory_basis_unavailable_reason is None:
            raise ValueError(
                "statutory_basis is empty and no "
                "statutory_basis_unavailable_reason given; annotators must "
                "record why statutes were not captured"
            )
        # INV-5: every per_issue.issue must appear in claimed_amounts
        # (vacuously satisfied when per_issue is empty under an unapportioned outcome)
        claimed_issues = {ca.issue for ca in self.claimed_amounts}
        for io in self.ground_truth_outcome.per_issue:
            if io.issue not in claimed_issues:
                raise ValueError(
                    f"ground_truth_outcome refers to issue {io.issue!r} "
                    f"not present in claimed_amounts {sorted(claimed_issues)}"
                )
        # INV-9: overall_winner consistent with the per_issue.winner aggregate.
        # Skipped when the outcome is unapportioned (no per_issue to aggregate against —
        # the annotator is asserting overall_winner directly, citing unapportioned_reason).
        if self.ground_truth_outcome.unapportioned_reason is None:
            winners = {io.winner for io in self.ground_truth_outcome.per_issue}
            expected_overall = (
                next(iter(winners)) if len(winners) == 1 else Winner.SPLIT
            )
            if self.ground_truth_outcome.overall_winner != expected_overall:
                raise ValueError(
                    f"overall_winner {self.ground_truth_outcome.overall_winner.value!r} "
                    f"inconsistent with per_issue winners "
                    f"{sorted(w.value for w in winners)} "
                    f"(expected {expected_overall.value!r})"
                )
        # INV-7: case_size consistent with the canonical disputed amount
        # (independent of mirrored claim/counterclaim entries in claimed_amounts)
        expected_size = (
            CaseSize.SMALL
            if self.disputed_amount_gbp <= _SMALL_CASE_THRESHOLD_GBP
            else CaseSize.LARGE
        )
        if self.case_size != expected_size:
            raise ValueError(
                f"case_size {self.case_size.value!r} inconsistent with "
                f"disputed_amount_gbp=GBP{self.disputed_amount_gbp} "
                f"(expected {expected_size.value!r})"
            )
        return self
