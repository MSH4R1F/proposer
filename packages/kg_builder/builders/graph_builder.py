"""
Knowledge Graph builder.

Converts CaseFile data into a structured Knowledge Graph.
"""

from datetime import date
from typing import List, Optional
from uuid import uuid4

import structlog

from ..models.nodes import (
    NodeType,
    PartyNode,
    PropertyNode,
    LeaseNode,
    EvidenceNode,
    EventNode,
    IssueNode,
    ClaimedAmountNode,
)
from ..models.edges import Edge, EdgeType
from ..models.graph import KnowledgeGraph

# Import CaseFile from llm_orchestrator (will be available when used together)
try:
    from llm_orchestrator.models.case_file import (
        CaseFile,
        PartyRole,
        DisputeIssue,
        EvidenceItem,
        ClaimedAmount,
    )
except ImportError:
    # For standalone testing
    CaseFile = None

logger = structlog.get_logger()


class GraphBuilder:
    """
    Builds a Knowledge Graph from a CaseFile.

    Extracts entities and relationships from the structured
    case file data to create a queryable graph.
    """

    def __init__(self, validate: bool = True):
        """
        Initialize the graph builder.

        Args:
            validate: Whether to validate the graph after building
        """
        self.validate = validate

    def build(self, case_file: "CaseFile") -> KnowledgeGraph:
        """
        Build a Knowledge Graph from a CaseFile.

        Args:
            case_file: The case file to convert

        Returns:
            KnowledgeGraph with nodes and edges
        """
        kg = KnowledgeGraph(case_id=case_file.case_id)

        # Build nodes
        party_nodes = self._build_party_nodes(case_file)
        property_node = self._build_property_node(case_file)
        lease_node = self._build_lease_node(case_file)
        evidence_nodes = self._build_evidence_nodes(case_file)
        issue_nodes = self._build_issue_nodes(case_file)
        claim_nodes = self._build_claim_nodes(case_file)
        event_nodes = self._build_event_nodes(case_file)

        # Add all nodes
        for node in party_nodes:
            kg.add_node(node)

        if property_node:
            kg.add_node(property_node)

        if lease_node:
            kg.add_node(lease_node)

        for node in evidence_nodes:
            kg.add_node(node)

        for node in issue_nodes:
            kg.add_node(node)

        for node in claim_nodes:
            kg.add_node(node)

        for node in event_nodes:
            kg.add_node(node)

        # Build edges
        edges = self._build_edges(
            kg,
            party_nodes,
            property_node,
            lease_node,
            evidence_nodes,
            issue_nodes,
            claim_nodes,
            case_file,
        )

        for edge in edges:
            kg.add_edge(edge)

        # Validate if requested
        if self.validate:
            from .validators import KGValidator
            validator = KGValidator()
            kg = validator.validate(kg)

        logger.info(
            "knowledge_graph_built",
            case_id=case_file.case_id,
            nodes=len(kg.nodes),
            edges=len(kg.edges),
            is_consistent=kg.is_consistent,
        )

        return kg

    def _build_party_nodes(self, case_file: "CaseFile") -> List[PartyNode]:
        """Build party nodes from case file."""
        nodes = []

        # User party (always exists)
        user_node = PartyNode(
            node_id=f"party_{case_file.user_role.value}",
            role=case_file.user_role.value,
            name=case_file.tenant_name if case_file.user_role.value == "tenant" else case_file.landlord_name,
            source="user_input",
        )
        nodes.append(user_node)

        # Other party
        other_role = "landlord" if case_file.user_role.value == "tenant" else "tenant"
        other_name = case_file.landlord_name if other_role == "landlord" else case_file.tenant_name
        if other_name or True:  # Always create the other party node
            other_node = PartyNode(
                node_id=f"party_{other_role}",
                role=other_role,
                name=other_name,
                source="user_input" if other_name else "inferred",
            )
            nodes.append(other_node)

        # Agent if mentioned
        if case_file.agent_name:
            agent_node = PartyNode(
                node_id="party_agent",
                role="agent",
                name=case_file.agent_name,
                source="user_input",
            )
            nodes.append(agent_node)

        return nodes

    def _build_property_node(self, case_file: "CaseFile") -> Optional[PropertyNode]:
        """Build property node from case file."""
        prop = case_file.property
        if not prop.address:
            return None

        return PropertyNode(
            node_id="property_main",
            address=prop.address,
            postcode=prop.postcode,
            property_type=prop.property_type,
            num_bedrooms=prop.num_bedrooms,
            furnished=prop.furnished,
            region=prop.region or prop.infer_region(),
            source="user_input",
        )

    def _build_lease_node(self, case_file: "CaseFile") -> Optional[LeaseNode]:
        """Build lease node from case file."""
        ten = case_file.tenancy
        if not ten.start_date and not ten.deposit_amount:
            return None

        return LeaseNode(
            node_id="lease_main",
            start_date=ten.start_date,
            end_date=ten.end_date,
            tenancy_type=ten.tenancy_type,
            monthly_rent=ten.monthly_rent,
            deposit_amount=ten.deposit_amount,
            deposit_protected=ten.deposit_protected,
            deposit_scheme=ten.deposit_scheme,
            protection_date=ten.protection_date,
            source="user_input",
        )

    def _build_evidence_nodes(self, case_file: "CaseFile") -> List[EvidenceNode]:
        """Build evidence nodes from case file."""
        nodes = []

        for ev in case_file.evidence:
            node = EvidenceNode(
                node_id=f"evidence_{ev.id}",
                evidence_type=ev.type.value,
                description=ev.description,
                file_url=ev.file_url,
                date_created=ev.date_created,
                confidence=ev.confidence,
                source=ev.source,
            )
            nodes.append(node)

        return nodes

    def _build_issue_nodes(self, case_file: "CaseFile") -> List[IssueNode]:
        """Build issue nodes from case file."""
        nodes = []

        for i, issue in enumerate(case_file.issues):
            # Get description from narrative if available
            description = self._get_issue_description(issue, case_file)

            node = IssueNode(
                node_id=f"issue_{issue.value}",
                issue_type=issue.value,
                description=description,
                disputed=True,
                source="user_input",
            )
            nodes.append(node)

        return nodes

    def _get_issue_description(self, issue: "DisputeIssue", case_file: "CaseFile") -> str:
        """Get a description for an issue from the case file."""
        # Try to find claims related to this issue
        claims = case_file.tenant_claims + case_file.landlord_claims
        for claim in claims:
            if claim.issue == issue:
                return claim.description

        # Default descriptions
        descriptions = {
            "cleaning": "Dispute over cleaning charges",
            "damage": "Dispute over damage claims",
            "rent_arrears": "Dispute over unpaid rent",
            "deposit_protection": "Deposit protection compliance issue",
            "inventory_dispute": "Dispute over inventory condition",
            "garden": "Dispute over garden maintenance",
            "decoration": "Dispute over decoration/redecoration",
            "fair_wear_and_tear": "Dispute over fair wear and tear assessment",
            "missing_items": "Dispute over missing items",
            "utilities": "Dispute over utility charges",
        }

        return descriptions.get(issue.value, f"Dispute regarding {issue.value}")

    def _build_claim_nodes(self, case_file: "CaseFile") -> List[ClaimedAmountNode]:
        """Build claim nodes from case file."""
        nodes = []

        for claim in case_file.tenant_claims:
            node = ClaimedAmountNode(
                node_id=f"claim_tenant_{claim.id}",
                claimant="tenant",
                amount=claim.amount,
                issue_type=claim.issue.value,
                description=claim.description,
                supported_by_evidence=len(claim.evidence_ids) > 0,
                source="user_input",
            )
            nodes.append(node)

        for claim in case_file.landlord_claims:
            node = ClaimedAmountNode(
                node_id=f"claim_landlord_{claim.id}",
                claimant="landlord",
                amount=claim.amount,
                issue_type=claim.issue.value,
                description=claim.description,
                supported_by_evidence=len(claim.evidence_ids) > 0,
                source="user_input",
            )
            nodes.append(node)

        return nodes

    def _build_event_nodes(self, case_file: "CaseFile") -> List[EventNode]:
        """Build event nodes from case file data."""
        nodes = []

        # Tenancy start event
        if case_file.tenancy.start_date:
            node = EventNode(
                node_id="event_tenancy_start",
                event_type="tenancy_start",
                event_date=case_file.tenancy.start_date,
                description="Tenancy started",
                source="user_input",
            )
            nodes.append(node)

        # Tenancy end event
        if case_file.tenancy.end_date:
            node = EventNode(
                node_id="event_tenancy_end",
                event_type="tenancy_end",
                event_date=case_file.tenancy.end_date,
                description="Tenancy ended",
                source="user_input",
            )
            nodes.append(node)

        # Deposit protection event
        if case_file.tenancy.protection_date:
            node = EventNode(
                node_id="event_deposit_protected",
                event_type="deposit_protected",
                event_date=case_file.tenancy.protection_date,
                description=f"Deposit protected with {case_file.tenancy.deposit_scheme or 'scheme'}",
                source="user_input",
            )
            nodes.append(node)

        # Add any events from the case file events list
        for i, event_data in enumerate(case_file.events):
            if isinstance(event_data, dict):
                node = EventNode(
                    node_id=f"event_{i}",
                    event_type=event_data.get("type", "other"),
                    event_date=event_data.get("date"),
                    description=event_data.get("description", ""),
                    source="user_input",
                )
                nodes.append(node)

        return nodes

    def _build_edges(
        self,
        kg: KnowledgeGraph,
        party_nodes: List[PartyNode],
        property_node: Optional[PropertyNode],
        lease_node: Optional[LeaseNode],
        evidence_nodes: List[EvidenceNode],
        issue_nodes: List[IssueNode],
        claim_nodes: List[ClaimedAmountNode],
        case_file: "CaseFile",
    ) -> List[Edge]:
        """Build edges connecting the nodes."""
        edges = []

        # Find tenant and landlord nodes
        tenant_node = next((n for n in party_nodes if n.role == "tenant"), None)
        landlord_node = next((n for n in party_nodes if n.role == "landlord"), None)

        # Party -> Property edges
        if property_node:
            if landlord_node:
                edges.append(Edge.create(
                    EdgeType.PARTY_OWNS,
                    landlord_node.node_id,
                    property_node.node_id,
                    description="Landlord owns property",
                ))
            if tenant_node:
                edges.append(Edge.create(
                    EdgeType.PARTY_RENTS,
                    tenant_node.node_id,
                    property_node.node_id,
                    description="Tenant rents property",
                ))

        # Lease -> Property edge
        if lease_node and property_node:
            edges.append(Edge.create(
                EdgeType.LEASE_FOR,
                lease_node.node_id,
                property_node.node_id,
                description="Lease agreement for property",
            ))

        # Party -> Claim edges
        for claim in claim_nodes:
            party_node = tenant_node if claim.claimant == "tenant" else landlord_node
            if party_node:
                edges.append(Edge.create(
                    EdgeType.PARTY_CLAIMS,
                    party_node.node_id,
                    claim.node_id,
                    description=f"{claim.claimant} claims £{claim.amount}",
                ))

        # Claim -> Issue edges
        for claim in claim_nodes:
            issue_node = next(
                (n for n in issue_nodes if n.issue_type == claim.issue_type),
                None
            )
            if issue_node:
                edges.append(Edge.create(
                    EdgeType.CLAIM_RELATES_TO,
                    claim.node_id,
                    issue_node.node_id,
                    description=f"Claim relates to {claim.issue_type}",
                ))

        # Evidence -> Issue edges
        for evidence in evidence_nodes:
            # Link evidence to relevant issues based on type
            relevant_issues = self._get_relevant_issues_for_evidence(evidence, issue_nodes)
            for issue in relevant_issues:
                edges.append(Edge.create(
                    EdgeType.EVIDENCE_RELATES_TO,
                    evidence.node_id,
                    issue.node_id,
                    confidence=0.7,  # Default confidence
                    description=f"{evidence.evidence_type} relates to {issue.issue_type}",
                ))

        # Link evidence to claims by ID
        for claim in case_file.tenant_claims + case_file.landlord_claims:
            for ev_id in claim.evidence_ids:
                evidence_node = next(
                    (n for n in evidence_nodes if n.node_id == f"evidence_{ev_id}"),
                    None
                )
                claim_node = next(
                    (n for n in claim_nodes if claim.id in n.node_id),
                    None
                )
                if evidence_node and claim_node:
                    edges.append(Edge.create(
                        EdgeType.EVIDENCE_SUPPORTS,
                        evidence_node.node_id,
                        claim_node.node_id,
                        description="Evidence supports claim",
                    ))

        # Temporal edges between events
        event_nodes = kg.get_nodes_by_type(NodeType.EVENT)
        sorted_events = sorted(
            [e for e in event_nodes if e.event_date],
            key=lambda x: x.event_date,
        )

        for i in range(len(sorted_events) - 1):
            edges.append(Edge.create(
                EdgeType.EVENT_BEFORE,
                sorted_events[i].node_id,
                sorted_events[i + 1].node_id,
                description=f"{sorted_events[i].event_type} before {sorted_events[i+1].event_type}",
            ))

        return edges

    def _get_relevant_issues_for_evidence(
        self, evidence: EvidenceNode, issues: List[IssueNode]
    ) -> List[IssueNode]:
        """Determine which issues an evidence type is relevant to."""
        evidence_issue_map = {
            "inventory_checkin": ["cleaning", "damage", "fair_wear_and_tear"],
            "inventory_checkout": ["cleaning", "damage", "fair_wear_and_tear"],
            "photos_before": ["cleaning", "damage", "decoration"],
            "photos_after": ["cleaning", "damage", "decoration"],
            "receipts": ["cleaning", "damage"],
            "invoices": ["cleaning", "damage"],
            "deposit_certificate": ["deposit_protection"],
            "tenancy_agreement": ["rent_arrears", "deposit_protection"],
            "correspondence": [],  # Relates to all
        }

        relevant_types = evidence_issue_map.get(evidence.evidence_type, [])

        if not relevant_types:
            # Correspondence and other relates to all
            return issues

        return [i for i in issues if i.issue_type in relevant_types]
