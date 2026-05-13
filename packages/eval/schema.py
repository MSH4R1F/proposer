"""Gold-case schema for the evaluation harness.

See docs/eval/gold-schema.md for a human-readable description of fields,
allowed enum values, and the cross-field invariants enforced on GoldCase.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MIN_DECISION_DATE = date(2019, 1, 1)
_MAX_DECISION_DATE = date(2024, 12, 31)
_DOMAIN_MAX_DECISION_DATE = {
    # The social-repairs Ombudsman research seed scraped in May 2026 contains
    # real 2025/2026 determinations. Keep the legacy pilot window for all
    # other domains, but do not force false dates onto this domain's gold rows.
    "housing.repairs_social.v1": date(2026, 5, 4),
}
_SMALL_CASE_THRESHOLD_GBP = Decimal("1500")


class SchemaVersion(str, Enum):
    V1 = "v1"


class ClaimType(str, Enum):
    # Housing values (deposit + repairs_social verticals).
    CLEANING = "cleaning"
    DAMAGES = "damages"
    DEPOSIT_NON_PROTECTION = "deposit_non_protection"
    DISREPAIR = "disrepair"
    END_OF_TENANCY = "end_of_tenancy"
    # Employment values (SHA-65 vertical). v1 covers unfair dismissal only.
    UNFAIR_DISMISSAL = "unfair_dismissal"


class CaseSize(str, Enum):
    SMALL = "small"
    LARGE = "large"
    UNKNOWN = "unknown"


class PartyRole(str, Enum):
    # Housing values.
    TENANT = "tenant"
    LANDLORD = "landlord"
    AGENT = "agent"
    # Employment values (SHA-65 vertical).
    CLAIMANT = "claimant"
    RESPONDENT_EMPLOYER = "respondent_employer"


class Winner(str, Enum):
    # Housing values.
    TENANT = "tenant"
    LANDLORD = "landlord"
    # Employment values.
    CLAIMANT = "claimant"
    RESPONDENT = "respondent"
    # Forum-neutral.
    SPLIT = "split"


class Determination(str, Enum):
    """Substantive finding on a single complaint head.

    Housing Ombudsman values (legacy — see
    ``docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md``):

    * ``maladministration``, ``severe_maladministration``, ``service_failure``
      indicate the Ombudsman found against the landlord on the merits and
      typically issues a binding compensation order.
    * ``reasonable_redress`` indicates the Ombudsman found the landlord's
      pre-existing offer proportionate; only non-binding recommendations are
      issued.
    * ``no_maladministration`` is a substantive landlord defence.
    * ``resolved_with_intervention`` indicates settlement during Ombudsman
      involvement; not a merits decision.
    * ``outside_jurisdiction`` is a non-determination — the Ombudsman declined
      to investigate. Eval should test for abstention on these rows.

    Forum-neutral employment-friendly values (SHA-65 vertical):

    * ``claimant_success`` — claimant won on the merits of the lead issue.
    * ``respondent_success`` — respondent won.
    * ``partial_success`` — mixed result across complaint heads.
    * ``non_merits`` — preliminary / strike-out / withdrawn / default /
      remedy-only / jurisdiction-only / reconsideration. Eval treats these
      as abstention test points (cf. ``outside_jurisdiction`` for the
      Ombudsman side).

    The legacy ``Winner`` enum is preserved for backward compatibility via
    ``overall_winner_legacy``; the canonical mapping lives in
    ``_legacy_winner_for``.
    """

    # Housing Ombudsman values.
    MALADMINISTRATION = "maladministration"
    SEVERE_MALADMINISTRATION = "severe_maladministration"
    SERVICE_FAILURE = "service_failure"
    REASONABLE_REDRESS = "reasonable_redress"
    NO_MALADMINISTRATION = "no_maladministration"
    RESOLVED_WITH_INTERVENTION = "resolved_with_intervention"
    OUTSIDE_JURISDICTION = "outside_jurisdiction"

    # Forum-neutral / employment values.
    CLAIMANT_SUCCESS = "claimant_success"
    RESPONDENT_SUCCESS = "respondent_success"
    PARTIAL_SUCCESS = "partial_success"
    NON_MERITS = "non_merits"


# ---------------------------------------------------------------------------
# Forum-coercion partitions
# ---------------------------------------------------------------------------
#
# Option 1 of the SHA-65-0 schema gate extends GoldCase enums additively.
# To stop accidental cross-forum coercion, validator INV-F1 partitions every
# value into a forum family and rejects mixing on a single gold row.

_HOUSING_PARTY_ROLES = frozenset(
    {PartyRole.TENANT, PartyRole.LANDLORD, PartyRole.AGENT}
)
_EMPLOYMENT_PARTY_ROLES = frozenset(
    {PartyRole.CLAIMANT, PartyRole.RESPONDENT_EMPLOYER}
)

_HOUSING_WINNERS = frozenset({Winner.TENANT, Winner.LANDLORD})
_EMPLOYMENT_WINNERS = frozenset({Winner.CLAIMANT, Winner.RESPONDENT})
# Winner.SPLIT is forum-neutral and intentionally absent from both sets.

_HOUSING_CLAIM_TYPES = frozenset(
    {
        ClaimType.CLEANING,
        ClaimType.DAMAGES,
        ClaimType.DEPOSIT_NON_PROTECTION,
        ClaimType.DISREPAIR,
        ClaimType.END_OF_TENANCY,
    }
)
_EMPLOYMENT_CLAIM_TYPES = frozenset({ClaimType.UNFAIR_DISMISSAL})

_HOUSING_DETERMINATIONS = frozenset(
    {
        Determination.MALADMINISTRATION,
        Determination.SEVERE_MALADMINISTRATION,
        Determination.SERVICE_FAILURE,
        Determination.REASONABLE_REDRESS,
        Determination.NO_MALADMINISTRATION,
        Determination.RESOLVED_WITH_INTERVENTION,
        Determination.OUTSIDE_JURISDICTION,
    }
)
# Employment + forum-neutral determinations. The four forum-neutral values
# could conceivably appear on a future housing vertical, but housing rows
# today MUST use the Ombudsman-specific values — adding them here would
# silently broaden the partition with no test coverage. Re-evaluate when a
# second housing forum adopts the neutral set.
_EMPLOYMENT_DETERMINATIONS = frozenset(
    {
        Determination.CLAIMANT_SUCCESS,
        Determination.RESPONDENT_SUCCESS,
        Determination.PARTIAL_SUCCESS,
        Determination.NON_MERITS,
    }
)


def _domain_family(domain_id: Optional[str]) -> Optional[str]:
    """Return ``'housing'`` or ``'employment'`` for a recognised ``domain_id``.

    ``None`` for unrecognised / unset ``domain_id`` so the existing legacy
    rows that pre-date the per-domain SHA-20 fields keep validating.
    """

    if not domain_id:
        return None
    if domain_id.startswith("housing."):
        return "housing"
    if domain_id.startswith("employment."):
        return "employment"
    return None


def _legacy_winner_for(determination: Determination) -> Winner:
    """Canonical mapping from Determination to the legacy binary Winner.

    Used by `GroundTruthOutcome._validate_outcome` to enforce that any caller-
    supplied `overall_winner_legacy` matches the rule, and by the migration
    script to populate the field deterministically.

    Housing Ombudsman side:

    * ``RESOLVED_WITH_INTERVENTION`` maps to SPLIT because settlement during
      Ombudsman intervention is not a clean tenant-or-landlord merits win.

    Employment side (SHA-65):

    * ``CLAIMANT_SUCCESS`` -> ``Winner.CLAIMANT``
    * ``RESPONDENT_SUCCESS`` -> ``Winner.RESPONDENT``
    * ``PARTIAL_SUCCESS`` -> ``Winner.SPLIT`` (reuses the forum-neutral
      split value rather than introducing a parallel partial-claimant
      construct — keeps eval aggregation simple).
    * ``NON_MERITS`` -> ``Winner.RESPONDENT``. A claim that never reached
      the merits is effectively dismissed for outcome-modelling purposes,
      mirroring how ``outside_jurisdiction`` maps to LANDLORD.
    """

    if determination in (
        Determination.MALADMINISTRATION,
        Determination.SEVERE_MALADMINISTRATION,
        Determination.SERVICE_FAILURE,
    ):
        return Winner.TENANT
    if determination in (
        Determination.REASONABLE_REDRESS,
        Determination.NO_MALADMINISTRATION,
        Determination.OUTSIDE_JURISDICTION,
    ):
        return Winner.LANDLORD
    if determination == Determination.RESOLVED_WITH_INTERVENTION:
        return Winner.SPLIT
    if determination == Determination.CLAIMANT_SUCCESS:
        return Winner.CLAIMANT
    if determination == Determination.RESPONDENT_SUCCESS:
        return Winner.RESPONDENT
    if determination == Determination.PARTIAL_SUCCESS:
        return Winner.SPLIT
    if determination == Determination.NON_MERITS:
        return Winner.RESPONDENT
    raise ValueError(f"unhandled determination: {determination!r}")


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


class ComplaintFinding(StrictBaseModel):
    """Per-complaint-head determination + award.

    Housing Ombudsman cases frequently contain mixed findings across multiple
    complaint heads (e.g. `no maladministration; maladministration; service
    failure; reasonable redress`). When non-empty, this list captures each
    head separately so eval metrics can score per-finding accuracy and not
    just the collapsed top-level determination.
    """

    complaint_label: str = Field(min_length=1)
    finding: Determination
    awarded_gbp: Decimal = Field(ge=0, default=Decimal("0"))


class ReasoningQuote(StrictBaseModel):
    text: str = Field(min_length=1)
    provenance: Provenance


class GroundTruthOutcome(StrictBaseModel):
    """Ground-truth outcome of a tribunal or Ombudsman decision.

    Two paths are permitted:

    * **Apportioned** (default): `per_issue` is non-empty, INV-6 enforces
      `total_awarded_gbp == sum(per_issue.awarded_gbp)` exactly.
    * **Unapportioned**: when `unapportioned_reason` is set, the tribunal
      gave a global figure with no per-issue breakdown. `per_issue` MUST
      be empty in this case; `total_awarded_gbp` is the only authoritative
      number; INV-5 (per-issue/claimed-amounts label match) is vacuously
      satisfied.

    Determination ontology (added 2026-05-06 for housing.repairs_social.v1):

    * `determination` carries the substantive Ombudsman finding.
    * `determination_per_complaint` carries per-complaint-head findings for
      mixed cases.
    * `amount_ordered_now_gbp`, `amount_previously_offered_gbp`,
      `amount_global_unapportioned_gbp` split the polysemous
      `total_awarded_gbp` field into the three legally-distinct constructs
      identified in the balanced-50 RCA.
    * `overall_winner_legacy` is the derived backward-compat winner — if set,
      it must match the canonical determination -> winner mapping.

    Invariants enforced by `_validate_outcome`:

    1. If any of the three split amount fields is set, their sum equals
       `total_awarded_gbp`.
    2. `outside_jurisdiction` cases must have `total_awarded_gbp == 0` and
       all split amount fields None.
    3. `overall_winner_legacy`, if set, matches `_legacy_winner_for(determination)`.
    """

    overall_winner: Winner
    total_awarded_gbp: Decimal = Field(ge=0)
    per_issue: list[IssueOutcome] = Field(default_factory=list)
    unapportioned_reason: Optional[str] = None

    # --- 2026-05-06 determination ontology (additive, optional) -------
    determination: Optional[Determination] = None
    determination_per_complaint: list[ComplaintFinding] = Field(default_factory=list)
    amount_ordered_now_gbp: Optional[Decimal] = Field(default=None, ge=0)
    amount_previously_offered_gbp: Optional[Decimal] = Field(default=None, ge=0)
    amount_global_unapportioned_gbp: Optional[Decimal] = Field(default=None, ge=0)
    overall_winner_legacy: Optional[Winner] = None

    # --- 2026-05-14 employment-remedy fields (additive, optional) -----
    # Populated only on employment-family GoldCase rows. Validators in
    # GoldCase._validate_invariants ensure these never appear on housing
    # rows (INV-F2). All fields are Optional so legacy rows continue to
    # validate. The compensatory amount split mirrors Acas guidance:
    # basic award (statutory formula), compensatory award (loss of
    # earnings + future loss), deductions (Polkey + contributory fault as
    # a combined %), uplifts (Acas Code uplift as a %), and reinstatement
    # / re-engagement remedy flags (sought vs granted).
    basic_award_gbp: Optional[Decimal] = Field(default=None, ge=0)
    compensatory_award_gbp: Optional[Decimal] = Field(default=None, ge=0)
    deductions_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    uplifts_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    reinstatement_sought: Optional[bool] = None
    reinstatement_granted: Optional[bool] = None
    re_engagement_sought: Optional[bool] = None
    re_engagement_granted: Optional[bool] = None

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
        else:
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

    @model_validator(mode="after")
    def _validate_outcome(self) -> "GroundTruthOutcome":
        # INV-D1: split amount fields must sum to total when any is set
        split_amounts = [
            self.amount_ordered_now_gbp,
            self.amount_previously_offered_gbp,
            self.amount_global_unapportioned_gbp,
        ]
        if any(v is not None for v in split_amounts):
            non_null = [v for v in split_amounts if v is not None]
            split_sum = sum(non_null, start=Decimal("0"))
            if split_sum != self.total_awarded_gbp:
                raise ValueError(
                    f"sum(amount_ordered_now_gbp, amount_previously_offered_gbp, "
                    f"amount_global_unapportioned_gbp) = {split_sum} "
                    f"!= total_awarded_gbp ({self.total_awarded_gbp}); "
                    "set the unset fields to 0 if there is no contribution from "
                    "that construct, or omit all three to skip the split."
                )
        # INV-D2: outside_jurisdiction is a non-determination — total must be 0
        if self.determination == Determination.OUTSIDE_JURISDICTION:
            if self.total_awarded_gbp != Decimal("0") or any(
                v not in (None, Decimal("0")) for v in split_amounts
            ):
                raise ValueError(
                    "outside_jurisdiction determinations must record "
                    "total_awarded_gbp == 0 and no split amounts"
                )
        # INV-D3: overall_winner_legacy must match canonical mapping
        if self.overall_winner_legacy is not None and self.determination is not None:
            expected = _legacy_winner_for(self.determination)
            if self.overall_winner_legacy != expected:
                raise ValueError(
                    f"overall_winner_legacy ({self.overall_winner_legacy.value!r}) "
                    f"inconsistent with determination ({self.determination.value!r}); "
                    f"expected {expected.value!r}"
                )
        return self


class LabelerModel(StrictBaseModel):
    """A single labeling pass's provider/model/version triple.

    Recorded per case so a published gold set can be re-derived from raw
    LLM outputs (frozen in the run artifact) even after the live model is
    retired. ``api_version`` is optional — set it when the provider exposes
    a stable response-API version string the team should pin.
    """

    provider: Literal["anthropic", "openai"]
    model: str = Field(min_length=1)
    api_version: Optional[str] = None


_PROVENANCE_SOURCES = Literal[
    "deterministic_manifest",
    "model_agreement",
    "human_mandatory_review",
    "human_disagreement_adjudication",
    "human_agreed_cell_audit",
    "human_only_anchor",
]


class FieldLabelProvenance(StrictBaseModel):
    """Per-cell audit trail for a single ``GoldCase`` field.

    ``field_path`` uses the granular notation defined in §4 of the sparring
    plan (e.g. ``"per_issue[issue=damages].winner"``); see
    ``packages/eval/auto_label/disagreement.py`` for the canonical builder.
    """

    field_path: str = Field(min_length=1)
    source: _PROVENANCE_SOURCES
    source_spans: list[Provenance] = Field(default_factory=list)
    match_strategy: Optional[str] = None
    reviewer_rationale: Optional[str] = None


class LabelingProvenance(StrictBaseModel):
    """Per-case audit trail produced by ``packages/eval/auto_label/runner.py``.

    Carries every hash and version needed to replay a labeling decision
    once labeler models, OCR engines, or authority indexes drift. Raw LLM
    outputs are NOT stored here — they live in the per-case run artifact
    under ``data/eval_artifacts/labeling/<run_id>/<case_id>.json``. This
    keeps ``housing_v1.jsonl`` rows readable and diffable.
    """

    run_id: str = Field(min_length=1)
    labeled_at: datetime
    labeler_models: list[LabelerModel] = Field(min_length=1)

    # Reproducibility hashes / versions
    source_pdf_sha256: str
    ocr_text_sha256: str
    ocr_engine: Optional[str] = None
    ocr_engine_version: Optional[str] = None
    prompt_template_hash: str = Field(min_length=1)
    prompt_pack_hash: Optional[str] = None
    gold_schema_hash: str = Field(min_length=1)
    corpus_manifest_hash: str = Field(min_length=1)
    domain_spec_hash: Optional[str] = None
    authority_index_id: Optional[str] = None
    authority_index_hash: Optional[str] = None
    statute_index_id: Optional[str] = None
    statute_index_hash: Optional[str] = None
    canonicalizer_version: str = Field(min_length=1)
    grounder_version: str = Field(min_length=1)
    audit_seed: int

    # Human-control status
    is_human_only_anchor: bool = False
    anchor_set_id: Optional[str] = None
    mandatory_review_completed_at: Optional[datetime] = None
    human_adjudicator: Optional[str] = None
    adjudicated_fields: list[str] = Field(default_factory=list)

    # Reported metrics — raw rates, NOT Cohen's kappa.
    inter_model_agreement_rate: float = Field(ge=0.0, le=1.0)
    grounding_pass_rate: float = Field(ge=0.0, le=1.0)
    audit_flip_rate: float = Field(ge=0.0, le=1.0)
    mandatory_review_flip_rate: float = Field(ge=0.0, le=1.0)
    field_provenance: list[FieldLabelProvenance] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_sha256_fields(self) -> "LabelingProvenance":
        for field_name in ("source_pdf_sha256", "ocr_text_sha256"):
            value = getattr(self, field_name)
            if not _SHA256_RE.match(value):
                raise ValueError(
                    f"{field_name} must be 64 lowercase hex chars; got {value!r}"
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
    disputed_amount_gbp: Optional[Decimal] = Field(default=None, ge=0)
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
    claimed_amounts: list[ClaimedAmount] = Field(default_factory=list)
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
    labeling_provenance: Optional[LabelingProvenance] = Field(
        default=None,
        description=(
            "When set, this row was produced by the auto-label pipeline "
            "(dual-LLM + auto-grounder + human adjudication). None means "
            "the row predates the pipeline (legacy hand-annotated cases). "
            "See packages/eval/auto_label/runner.py and "
            "docs/eval/gold-schema.md."
        ),
    )

    def _enforce_forum_partition(self, family: str) -> None:
        """Refuse any row that mixes housing-family + employment-family enum values.

        Called from ``_validate_invariants`` when ``family`` is known. The
        partition is documented above (``_HOUSING_*`` / ``_EMPLOYMENT_*``
        frozensets); ``Winner.SPLIT`` is intentionally forum-neutral and
        permitted on either side.
        """

        if family == "housing":
            allowed_roles = _HOUSING_PARTY_ROLES
            allowed_winners = _HOUSING_WINNERS | {Winner.SPLIT}
            allowed_claim_types = _HOUSING_CLAIM_TYPES
            allowed_determinations = _HOUSING_DETERMINATIONS
        elif family == "employment":
            allowed_roles = _EMPLOYMENT_PARTY_ROLES
            allowed_winners = _EMPLOYMENT_WINNERS | {Winner.SPLIT}
            allowed_claim_types = _EMPLOYMENT_CLAIM_TYPES
            allowed_determinations = _EMPLOYMENT_DETERMINATIONS
        else:
            return

        bad_roles = [p.role for p in self.parties if p.role not in allowed_roles]
        if bad_roles:
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but parties carry role(s) "
                f"{sorted({r.value for r in bad_roles})} from the other "
                "forum. Cross-forum coercion is rejected."
            )

        bad_claim_types = [
            ct for ct in self.claim_types if ct not in allowed_claim_types
        ]
        if bad_claim_types:
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but claim_types include "
                f"{sorted({c.value for c in bad_claim_types})} from the "
                "other forum. Cross-forum coercion is rejected."
            )

        outcome = self.ground_truth_outcome
        if outcome.overall_winner not in allowed_winners:
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but ground_truth_outcome.overall_winner is "
                f"{outcome.overall_winner.value!r} from the other forum. "
                "Cross-forum coercion is rejected."
            )

        bad_issue_winners = [
            io.winner for io in outcome.per_issue if io.winner not in allowed_winners
        ]
        if bad_issue_winners:
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but per_issue carries winner(s) "
                f"{sorted({w.value for w in bad_issue_winners})} from the "
                "other forum. Cross-forum coercion is rejected."
            )

        if (
            outcome.determination is not None
            and outcome.determination not in allowed_determinations
        ):
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but ground_truth_outcome.determination is "
                f"{outcome.determination.value!r} from the other forum. "
                "Cross-forum coercion is rejected."
            )

        bad_per_complaint = [
            cf.finding
            for cf in outcome.determination_per_complaint
            if cf.finding not in allowed_determinations
        ]
        if bad_per_complaint:
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but determination_per_complaint carries "
                f"finding(s) {sorted({f.value for f in bad_per_complaint})} "
                "from the other forum. Cross-forum coercion is rejected."
            )

        if (
            outcome.overall_winner_legacy is not None
            and outcome.overall_winner_legacy not in allowed_winners
        ):
            raise ValueError(
                f"INV-F1: domain_id {self.domain_id!r} is in the "
                f"{family!r} family but overall_winner_legacy is "
                f"{outcome.overall_winner_legacy.value!r} from the other forum. "
                "Cross-forum coercion is rejected."
            )

    @model_validator(mode="after")
    def _validate_invariants(self) -> "GoldCase":
        # INV-1: decision_date in PILOT-permitted window
        max_decision_date = _DOMAIN_MAX_DECISION_DATE.get(
            self.domain_id or "",
            _MAX_DECISION_DATE,
        )
        if not (_MIN_DECISION_DATE <= self.decision_date <= max_decision_date):
            raise ValueError(
                f"decision_date {self.decision_date} outside permitted "
                f"window [{_MIN_DECISION_DATE}, {max_decision_date}]"
            )
        # INV-2: party-role coverage. Branches on the gold case's domain
        # family so employment rows aren't forced to claim a "landlord".
        family = _domain_family(self.domain_id)
        roles = {p.role for p in self.parties}
        if family == "employment":
            if (
                PartyRole.CLAIMANT not in roles
                or PartyRole.RESPONDENT_EMPLOYER not in roles
            ):
                raise ValueError(
                    "employment-family gold rows require at least one "
                    "claimant and one respondent_employer party; "
                    f"got roles={sorted(r.value for r in roles)}"
                )
        else:
            # Housing (and legacy unset-domain) rows still require
            # tenant + landlord per the original SHA-28 contract.
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
        # Domains where the upstream record may not carry a pre-decision
        # monetary claim. The Housing Ombudsman corpus orders global
        # compensation without an itemised dispute amount; the Employment
        # Tribunal corpus often issues judgments where the merits are
        # decided and remedy is deferred. Legacy deposit/RRO rows still
        # require claimed/disputed amounts.
        _CORPUS_WITHOUT_DISPUTED_AMOUNT = (
            "housing.repairs_social.v1",
            # employment.* family — any sub-domain (unfair_dismissal,
            # discrimination, etc) follows the same rule.
        )
        amount_required = self.domain_id not in _CORPUS_WITHOUT_DISPUTED_AMOUNT and family != "employment"
        if amount_required:
            if self.disputed_amount_gbp is None:
                raise ValueError(
                    "disputed_amount_gbp is required unless domain_id is "
                    "in the housing.repairs_social.v1 or employment.* "
                    "exempt set"
                )
            if not self.claimed_amounts:
                raise ValueError(
                    "claimed_amounts must contain at least one row unless "
                    "domain_id is in the housing.repairs_social.v1 or "
                    "employment.* exempt set"
                )
        elif self.domain_id == "housing.repairs_social.v1":
            # housing.repairs_social.v1 — determination is required (INV-D4)
            if self.ground_truth_outcome.determination is None:
                raise ValueError(
                    "ground_truth_outcome.determination is required when "
                    "domain_id == 'housing.repairs_social.v1' (INV-D4); "
                    "see docs/eval/housing-ombudsman-determination-ontology-2026-05-06.md"
                )
        elif family == "employment":
            # INV-D5: employment-family rows must record a determination so
            # downstream metrics can group claimant_success / respondent_success
            # / partial_success / non_merits without falling back to the
            # housing-shaped winner-only summary.
            if self.ground_truth_outcome.determination is None:
                raise ValueError(
                    "ground_truth_outcome.determination is required when "
                    f"domain_id is in the employment family (got {self.domain_id!r}) "
                    "(INV-D5); set claimant_success / respondent_success / "
                    "partial_success / non_merits."
                )

        # INV-F1: cross-forum coercion guard.
        #
        # Option 1 of the SHA-65-0 schema gate (chosen by the user on
        # 2026-05-14) extends GoldCase enums additively across housing and
        # employment. The whole point of going with option 1 over an
        # adapter pattern is that *one* schema represents both forums —
        # but only if the enum partitions stay internally consistent on a
        # single row. INV-F1 refuses any row that mixes families.
        if family is not None:
            self._enforce_forum_partition(family)

        # INV-F2: employment-only remedy fields. Optional ET-specific
        # remedy fields on GroundTruthOutcome MUST be unset on
        # non-employment rows so a housing case can never accidentally
        # carry a basic_award or compensatory_award (those concepts have
        # no Ombudsman analogue).
        if family != "employment":
            for field_name in (
                "basic_award_gbp",
                "compensatory_award_gbp",
                "deductions_pct",
                "uplifts_pct",
                "reinstatement_sought",
                "reinstatement_granted",
                "re_engagement_sought",
                "re_engagement_granted",
            ):
                value = getattr(self.ground_truth_outcome, field_name)
                if value is not None:
                    raise ValueError(
                        f"ground_truth_outcome.{field_name} is set "
                        f"({value!r}) but domain_id "
                        f"{self.domain_id!r} is not in the employment "
                        "family (INV-F2). ET remedy fields belong only on "
                        "employment.* gold rows."
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
        if self.disputed_amount_gbp is None:
            if self.case_size != CaseSize.UNKNOWN:
                raise ValueError(
                    f"case_size {self.case_size.value!r} inconsistent with "
                    "unknown disputed_amount_gbp (expected 'unknown')"
                )
            return self

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
