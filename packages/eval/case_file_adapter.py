"""Reconstruct a pre-decision `CaseFile` from a post-decision `GoldCase`.

The prediction engine consumes `CaseFile` (intake state). Gold cases are
post-decision tribunal records — they contain the verdict, the tribunal's
reasoning quotes, the statutory basis the tribunal relied on, and the
authorities the tribunal cited. None of those existed when the case was
"intake"; presenting them to the engine would let it cheat on the test
the harness is trying to administer.

This adapter intentionally **drops** every post-decision artifact:

| Gold field | Why dropped |
|---|---|
| `ground_truth_outcome` | The answer the engine must predict |
| `key_reasoning_quotes` | The tribunal's reasoning |
| `statutory_basis` | What the tribunal cited (post hoc) |
| `cited_authorities` | What the tribunal cited (post hoc) |
| `decision_date` | The tribunal hadn't decided yet at intake |
| `evidence_unavailable_reason` | Annotation-time scaffolding |
| `statutory_basis_unavailable_reason` | Annotation-time scaffolding |

Other reconstruction is lossy in benign ways:

- Party names: gold doesn't carry them (privacy). Placeholder strings are
  used so downstream code that assumes non-null still works.
- `claim_types` mapping into `DisputeIssue`: see `eval.issue_alignment`.
  Unmappable types (`end_of_tenancy`, and `disrepair` outside a repairs
  matter type) fall back to
  `DisputeIssue.OTHER` and are recorded on the returned
  `LossyReconstruction.unmapped_claim_types` set so the runner can
  emit an alignment report.

`LossyReconstruction.case_file` is the consumable artifact. The other
fields are introspection — the runner uses them to log per-case
reconstruction quality and, where possible, to map enum-style prediction
issue labels back to the gold case's pre-decision claimed-amount labels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Set

from eval.issue_alignment import UnmappableIssue, eval_to_orchestrator
from eval.schema import GoldCase, PartyRole as EvalPartyRole

if TYPE_CHECKING:
    from llm_orchestrator.models.case_file import CaseFile


@dataclass
class LossyReconstruction:
    """Wraps a reconstructed `CaseFile` with provenance about what was
    dropped or coerced. Lets the live runner emit per-case alignment
    diagnostics without adding orchestrator-side fields."""

    case_file: "CaseFile"
    unmapped_claim_types: Set[str] = field(default_factory=set)
    statutory_basis_count: int = 0
    cited_authorities_count: int = 0
    evidence_items_dropped: int = 0
    gold_issue_labels_by_claim_type: dict[str, str] = field(default_factory=dict)


# Crude mapping from gold Evidence.kind strings to orchestrator EvidenceType.
# Conservative: anything we don't recognise → OTHER. Adjust as gold-set
# vocabulary stabilises.
_EVIDENCE_KIND_MAP = {
    "inventory_checkin": "inventory_checkin",
    "inventory_checkout": "inventory_checkout",
    "photos_before": "photos_before",
    "photos_after": "photos_after",
    "receipts": "receipts",
    "invoices": "invoices",
    "correspondence": "correspondence",
    "tenancy_agreement": "tenancy_agreement",
    "deposit_certificate": "deposit_certificate",
    "witness_statement": "witness_statement",
}

_OMBUDSMAN_COMPENSATION_LABELS = {
    "ombudsman_compensation",
    "compensation",
    "ombudsman_remedy",
}

_PRE_DECISION_CLAIM_PROVENANCE_MARKERS = {
    "pre-decision claim",
    "pre decision claim",
    "predecision claim",
    "pre_decision_claim",
    "resident claimed",
    "tenant claimed",
}


def gold_case_to_case_file(gold: GoldCase) -> LossyReconstruction:
    """Build a pre-decision `CaseFile` from `GoldCase`. See module docstring."""
    from llm_orchestrator.models.case_file import (
        CaseFile,
        ClaimedAmount,
        DisputeIssue,
        EvidenceItem,
        EvidenceType,
        PartyRole,
        PropertyDetails,
        TenancyDetails,
    )

    unmapped: Set[str] = set()
    issues = []
    # Phase 7 audit D3: pass gold.matter_type into the alignment so the
    # deposit_deduction vs deposit_non_protection split is honoured.
    mt = gold.matter_type
    for ct in gold.claim_types:
        try:
            issues.append(eval_to_orchestrator(ct, matter_type=mt))
        except UnmappableIssue:
            unmapped.add(ct.value)
            issues.append(DisputeIssue.OTHER)

    tenant_claims = []
    landlord_claims = []
    omitted_outcome_amount_paths: list[str] = []
    for ca in gold.claimed_amounts or []:
        if is_outcome_derived_ombudsman_claimed_amount(gold, ca):
            omitted_outcome_amount_paths.append(_claimed_amount_path(ca))
            continue
        # ca.issue is a string in eval-vocabulary; try to remap to orch.
        try:
            issue_enum = eval_to_orchestrator(ca.issue, matter_type=mt)
        except UnmappableIssue:
            issue_enum = _fallback_claim_issue_for_amount(
                ca.issue,
                domain_id=gold.domain_id,
                matter_type=mt,
                mapped_case_issues=issues,
                default=DisputeIssue.OTHER,
            )
        claim = ClaimedAmount(
            issue=issue_enum,
            amount=float(ca.amount_gbp),
            description=_claim_description(gold, ca),
        )
        if ca.by_party == EvalPartyRole.TENANT:
            tenant_claims.append(claim)
        else:
            landlord_claims.append(claim)

    dispute_amount = _case_file_dispute_amount(gold)
    if dispute_amount is None and is_outcome_derived_ombudsman_disputed_amount(gold):
        omitted_outcome_amount_paths.append("disputed_amount_gbp")

    evidence_items = []
    dropped_count = 0
    for e in gold.evidence:
        ev_type_value = _EVIDENCE_KIND_MAP.get(e.kind.lower(), "other")
        try:
            ev_type = EvidenceType(ev_type_value)
        except ValueError:
            ev_type = EvidenceType.OTHER
            dropped_count += 1
        evidence_items.append(
            EvidenceItem(
                type=ev_type,
                description=e.description,
                source="gold_reconstruction",
            )
        )

    domain_id = gold.domain_id or "housing.deposit.v1"
    matter_types = [gold.matter_type] if gold.matter_type else []
    case_file = CaseFile(
        case_id=gold.case_id,
        user_role=PartyRole.TENANT,  # default — see module docstring
        domain_id=domain_id,
        domain_version=gold.schema_version.value,
        matter_types=matter_types,
        routing_confidence=1.0,
        routing_metadata={
            "source": "gold_reconstruction",
            "forum": gold.forum,
            "source_kind": gold.source_kind,
            "source_publisher": gold.source_publisher,
        },
        tenant_name="Tenant",
        landlord_name="Landlord",
        property=PropertyDetails(region=gold.region.value.upper()[:3]),
        tenancy=TenancyDetails(),
        issues=issues,
        dispute_amount=dispute_amount,
        tenant_claims=tenant_claims,
        landlord_claims=landlord_claims,
        evidence=evidence_items,
        tenant_narrative=gold.facts,
        landlord_narrative=None,
        intake_complete=True,
        completeness_score=1.0,
        metadata={
            "source": "gold_reconstruction",
            "schema_version": gold.schema_version.value,
            "domain_id": gold.domain_id,
            "forum": gold.forum,
            "source_publisher": gold.source_publisher,
            "source_kind": gold.source_kind,
            "retrieval_namespace_id": gold.retrieval_namespace_id,
            "corpus_version": gold.corpus_version,
            "matter_type": gold.matter_type,
            "target_source_id": gold.target_source_id,
            "target_source_url": gold.source_url,
            "excluded_source_ids": list(gold.excluded_source_ids),
            "source_pdf_sha256": gold.source_pdf_sha256,
            "ocr_confidence": gold.ocr_confidence,
            "unmapped_claim_types": sorted(unmapped),
            "omitted_outcome_derived_amount_fields": sorted(
                set(omitted_outcome_amount_paths)
            ),
        },
    )

    return LossyReconstruction(
        case_file=case_file,
        unmapped_claim_types=unmapped,
        statutory_basis_count=len(gold.statutory_basis),
        cited_authorities_count=len(gold.cited_authorities),
        evidence_items_dropped=dropped_count,
        gold_issue_labels_by_claim_type=_gold_issue_label_map(gold),
    )


def _gold_issue_label_map(gold: GoldCase) -> dict[str, str]:
    """Best-effort non-leaky map from `ClaimType` to gold issue label.

    Eval metrics join per-issue predictions to `ground_truth_outcome.per_issue`
    by free-text issue label. The predictor, however, emits enum-like issue
    types. When the pre-decision `claimed_amounts` labels have a one-to-one
    shape with `claim_types`, we can safely map e.g. `cleaning` →
    `carpet_cleaning` without reading the tribunal outcome. Ambiguous cases are
    left unmapped so metrics surface them as missing rather than guessing.
    """
    labels = _unique_preserving_order(
        ca.issue
        for ca in gold.claimed_amounts or []
        if not is_outcome_derived_ombudsman_claimed_amount(gold, ca)
    )
    claim_types = [ct.value for ct in gold.claim_types]
    if len(labels) != len(claim_types):
        return {}
    return dict(zip(claim_types, labels))


def _fallback_claim_issue_for_amount(
    issue_label: str,
    *,
    domain_id: str | None,
    matter_type: str | None,
    mapped_case_issues,
    default,
):
    """Map forum-specific free-text claimed amount labels to CaseFile issues."""
    if (
        domain_id == "housing.repairs_social.v1"
        and str(issue_label).strip().lower() in _OMBUDSMAN_COMPENSATION_LABELS
    ):
        repairs_issues = [
            issue
            for issue in mapped_case_issues
            if issue.value
            in {
                "repairs_disrepair",
                "repairs_damp_mould",
                "complaint_handling_failure",
            }
        ]
        if len(repairs_issues) == 1:
            return repairs_issues[0]
        if matter_type:
            try:
                return eval_to_orchestrator("disrepair", matter_type=matter_type)
            except UnmappableIssue:
                pass
    return default


def _claim_description(gold: GoldCase, claimed_amount) -> str:
    facts = (gold.facts or "").strip()
    prefix = (
        f"{claimed_amount.issue} claimed by {claimed_amount.by_party.value} "
        f"for £{claimed_amount.amount_gbp}."
    )
    if not facts:
        return prefix
    return f"{prefix} Pre-decision complaint facts: {facts[:1200]}"


def _case_file_dispute_amount(gold: GoldCase) -> float | None:
    if is_outcome_derived_ombudsman_disputed_amount(gold):
        return None
    amount = _decimal_or_none(getattr(gold, "disputed_amount_gbp", None))
    return float(amount) if amount is not None else None


def is_outcome_derived_ombudsman_disputed_amount(gold: GoldCase) -> bool:
    """Return True when a legacy Ombudsman disputed amount is the final award.

    Early Housing Ombudsman gold drafts promoted the global compensation order
    into pre-decision amount fields. Eval consumers can use this predicate to
    suppress those fields without rewriting the reviewed outcome labels.
    """
    if not _is_generated_ombudsman_global_compensation_outcome(gold):
        return False
    if not _amount_matches_outcome_total(
        gold, getattr(gold, "disputed_amount_gbp", None)
    ):
        return False
    if _has_pre_decision_claim_amount_provenance(gold, "disputed_amount_gbp"):
        return False
    return True


def is_outcome_derived_ombudsman_claimed_amount(
    gold: GoldCase, claimed_amount
) -> bool:
    """Return True when a legacy Ombudsman claimed amount is the final award."""
    issue = str(getattr(claimed_amount, "issue", "") or "").strip().lower()
    if issue not in _OMBUDSMAN_COMPENSATION_LABELS:
        return False
    if not _is_generated_ombudsman_global_compensation_outcome(gold):
        return False
    if not _amount_matches_outcome_total(
        gold, getattr(claimed_amount, "amount_gbp", None)
    ):
        return False
    if _has_pre_decision_claim_amount_provenance(
        gold, _claimed_amount_path(claimed_amount)
    ):
        return False
    return True


def _is_generated_ombudsman_global_compensation_outcome(gold: GoldCase) -> bool:
    if not (
        gold.domain_id == "housing.repairs_social.v1"
        or gold.forum == "housing_ombudsman"
        or gold.source_kind == "ombudsman_determination"
    ):
        return False
    outcome = getattr(gold, "ground_truth_outcome", None)
    reason = str(getattr(outcome, "unapportioned_reason", "") or "").lower()
    return "global compensation order" in reason


def _amount_matches_outcome_total(gold: GoldCase, amount) -> bool:
    outcome = getattr(gold, "ground_truth_outcome", None)
    outcome_total = _decimal_or_none(getattr(outcome, "total_awarded_gbp", None))
    amount_decimal = _decimal_or_none(amount)
    return outcome_total is not None and amount_decimal == outcome_total


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _claimed_amount_path(claimed_amount) -> str:
    by_party = getattr(claimed_amount, "by_party", "")
    by_party_value = getattr(by_party, "value", by_party)
    return (
        f"claimed_amounts[issue={getattr(claimed_amount, 'issue', '?')}"
        f"|by_party={by_party_value}].amount_gbp"
    )


def _has_pre_decision_claim_amount_provenance(gold: GoldCase, path: str) -> bool:
    provenance_text = _field_provenance_text(gold, path)
    return any(
        marker in provenance_text
        for marker in _PRE_DECISION_CLAIM_PROVENANCE_MARKERS
    )


def _field_provenance_text(gold: GoldCase, path: str) -> str:
    labeling = getattr(gold, "labeling_provenance", None)
    if labeling is None:
        return ""
    chunks: list[str] = []
    for row in getattr(labeling, "field_provenance", []) or []:
        if getattr(row, "field_path", None) != path:
            continue
        for attr in ("source", "match_strategy", "reviewer_rationale"):
            value = getattr(row, attr, None)
            if value is not None:
                chunks.append(str(getattr(value, "value", value)))
    return " ".join(chunks).lower()


def _unique_preserving_order(values) -> list[str]:
    seen = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
