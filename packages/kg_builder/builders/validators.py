"""
Knowledge Graph validators.

Validates temporal logic, evidence chains, and consistency.
"""

from datetime import date, timedelta
from typing import List, Optional

import structlog

from ..models.nodes import NodeType, LeaseNode, EventNode
from ..models.edges import EdgeType
from ..models.graph import KnowledgeGraph

logger = structlog.get_logger()


class KGValidator:
    """
    Validates Knowledge Graph consistency.

    Checks for:
    - Temporal logic (events in valid order)
    - Evidence chain validity
    - Required relationships
    - Data completeness
    """

    def __init__(self, strict: bool = False):
        """
        Initialize the validator.

        Args:
            strict: If True, mark graph as inconsistent on warnings
        """
        self.strict = strict

    def validate(self, kg: KnowledgeGraph) -> KnowledgeGraph:
        """
        Validate a Knowledge Graph.

        Args:
            kg: The graph to validate

        Returns:
            The same graph with validation results populated
        """
        kg.validation_errors = []
        kg.validation_warnings = []

        # Run all validations
        self._validate_temporal_logic(kg)
        self._validate_deposit_protection(kg)
        self._validate_evidence_coverage(kg)
        self._validate_claim_support(kg)
        self._validate_required_nodes(kg)

        # Determine consistency
        kg.is_consistent = len(kg.validation_errors) == 0
        if self.strict and kg.validation_warnings:
            kg.is_consistent = False

        logger.info(
            "knowledge_graph_validated",
            case_id=kg.case_id,
            errors=len(kg.validation_errors),
            warnings=len(kg.validation_warnings),
            is_consistent=kg.is_consistent,
        )

        return kg

    def _validate_temporal_logic(self, kg: KnowledgeGraph) -> None:
        """Validate that events are in logical temporal order."""
        # Get lease and events
        lease_nodes = kg.get_nodes_by_type(NodeType.LEASE)
        event_nodes = kg.get_nodes_by_type(NodeType.EVENT)

        if not lease_nodes:
            return

        lease = lease_nodes[0]

        # Check tenancy dates make sense
        if lease.start_date and lease.end_date:
            if lease.end_date < lease.start_date:
                kg.validation_errors.append(
                    "Tenancy end date is before start date"
                )

            # Check duration is reasonable (< 20 years)
            duration = (lease.end_date - lease.start_date).days
            if duration > 7300:  # ~20 years
                kg.validation_warnings.append(
                    f"Tenancy duration seems unusually long: {duration} days"
                )

        # Check deposit protection timing
        if lease.protection_date and lease.start_date:
            days_to_protect = (lease.protection_date - lease.start_date).days

            if days_to_protect < 0:
                kg.validation_warnings.append(
                    "Deposit appears to be protected before tenancy started"
                )
            elif days_to_protect > 30:
                kg.validation_warnings.append(
                    f"Deposit protected {days_to_protect} days after tenancy start (> 30 day limit)"
                )

        # Check events are within tenancy period
        for event in event_nodes:
            if not event.event_date:
                continue

            if lease.start_date and event.event_date < lease.start_date:
                if event.event_type not in ["tenancy_start", "deposit_protected"]:
                    kg.validation_warnings.append(
                        f"Event '{event.event_type}' occurred before tenancy started"
                    )

    def _validate_deposit_protection(self, kg: KnowledgeGraph) -> None:
        """Validate deposit protection logic."""
        lease_nodes = kg.get_nodes_by_type(NodeType.LEASE)
        issue_nodes = kg.get_nodes_by_type(NodeType.ISSUE)

        if not lease_nodes:
            return

        lease = lease_nodes[0]

        # Check if deposit protection is an issue
        has_protection_issue = any(
            n.issue_type == "deposit_protection" for n in issue_nodes
        )

        if has_protection_issue:
            # If claiming protection issue, deposit should be unprotected or late
            if lease.deposit_protected is True:
                if lease.protection_date and lease.start_date:
                    days = (lease.protection_date - lease.start_date).days
                    if days <= 30:
                        kg.validation_warnings.append(
                            "Deposit protection issue claimed but deposit appears to be "
                            "protected within 30 days"
                        )

    def _validate_evidence_coverage(self, kg: KnowledgeGraph) -> None:
        """Check that issues have supporting evidence."""
        issue_nodes = kg.get_nodes_by_type(NodeType.ISSUE)
        evidence_edges = kg.get_edges_by_type(EdgeType.EVIDENCE_RELATES_TO)
        evidence_support = kg.get_edges_by_type(EdgeType.EVIDENCE_SUPPORTS)

        # Check each issue has at least one evidence link
        issues_without_evidence = []
        for issue in issue_nodes:
            has_evidence = any(
                e.target_node_id == issue.node_id
                for e in evidence_edges + evidence_support
            )
            if not has_evidence:
                issues_without_evidence.append(issue.issue_type)

        if issues_without_evidence:
            kg.validation_warnings.append(
                f"Issues without linked evidence: {', '.join(issues_without_evidence)}"
            )

    def _validate_claim_support(self, kg: KnowledgeGraph) -> None:
        """Check that claims have supporting evidence or relate to issues."""
        claim_nodes = kg.get_nodes_by_type(NodeType.CLAIMED_AMOUNT)

        for claim in claim_nodes:
            edges = kg.get_edges_for_node(claim.node_id)

            # Check for evidence support
            has_evidence = any(
                e.edge_type == EdgeType.EVIDENCE_SUPPORTS
                for e in edges
            )

            # Check for issue relation
            has_issue = any(
                e.edge_type == EdgeType.CLAIM_RELATES_TO
                for e in edges
            )

            if not has_evidence and not has_issue:
                kg.validation_warnings.append(
                    f"Claim '{claim.description[:50]}' has no supporting evidence or issue link"
                )

    def _validate_required_nodes(self, kg: KnowledgeGraph) -> None:
        """Check that required nodes exist."""
        # Should have at least 2 parties
        parties = kg.get_nodes_by_type(NodeType.PARTY)
        if len(parties) < 2:
            kg.validation_warnings.append(
                "Expected both tenant and landlord party nodes"
            )

        # Should have a property or lease
        properties = kg.get_nodes_by_type(NodeType.PROPERTY)
        leases = kg.get_nodes_by_type(NodeType.LEASE)

        if not properties and not leases:
            kg.validation_warnings.append(
                "No property or lease information found"
            )

        # Should have at least one issue
        issues = kg.get_nodes_by_type(NodeType.ISSUE)
        if not issues:
            kg.validation_warnings.append(
                "No dispute issues identified"
            )


def check_temporal_consistency(
    start_date: Optional[date],
    end_date: Optional[date],
    events: List[EventNode],
) -> List[str]:
    """
    Check temporal consistency of a set of dates and events.

    Returns list of issues found.
    """
    issues = []

    if start_date and end_date and end_date < start_date:
        issues.append("End date before start date")

    for event in events:
        if event.event_date:
            if start_date and event.event_date < start_date:
                issues.append(f"Event {event.event_type} before start date")
            if end_date and event.event_date > end_date:
                issues.append(f"Event {event.event_type} after end date")

    return issues
