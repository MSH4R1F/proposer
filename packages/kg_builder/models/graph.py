"""
Knowledge Graph container.

The main data structure that holds nodes and edges for a case.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Type
from uuid import uuid4

from pydantic import BaseModel, Field

from .nodes import (
    BaseNode,
    NodeType,
    PartyNode,
    PropertyNode,
    LeaseNode,
    EvidenceNode,
    EventNode,
    IssueNode,
    ClaimedAmountNode,
)
from .edges import Edge, EdgeType


class KnowledgeGraph(BaseModel):
    """
    JSON-based Knowledge Graph for MVP.

    Stores structured facts about a dispute with explicit
    relationships and confidence scores.
    """

    graph_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    case_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Graph data
    nodes: List[BaseNode] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

    # Validation state
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    validation_info: List[str] = Field(default_factory=list)
    is_consistent: bool = True
    data_quality_tier: str = Field(default="minimal")

    # SHA-20 Phase 3: domain routing + reproducibility hashes. The KG inherits
    # its domain from the source CaseFile; defaults preserve legacy deposit
    # behaviour so already-persisted graphs round-trip cleanly.
    domain_id: str = "housing.deposit.v1"
    domain_version: str = "v1"
    domain_spec_hash: Optional[str] = None
    ontology_hash: Optional[str] = None

    # SHA-20 Phase 5: ontology routing. ``ontology_id`` is set when the
    # graph is built/validated against a specific ontology spec; it
    # defaults to ``None`` so already-persisted graphs round-trip.
    ontology_id: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # SHA-61 / SHA-119: ontology + domain helpers
    # ------------------------------------------------------------------ #

    @property
    def primary_domain_id(self) -> str:
        """The graph's primary domain id.

        Reads the top-level ``domain_id`` field and mirrors any value
        present under ``metadata['domain_id']`` for backward compat.
        """
        # Prefer top-level field; fall back to legacy metadata mirror.
        if self.domain_id:
            return self.domain_id
        meta_domain = self.metadata.get("domain_id") if isinstance(self.metadata, dict) else None
        return meta_domain or "housing.deposit.v1"

    def set_primary_domain(self, domain_id: str) -> None:
        """Set the primary domain id and mirror it into metadata.

        Mirrors are kept for backwards compat with code that read
        ``kg.metadata['domain_id']`` before SHA-20 Phase 3.
        """
        self.domain_id = domain_id
        if not isinstance(self.metadata, dict):
            self.metadata = {}
        self.metadata["domain_id"] = domain_id

    def add_node(self, node: BaseNode) -> bool:
        """
        Add a node to the graph.

        Returns True if added, False if duplicate.
        """
        if self._node_exists(node.node_id):
            return False
        self.nodes.append(node)
        self.updated_at = datetime.now().isoformat()
        return True

    def add_edge(self, edge: Edge) -> bool:
        """
        Add an edge to the graph.

        Validates that both source and target nodes exist.
        Returns True if added, False if validation fails.
        """
        if not self._node_exists(edge.source_node_id):
            self.validation_errors.append(
                f"Edge source node not found: {edge.source_node_id}"
            )
            return False

        if not self._node_exists(edge.target_node_id):
            self.validation_errors.append(
                f"Edge target node not found: {edge.target_node_id}"
            )
            return False

        # Check for duplicate edges
        for existing in self.edges:
            if (
                existing.source_node_id == edge.source_node_id
                and existing.target_node_id == edge.target_node_id
                and existing.edge_type == edge.edge_type
            ):
                return False

        self.edges.append(edge)
        self.updated_at = datetime.now().isoformat()
        return True

    def _node_exists(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        return any(n.node_id == node_id for n in self.nodes)

    def get_node(self, node_id: str) -> Optional[BaseNode]:
        """Get a node by ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_nodes_by_type(self, node_type: NodeType) -> List[BaseNode]:
        """Get all nodes of a specific type."""
        return [n for n in self.nodes if n.node_type == node_type]

    def get_edges_for_node(self, node_id: str, direction: str = "both") -> List[Edge]:
        """
        Get all edges connected to a node.

        Args:
            node_id: The node to find edges for
            direction: "outgoing", "incoming", or "both"
        """
        edges = []
        for edge in self.edges:
            if direction in ("both", "outgoing") and edge.source_node_id == node_id:
                edges.append(edge)
            elif direction in ("both", "incoming") and edge.target_node_id == node_id:
                edges.append(edge)
        return edges

    def get_edges_by_type(self, edge_type: EdgeType) -> List[Edge]:
        """Get all edges of a specific type."""
        return [e for e in self.edges if e.edge_type == edge_type]

    def get_connected_nodes(self, node_id: str) -> List[BaseNode]:
        """Get all nodes connected to a given node."""
        connected_ids: Set[str] = set()
        for edge in self.edges:
            if edge.source_node_id == node_id:
                connected_ids.add(edge.target_node_id)
            elif edge.target_node_id == node_id:
                connected_ids.add(edge.source_node_id)

        return [n for n in self.nodes if n.node_id in connected_ids]

    def find_path(
        self, start_id: str, end_id: str, max_depth: int = 5
    ) -> Optional[List[str]]:
        """
        Find a path between two nodes using BFS.

        Returns list of node IDs or None if no path exists.
        """
        if start_id == end_id:
            return [start_id]

        visited: Set[str] = {start_id}
        queue: List[List[str]] = [[start_id]]

        while queue:
            path = queue.pop(0)
            if len(path) > max_depth:
                continue

            current = path[-1]
            for edge in self.get_edges_for_node(current):
                next_node = (
                    edge.target_node_id
                    if edge.source_node_id == current
                    else edge.source_node_id
                )

                if next_node == end_id:
                    return path + [next_node]

                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(path + [next_node])

        return None

    def get_evidence_for_issue(self, issue_node_id: str) -> List[EvidenceNode]:
        """Get all evidence nodes that support or refute an issue."""
        evidence_nodes = []
        for edge in self.edges:
            if edge.target_node_id == issue_node_id and edge.edge_type in (
                EdgeType.EVIDENCE_SUPPORTS,
                EdgeType.EVIDENCE_REFUTES,
                EdgeType.EVIDENCE_RELATES_TO,
            ):
                node = self.get_node(edge.source_node_id)
                if node and node.node_type == NodeType.EVIDENCE:
                    evidence_nodes.append(node)  # type: ignore
        return evidence_nodes

    def get_timeline(self) -> List[EventNode]:
        """Get all events sorted by date."""
        events = self.get_nodes_by_type(NodeType.EVENT)
        # Sort by date, putting None dates at the end
        return sorted(
            events,  # type: ignore
            key=lambda e: e.event_date or datetime.max.date(),
        )

    def to_summary(self) -> Dict[str, Any]:
        """Generate a summary of the knowledge graph."""
        return {
            "graph_id": self.graph_id,
            "case_id": self.case_id,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes_by_type": {
                nt.value: len(self.get_nodes_by_type(nt)) for nt in NodeType
            },
            "is_consistent": self.is_consistent,
            "validation_errors": len(self.validation_errors),
            "validation_warnings": len(self.validation_warnings),
        }

    def to_cypher(self) -> str:
        """
        Generate Cypher statements for Neo4j import.

        Useful for future migration to Neo4j.
        """
        statements = []

        # Create nodes
        for node in self.nodes:
            props = node.model_dump(exclude={"node_type", "metadata"})
            props_str = ", ".join(
                f"{k}: {repr(v)}" for k, v in props.items() if v is not None
            )
            statements.append(
                f"CREATE (:{node.node_type.value.title()} {{{props_str}}})"
            )

        # Create edges
        for edge in self.edges:
            statements.append(
                f"MATCH (a {{node_id: '{edge.source_node_id}'}}), "
                f"(b {{node_id: '{edge.target_node_id}'}}) "
                f"CREATE (a)-[:{edge.edge_type.value.upper()}]->(b)"
            )

        return ";\n".join(statements)

    model_config = {"arbitrary_types_allowed": True}
