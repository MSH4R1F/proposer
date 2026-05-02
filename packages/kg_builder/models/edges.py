"""
Knowledge Graph edge types.

Defines relationships between nodes in the Knowledge Graph.
"""

from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class EdgeType(str, Enum):
    """Types of edges (relationships) in the Knowledge Graph."""
    # Evidence relationships
    EVIDENCE_SUPPORTS = "evidence_supports"
    EVIDENCE_REFUTES = "evidence_refutes"
    EVIDENCE_RELATES_TO = "evidence_relates_to"

    # Temporal relationships
    EVENT_BEFORE = "event_before"
    EVENT_AFTER = "event_after"
    EVENT_DURING = "event_during"

    # Party relationships
    PARTY_OWNS = "party_owns"
    PARTY_RENTS = "party_rents"
    PARTY_MANAGES = "party_manages"
    PARTY_CLAIMS = "party_claims"

    # Issue relationships
    CLAIM_RELATES_TO = "claim_relates_to"
    ISSUE_INVOLVES = "issue_involves"
    ISSUE_CAUSED_BY = "issue_caused_by"

    # Lease relationships
    LEASE_FOR = "lease_for"
    DEPOSIT_PROTECTED_BY = "deposit_protected_by"


class Edge(BaseModel):
    """
    Represents a relationship between two nodes.

    Edges are directional: source_node -> target_node
    """
    edge_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    edge_type: EdgeType
    source_node_id: str
    target_node_id: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = Field(default="user_input")  # user_input, inferred, document
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # SHA-61 / SHA-119: ontology-aware routing metadata. All defaulted so
    # existing call sites and persisted JSON continue to round-trip. The
    # ``source_domain`` field is the explicit cross-domain bridge marker;
    # it is read by ``packages.kg_builder.ontology.validators`` to decide
    # whether a cross-domain edge is permitted.
    domain_id: Optional[str] = None
    forum: Optional[str] = None
    source_ref: Optional[str] = None
    source_domain: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        edge_type: EdgeType,
        source_id: str,
        target_id: str,
        confidence: float = 1.0,
        source: str = "user_input",
        description: Optional[str] = None,
    ) -> "Edge":
        """Create an edge between two nodes."""
        return cls(
            edge_type=edge_type,
            source_node_id=source_id,
            target_node_id=target_id,
            confidence=confidence,
            source=source,
            description=description,
        )

    def __str__(self) -> str:
        """String representation of the edge."""
        return f"{self.source_node_id} --[{self.edge_type.value}]--> {self.target_node_id}"
