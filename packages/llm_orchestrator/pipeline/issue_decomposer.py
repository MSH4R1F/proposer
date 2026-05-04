from __future__ import annotations

from datetime import date
import importlib
from typing import Any, Iterable, List, Optional, Sequence

import structlog

from ..models.case_file import CaseFile, ClaimedAmount, EvidenceItem
from ..models.prediction_v2 import (
    ClaimDetail,
    EvidenceConflict,
    IssueContext,
    IssueType,
    TimelineEvent,
    map_str_to_issue_type,
)

logger = structlog.get_logger()


EVIDENCE_ISSUE_MAP = {
    "inventory_checkin": ["cleaning", "damage", "fair_wear_and_tear", "missing_items"],
    "inventory_checkout": ["cleaning", "damage", "fair_wear_and_tear", "missing_items"],
    "photos_before": [
        "cleaning",
        "damage",
        "redecoration",
        "garden",
        "repairs_disrepair",
        "repairs_damp_mould",
    ],
    "photos_after": [
        "cleaning",
        "damage",
        "redecoration",
        "garden",
        "repairs_disrepair",
        "repairs_damp_mould",
    ],
    "receipts": ["cleaning", "damage", "repairs_disrepair"],
    "invoices": ["cleaning", "damage", "repairs_disrepair"],
    "deposit_certificate": ["deposit_protection"],
    "tenancy_agreement": ["rent_arrears", "deposit_protection"],
    "correspondence": [],
    "witness_statement": [],
    "other": [],
}

INVENTORY_SENSITIVE_ISSUES = {
    IssueType.CLEANING,
    IssueType.DAMAGE,
    IssueType.FAIR_WEAR_AND_TEAR,
    IssueType.MISSING_ITEMS,
}


