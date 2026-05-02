"""
Knowledge Graph node types.

Defines the structured entities extracted from case files.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of nodes in the Knowledge Graph."""

    PARTY = "party"
    LEASE = "lease"
    EVIDENCE = "evidence"
    EVENT = "event"
    ISSUE = "issue"
    CLAIMED_AMOUNT = "claimed_amount"
    PROPERTY = "property"


class BaseNode(BaseModel):
    """Base class for all Knowledge Graph nodes."""

    node_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    node_type: NodeType
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = Field(default="user_input")  # user_input, document, inferred
    source_text: Optional[str] = None  # Original text this was extracted from
    created_at: str = Field(default_factory=lambda: date.today().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # SHA-61 / SHA-119: ontology-aware routing metadata. All defaulted so
    # that existing call sites and persisted JSON continue to deserialize
    # without modification. Populated at attach-time by the GraphBuilder
    # (or set explicitly for cross-domain Evidence bridges).
    domain_id: Optional[str] = None
    forum: Optional[str] = None
    source_ref: Optional[str] = None  # opaque pointer to RAG/citation source
    source_domain: Optional[str] = None  # cross-domain bridge marker
    provenance: Dict[str, Any] = Field(default_factory=dict)


class PartyNode(BaseNode):
    """Represents a party in the dispute (tenant, landlord, agent)."""

    node_type: NodeType = NodeType.PARTY
    role: str  # tenant, landlord, agent, guarantor
    name: Optional[str] = None
    is_company: bool = False
    company_name: Optional[str] = None
    contact_info: Optional[str] = None


class PropertyNode(BaseNode):
    """Represents the rental property."""

    node_type: NodeType = NodeType.PROPERTY
    address: Optional[str] = None
    postcode: Optional[str] = None
    property_type: Optional[str] = None  # flat, house, HMO, room
    num_bedrooms: Optional[int] = None
    furnished: Optional[bool] = None
    region: Optional[str] = None  # Tribunal region


class LeaseNode(BaseNode):
    """Represents the tenancy agreement."""

    node_type: NodeType = NodeType.LEASE
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    tenancy_type: Optional[str] = None  # AST, periodic
    monthly_rent: Optional[float] = None
    deposit_amount: Optional[float] = None
    deposit_received_date: Optional[date] = None
    deposit_protected: Optional[bool] = None
    deposit_scheme: Optional[str] = None
    protection_date: Optional[date] = None
    prescribed_info_provided: Optional[bool] = None
    prescribed_info_date: Optional[date] = None


class EvidenceNode(BaseNode):
    """Represents a piece of evidence."""

    node_type: NodeType = NodeType.EVIDENCE
    evidence_type: str  # inventory_checkin, photos_before, etc.
    description: str
    file_url: Optional[str] = None
    date_created: Optional[date] = None
    quality: Optional[str] = None  # good, partial, poor, missing


class EventNode(BaseNode):
    """Represents a significant event in the timeline."""

    node_type: NodeType = NodeType.EVENT
    event_type: str  # tenancy_start, tenancy_end, inspection, damage_discovered, etc.
    event_date: Optional[date] = None
    description: str
    actors: List[str] = Field(default_factory=list)  # Who was involved


class IssueNode(BaseNode):
    """Represents a dispute issue."""

    node_type: NodeType = NodeType.ISSUE
    issue_type: str  # cleaning, damage, deposit_protection, etc.
    description: str
    disputed: bool = True
    severity: Optional[str] = None  # minor, moderate, major
    location: Optional[str] = None  # Where in property (kitchen, bathroom, etc.)


class ClaimedAmountNode(BaseNode):
    """Represents a monetary claim by a party."""

    node_type: NodeType = NodeType.CLAIMED_AMOUNT
    claimant: str  # tenant or landlord
    amount: float
    issue_type: str
    description: str
    supported_by_evidence: bool = False
    reasonableness: Optional[str] = None  # reasonable, excessive, inadequate


# Type alias for any node
Node = Union[
    PartyNode,
    PropertyNode,
    LeaseNode,
    EvidenceNode,
    EventNode,
    IssueNode,
    ClaimedAmountNode,
]
