"""Typed KG fact extraction for SHA-33 retrieval-side fusion + prompt fact card.

Three high-signal typed facts derived from the KnowledgeGraph:
- deposit_protection_status — verifiable from dates on LeaseNode
- prescribed_information_status — verifiable from dates on LeaseNode
- check_in_inventory_baseline — derivable from EvidenceNode types

These are the only facts promoted to typed-enum first-class status. All other
KG content stays in its existing free-text form (kg_constraints,
timeline_summary, evidence_summary) to preserve cite-or-abstain integrity
and avoid escalating user-input-derived strings into the prompt.

DEPRECATED (Stream C PR 4): the rendering responsibility for this module's
KGFacts has moved to ``packages/domain_packs/housing/deposit/renderer.py``
(invoked via ``DomainPack.render_factor_card``). This module is kept for
two reasons:

1. ``derive_kg_facts(kg, issue_type) -> KGFacts`` remains the deposit fact
   extractor consumed by ``prediction_engine_v2.py`` to populate
   ``kg_facts_by_issue`` (and via Task 4.5 also ``case_graph_by_issue``).
2. ``KGFacts`` is the input type for the deposit pack renderer (typed
   facade); the pack accepts it via duck-typing.

A post-Stream-C cleanup PR (out of scope here) will eventually delete this
module entirely once the deposit pack has a more general extractor and the
deposit byte-equivalence reference at
``IssuePredictor._format_kg_fact_card`` is no longer needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

try:
    from typing import Literal  # py3.8+
except ImportError:  # pragma: no cover
    from typing_extensions import Literal  # type: ignore

from ..models.prediction_v2 import IssueType


DepositStatus = Literal[
    "not_protected", "protected_late", "protected_on_time", "unknown"
]
PrescribedStatus = Literal[
    "not_provided", "provided_late", "provided_on_time", "unknown"
]
InventoryBaseline = Literal["present", "absent", "unknown"]


_INVENTORY_SENSITIVE_ISSUES = {
    IssueType.CLEANING,
    IssueType.DAMAGE,
    IssueType.FAIR_WEAR_AND_TEAR,
    IssueType.MISSING_ITEMS,
}


@dataclass(frozen=True)
class KGFacts:
    """Three typed KG facts that drive both retrieval reranking and prompt fact card."""

    deposit_protection_status: DepositStatus = "unknown"
    deposit_scheme: Optional[str] = None
    deposit_late_by_days: Optional[int] = None
    prescribed_information_status: PrescribedStatus = "unknown"
    prescribed_late_by_days: Optional[int] = None
    check_in_inventory_baseline: InventoryBaseline = "unknown"

    def is_empty(self) -> bool:
        return (
            self.deposit_protection_status == "unknown"
            and self.prescribed_information_status == "unknown"
            and self.check_in_inventory_baseline == "unknown"
        )


def derive_kg_facts(kg: Any, issue_type: IssueType) -> KGFacts:
    """Pull typed facts off the KG. Returns all-unknown when KG is None or empty."""
    if kg is None:
        return KGFacts()

    try:
        from kg_builder.models.nodes import NodeType
    except ImportError:
        return KGFacts()

    lease_nodes = kg.get_nodes_by_type(NodeType.LEASE)
    lease = lease_nodes[0] if lease_nodes else None

    deposit_status: DepositStatus = "unknown"
    deposit_late_by: Optional[int] = None
    deposit_scheme: Optional[str] = None
    prescribed_status: PrescribedStatus = "unknown"
    prescribed_late_by: Optional[int] = None

    if lease is not None:
        receipt_date = getattr(lease, "deposit_received_date", None) or (
            _find_deposit_receipt_date(kg)
        )
        deposit_scheme = getattr(lease, "deposit_scheme", None)
        protected = getattr(lease, "deposit_protected", None)
        start = receipt_date or getattr(lease, "start_date", None)
        protection_date = getattr(lease, "protection_date", None)

        if protected is False:
            deposit_status = "not_protected"
        elif protected is True and start and protection_date:
            days = (protection_date - start).days
            if days > 30:
                deposit_status = "protected_late"
                deposit_late_by = days - 30
            else:
                deposit_status = "protected_on_time"
        elif protected is True:
            deposit_status = "protected_on_time"

        prescribed = getattr(lease, "prescribed_info_provided", None)
        prescribed_date = getattr(lease, "prescribed_info_date", None)
        if prescribed is False:
            prescribed_status = "not_provided"
        elif prescribed is True and start and prescribed_date:
            days = (prescribed_date - start).days
            if days > 30:
                prescribed_status = "provided_late"
                prescribed_late_by = days - 30
            else:
                prescribed_status = "provided_on_time"
        elif prescribed is True:
            prescribed_status = "provided_on_time"

    inventory: InventoryBaseline = "unknown"
    if issue_type in _INVENTORY_SENSITIVE_ISSUES:
        evidence_nodes = kg.get_nodes_by_type(NodeType.EVIDENCE)
        has_checkin = any(
            "inventory_checkin" in str(getattr(e, "evidence_type", "")).lower()
            for e in evidence_nodes
        )
        inventory = "present" if has_checkin else "absent"

    return KGFacts(
        deposit_protection_status=deposit_status,
        deposit_scheme=deposit_scheme,
        deposit_late_by_days=deposit_late_by,
        prescribed_information_status=prescribed_status,
        prescribed_late_by_days=prescribed_late_by,
        check_in_inventory_baseline=inventory,
    )


def _find_deposit_receipt_date(kg: Any) -> Optional[Any]:
    try:
        from kg_builder.models.nodes import NodeType
    except ImportError:
        return None

    receipt_event_types = {"deposit_paid", "deposit_lodged", "deposit_received"}
    event_nodes = kg.get_nodes_by_type(NodeType.EVENT)
    dates = [
        getattr(event, "event_date", None)
        for event in event_nodes
        if getattr(event, "event_type", None) in receipt_event_types
        and getattr(event, "event_date", None) is not None
    ]
    return min(dates) if dates else None