class IssueDecomposer:
    def decompose(
        self, case_file: CaseFile, knowledge_graph: Optional[Any] = None
    ) -> List[IssueContext]:
        issue_contexts: List[IssueContext] = []
        kg_issue_types: set[IssueType] = set()

        if knowledge_graph is not None:
            try:
                edge_module = importlib.import_module("kg_builder.models.edges")
                graph_module = importlib.import_module("kg_builder.models.graph")
                node_module = importlib.import_module("kg_builder.models.nodes")

                EdgeType = edge_module.EdgeType
                KnowledgeGraph = graph_module.KnowledgeGraph
                NodeType = node_module.NodeType

                if isinstance(knowledge_graph, KnowledgeGraph):
                    issue_contexts = self._decompose_from_kg(
                        case_file=case_file,
                        kg=knowledge_graph,
                        NodeType=NodeType,
                        EdgeType=EdgeType,
                    )
                    kg_issue_types = {ctx.issue_type for ctx in issue_contexts}
                else:
                    logger.warning(
                        "knowledge_graph_not_knowledgegraph",
                        provided_type=type(knowledge_graph).__name__,
                    )
            except ImportError:
                logger.warning("kg_builder_import_failed_falling_back_to_casefile")
            except Exception:
                logger.exception("kg_decomposition_failed_falling_back_to_casefile")

        if not issue_contexts:
            issue_contexts = self._decompose_from_case_file(case_file)
        else:
            for issue in case_file.issues:
                mapped_issue_type = map_str_to_issue_type(issue.value)
                if mapped_issue_type in kg_issue_types:
                    continue
                missing_issue_ctx = self._build_case_file_issue_context(
                    case_file=case_file,
                    issue_type=mapped_issue_type,
                )
                missing_issue_ctx.data_completeness = 0.3
                issue_contexts.append(missing_issue_ctx)

        issue_contexts.sort(
            key=lambda ctx: (
                ctx.claimed_amount is None,
                -(ctx.claimed_amount or 0.0),
            )
        )
        return issue_contexts

    def _decompose_from_kg(
        self,
        case_file: CaseFile,
        kg: Any,
        NodeType: Any,
        EdgeType: Any,
    ) -> List[IssueContext]:
        issue_nodes = kg.get_nodes_by_type(NodeType.ISSUE)
        timeline_events = self._timeline_events_from_kg(kg)
        lease_nodes = kg.get_nodes_by_type(NodeType.LEASE)
        claim_edges = [
            edge
            for edge in kg.get_edges_by_type(EdgeType.CLAIM_RELATES_TO)
            if edge.target_node_id
        ]

        contexts: List[IssueContext] = []
        for issue_node in issue_nodes:
            issue_type = map_str_to_issue_type(issue_node.issue_type)
            evidence_nodes = kg.get_evidence_for_issue(issue_node.node_id)
            claim_nodes = self._claim_nodes_for_issue(
                kg=kg,
                issue_node_id=issue_node.node_id,
                claim_edges=claim_edges,
                NodeType=NodeType,
            )

            tenant_claim = self._claim_detail_from_kg_nodes(
                claim_nodes=claim_nodes,
                issue_type=issue_type,
                party="tenant",
            )
            landlord_claim = self._claim_detail_from_kg_nodes(
                claim_nodes=claim_nodes,
                issue_type=issue_type,
                party="landlord",
            )
            kg_constraints = self._derive_kg_constraints(
                issue_type=issue_type,
                linked_evidence=evidence_nodes,
                lease_nodes=lease_nodes,
            )

            contexts.append(
                IssueContext(
                    issue_type=issue_type,
                    issue_description=getattr(issue_node, "description", "") or "",
                    tenant_claim=tenant_claim,
                    landlord_claim=landlord_claim,
                    supporting_evidence=evidence_nodes,
                    timeline_events=timeline_events,
                    kg_constraints=kg_constraints,
                    evidence_conflicts=self._derive_evidence_conflicts(
                        issue_type=issue_type,
                        tenant_claim=tenant_claim,
                        landlord_claim=landlord_claim,
                    ),
                    claimed_amount=self._primary_claimed_amount(
                        tenant_claim, landlord_claim
                    ),
                    data_completeness=self._calculate_data_completeness(
                        evidence_count=len(evidence_nodes),
                        tenant_claim=tenant_claim,
                        landlord_claim=landlord_claim,
                        timeline_count=len(timeline_events),
                        description=getattr(issue_node, "description", "") or "",
                    ),
                )
            )

        return contexts

    def _decompose_from_case_file(self, case_file: CaseFile) -> List[IssueContext]:
        contexts: List[IssueContext] = []
        for issue in case_file.issues:
            issue_type = map_str_to_issue_type(issue.value)
            contexts.append(
                self._build_case_file_issue_context(
                    case_file=case_file, issue_type=issue_type
                )
            )
        return contexts

    def _build_case_file_issue_context(
        self, case_file: CaseFile, issue_type: IssueType
    ) -> IssueContext:
        evidence = self._filter_case_file_evidence(issue_type, case_file.evidence)
        tenant_claim = self._claim_detail_from_case_file_claims(
            claims=case_file.tenant_claims,
            issue_type=issue_type,
            party="tenant",
        )
        landlord_claim = self._claim_detail_from_case_file_claims(
            claims=case_file.landlord_claims,
            issue_type=issue_type,
            party="landlord",
        )
        timeline_events = self._timeline_events_from_case_file(case_file)
        kg_constraints = self._derive_case_file_constraints(
            case_file, issue_type, evidence
        )

        return IssueContext(
            issue_type=issue_type,
            issue_description=issue_type.value.replace("_", " "),
            tenant_claim=tenant_claim,
            landlord_claim=landlord_claim,
            supporting_evidence=evidence,
            timeline_events=timeline_events,
            kg_constraints=kg_constraints,
            evidence_conflicts=self._derive_evidence_conflicts(
                issue_type=issue_type,
                tenant_claim=tenant_claim,
                landlord_claim=landlord_claim,
            ),
            claimed_amount=self._primary_claimed_amount(tenant_claim, landlord_claim),
            data_completeness=self._calculate_data_completeness(
                evidence_count=len(evidence),
                tenant_claim=tenant_claim,
                landlord_claim=landlord_claim,
                timeline_count=len(timeline_events),
                description=issue_type.value,
            ),
        )

    def _filter_case_file_evidence(
        self, issue_type: IssueType, evidence_items: Sequence[EvidenceItem]
    ) -> List[EvidenceItem]:
        filtered: List[EvidenceItem] = []
        for evidence in evidence_items:
            evidence_type = evidence.type.value
            mapped_issues = EVIDENCE_ISSUE_MAP.get(evidence_type, [])
            if not mapped_issues or issue_type.value in mapped_issues:
                filtered.append(evidence)
        return filtered

    def _claim_nodes_for_issue(
        self,
        kg: Any,
        issue_node_id: str,
        claim_edges: Iterable[Any],
        NodeType: Any,
    ) -> List[Any]:
        claim_nodes: List[Any] = []
        for edge in claim_edges:
            if edge.target_node_id != issue_node_id:
                continue
            node = kg.get_node(edge.source_node_id)
            if node and node.node_type == NodeType.CLAIMED_AMOUNT:
                claim_nodes.append(node)
        return claim_nodes

    def _claim_detail_from_kg_nodes(
        self,
        claim_nodes: Sequence[Any],
        issue_type: IssueType,
        party: str,
    ) -> Optional[ClaimDetail]:
        relevant_nodes = [
            node
            for node in claim_nodes
            if str(getattr(node, "claimant", "")).lower() == party
        ]
        if not relevant_nodes:
            return None

        total_amount = sum(
            float(getattr(node, "amount", 0.0) or 0.0) for node in relevant_nodes
        )
        descriptions = [
            getattr(node, "description", "")
            for node in relevant_nodes
            if getattr(node, "description", "")
        ]
        description = "; ".join(descriptions)

        return ClaimDetail(
            party=party,
            issue_type=issue_type,
            claimed_amount=total_amount,
            description=description,
            supporting_evidence_ids=[],
        )

    def _claim_detail_from_case_file_claims(
        self,
        claims: Sequence[ClaimedAmount],
        issue_type: IssueType,
        party: str,
    ) -> Optional[ClaimDetail]:
        matching = [
            claim
            for claim in claims
            if map_str_to_issue_type(claim.issue.value) == issue_type
        ]
        if not matching:
            return None

        amount = sum(claim.amount for claim in matching)
        description = "; ".join(
            claim.description for claim in matching if claim.description
        )
        evidence_ids: List[str] = []
        for claim in matching:
            evidence_ids.extend(claim.evidence_ids)

        return ClaimDetail(
            party=party,
            issue_type=issue_type,
            claimed_amount=amount,
            description=description,
            supporting_evidence_ids=list(dict.fromkeys(evidence_ids)),
        )

    def _timeline_events_from_kg(self, kg: Any) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for event_node in kg.get_timeline():
            events.append(
                TimelineEvent(
                    date=getattr(event_node, "event_date", None),
                    description=getattr(event_node, "description", "") or "",
                    source=getattr(event_node, "source", "kg"),
                    relevance_to_issue="case-level event",
                )
            )
        return events

    def _timeline_events_from_case_file(
        self, case_file: CaseFile
    ) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for raw_event in case_file.events:
            event_date = raw_event.get("date")
            parsed_date: Optional[date] = (
                event_date if isinstance(event_date, date) else None
            )
            events.append(
                TimelineEvent(
                    date=parsed_date,
                    description=str(raw_event.get("description", "") or ""),
                    source=str(raw_event.get("source", "case_file") or "case_file"),
                    relevance_to_issue=str(
                        raw_event.get("relevance", "case-level event")
                        or "case-level event"
                    ),
                )
            )
        return events

    def _derive_kg_constraints(
        self,
        issue_type: IssueType,
        linked_evidence: Sequence[Any],
        lease_nodes: Sequence[Any],
    ) -> List[str]:
        constraints: List[str] = []

        if issue_type in INVENTORY_SENSITIVE_ISSUES:
            has_inventory = any(
                "inventory" in str(getattr(evidence, "evidence_type", "")).lower()
                for evidence in linked_evidence
            )
            if not has_inventory:
                constraints.append("No check-in inventory provided")

        lease_node = lease_nodes[0] if lease_nodes else None
        if issue_type == IssueType.DEPOSIT_PROTECTION and lease_node is not None:
            deposit_protected = getattr(lease_node, "deposit_protected", None)
            scheme = getattr(lease_node, "deposit_scheme", None)
            start_date = getattr(lease_node, "deposit_received_date", None) or getattr(
                lease_node, "start_date", None
            )
            protection_date = getattr(lease_node, "protection_date", None)
            prescribed_info_provided = getattr(
                lease_node, "prescribed_info_provided", None
            )
            prescribed_info_date = getattr(lease_node, "prescribed_info_date", None)

            if deposit_protected is False:
                constraints.append("Deposit not protected")
            elif (
                start_date
                and protection_date
                and (protection_date - start_date).days > 30
            ):
                constraints.append("deposit not protected within 30 days")
            elif deposit_protected is True and scheme:
                constraints.append(f"Deposit protected with {scheme}")
            elif deposit_protected is True:
                constraints.append("Deposit protected")

            if prescribed_info_provided is False:
                constraints.append("Prescribed information not provided")
            elif (
                start_date
                and prescribed_info_date
                and (prescribed_info_date - start_date).days > 30
            ):
                days_late = (prescribed_info_date - start_date).days
                constraints.append(
                    f"Prescribed information served late ({days_late} days after deposit receipt or tenancy-start fallback)"
                )

        if issue_type == IssueType.RENT_ARREARS and lease_node is not None:
            if getattr(lease_node, "end_date", None):
                constraints.append("Tenancy end date available for arrears calculation")

        return constraints

    def _derive_case_file_constraints(
        self,
        case_file: CaseFile,
        issue_type: IssueType,
        linked_evidence: Sequence[EvidenceItem],
    ) -> List[str]:
        constraints: List[str] = []

        if issue_type in INVENTORY_SENSITIVE_ISSUES:
            has_inventory = any(
                "inventory" in evidence.type.value for evidence in linked_evidence
            )
            if not has_inventory:
                constraints.append("No check-in inventory provided")

        tenancy = case_file.tenancy
        if issue_type == IssueType.DEPOSIT_PROTECTION:
            deadline_anchor = tenancy.deposit_received_date or tenancy.start_date
            if tenancy.deposit_protected is False:
                constraints.append("Deposit not protected")
            elif deadline_anchor and tenancy.protection_date:
                if (tenancy.protection_date - deadline_anchor).days > 30:
                    constraints.append("deposit not protected within 30 days")
                elif tenancy.deposit_scheme:
                    constraints.append(
                        f"Deposit protected with {tenancy.deposit_scheme}"
                    )
                else:
                    constraints.append("Deposit protected")
            elif tenancy.deposit_protected and tenancy.deposit_scheme:
                constraints.append(f"Deposit protected with {tenancy.deposit_scheme}")
            elif tenancy.deposit_protected:
                constraints.append("Deposit protected")

            if tenancy.prescribed_info_provided is False:
                constraints.append("Prescribed information not provided")
            elif deadline_anchor and tenancy.prescribed_info_date:
                days_after_start = (
                    tenancy.prescribed_info_date - deadline_anchor
                ).days
                if days_after_start > 30:
                    constraints.append(
                        f"Prescribed information served late ({days_after_start} days after deposit receipt or tenancy-start fallback)"
                    )

        if issue_type == IssueType.RENT_ARREARS and tenancy.end_date:
            constraints.append("Tenancy end date available for arrears calculation")

        return constraints

    def _derive_evidence_conflicts(
        self,
        issue_type: IssueType,
        tenant_claim: Optional[ClaimDetail],
        landlord_claim: Optional[ClaimDetail],
    ) -> List[EvidenceConflict]:
        if not tenant_claim and not landlord_claim:
            return []
        if tenant_claim and landlord_claim:
            return [
                EvidenceConflict(
                    issue_type=issue_type,
                    tenant_position=tenant_claim.description,
                    landlord_position=landlord_claim.description,
                    tenant_evidence_ids=tenant_claim.supporting_evidence_ids,
                    landlord_evidence_ids=landlord_claim.supporting_evidence_ids,
                )
            ]
        return []

    def _calculate_data_completeness(
        self,
        evidence_count: int,
        tenant_claim: Optional[ClaimDetail],
        landlord_claim: Optional[ClaimDetail],
        timeline_count: int,
        description: str,
    ) -> float:
        evidence_score = min(evidence_count / 3.0, 1.0) * 0.4

        claims_score = 0.0
        if tenant_claim and landlord_claim:
            claims_score = 0.35
        elif tenant_claim or landlord_claim:
            claims_score = 0.2

        timeline_score = 0.15 if timeline_count > 0 else 0.0
        description_score = 0.1 if description else 0.0

        return round(
            min(
                evidence_score + claims_score + timeline_score + description_score, 1.0
            ),
            2,
        )

    def _primary_claimed_amount(
        self,
        tenant_claim: Optional[ClaimDetail],
        landlord_claim: Optional[ClaimDetail],
    ) -> Optional[float]:
        if landlord_claim and landlord_claim.claimed_amount is not None:
            return landlord_claim.claimed_amount
        if tenant_claim and tenant_claim.claimed_amount is not None:
            return tenant_claim.claimed_amount
        return None
