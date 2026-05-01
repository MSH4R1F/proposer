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
  Unmappable types (`disrepair`, `end_of_tenancy`) fall back to
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
    for ct in gold.claim_types:
        try:
            issues.append(eval_to_orchestrator(ct))
        except UnmappableIssue:
            unmapped.add(ct.value)
            issues.append(DisputeIssue.OTHER)

    tenant_claims = []
    landlord_claims = []
    for ca in gold.claimed_amounts:
        # ca.issue is a string in eval-vocabulary; try to remap to orch.
        try:
            issue_enum = eval_to_orchestrator(ca.issue)
        except UnmappableIssue:
            issue_enum = DisputeIssue.OTHER
        claim = ClaimedAmount(
            issue=issue_enum,
            amount=float(ca.amount_gbp),
            description=f"Claimed by {ca.by_party.value}",
        )
        if ca.by_party == EvalPartyRole.TENANT:
            tenant_claims.append(claim)
        else:
            landlord_claims.append(claim)

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

    case_file = CaseFile(
        case_id=gold.case_id,
        user_role=PartyRole.TENANT,  # default — see module docstring
        tenant_name="Tenant",
        landlord_name="Landlord",
        property=PropertyDetails(region=gold.region.value.upper()[:3]),
        tenancy=TenancyDetails(),
        issues=issues,
        dispute_amount=float(gold.disputed_amount_gbp),
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
            "source_pdf_sha256": gold.source_pdf_sha256,
            "ocr_confidence": gold.ocr_confidence,
            "unmapped_claim_types": sorted(unmapped),
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
    labels = _unique_preserving_order(ca.issue for ca in gold.claimed_amounts)
    claim_types = [ct.value for ct in gold.claim_types]
    if len(labels) != len(claim_types):
        return {}
    return dict(zip(claim_types, labels))


def _unique_preserving_order(values) -> list[str]:
    seen = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
