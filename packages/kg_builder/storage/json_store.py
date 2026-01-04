"""
JSON-based Knowledge Graph storage.

Simple file-based storage for MVP, can be migrated to Neo4j later.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

import structlog

from ..models.graph import KnowledgeGraph
from ..models.nodes import (
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
from ..models.edges import Edge, EdgeType

logger = structlog.get_logger()


class JSONGraphStore:
    """
    JSON-based storage for Knowledge Graphs.

    Provides simple file-based persistence for MVP.
    Each case gets its own JSON file.
    """

    def __init__(self, storage_dir: Path):
        """
        Initialize the JSON store.

        Args:
            storage_dir: Directory to store JSON files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, case_id: str) -> Path:
        """Get the file path for a case's knowledge graph."""
        return self.storage_dir / f"kg_{case_id}.json"

    def save(self, kg: KnowledgeGraph) -> bool:
        """
        Save a Knowledge Graph to JSON.

        Args:
            kg: The knowledge graph to save

        Returns:
            True if successful
        """
        path = self._get_path(kg.case_id)

        try:
            # Convert to serializable format
            data = self._serialize_graph(kg)

            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(
                "knowledge_graph_saved",
                case_id=kg.case_id,
                path=str(path),
                nodes=len(kg.nodes),
                edges=len(kg.edges),
            )
            return True

        except Exception as e:
            logger.error("knowledge_graph_save_failed", error=str(e))
            return False

    def load(self, case_id: str) -> Optional[KnowledgeGraph]:
        """
        Load a Knowledge Graph from JSON.

        Args:
            case_id: The case ID to load

        Returns:
            KnowledgeGraph or None if not found
        """
        path = self._get_path(case_id)

        if not path.exists():
            logger.debug("knowledge_graph_not_found", case_id=case_id)
            return None

        try:
            with open(path) as f:
                data = json.load(f)

            kg = self._deserialize_graph(data)

            logger.info(
                "knowledge_graph_loaded",
                case_id=case_id,
                nodes=len(kg.nodes),
                edges=len(kg.edges),
            )
            return kg

        except Exception as e:
            logger.error("knowledge_graph_load_failed", error=str(e))
            return None

    def delete(self, case_id: str) -> bool:
        """
        Delete a Knowledge Graph.

        Args:
            case_id: The case ID to delete

        Returns:
            True if deleted, False if not found
        """
        path = self._get_path(case_id)

        if path.exists():
            path.unlink()
            logger.info("knowledge_graph_deleted", case_id=case_id)
            return True

        return False

    def list_all(self) -> List[str]:
        """
        List all stored case IDs.

        Returns:
            List of case IDs
        """
        case_ids = []
        for path in self.storage_dir.glob("kg_*.json"):
            case_id = path.stem.replace("kg_", "")
            case_ids.append(case_id)
        return case_ids

    def exists(self, case_id: str) -> bool:
        """Check if a knowledge graph exists for a case."""
        return self._get_path(case_id).exists()

    def _serialize_graph(self, kg: KnowledgeGraph) -> Dict:
        """Convert KnowledgeGraph to serializable dict."""
        return {
            "graph_id": kg.graph_id,
            "case_id": kg.case_id,
            "created_at": kg.created_at,
            "updated_at": kg.updated_at,
            "nodes": [self._serialize_node(n) for n in kg.nodes],
            "edges": [e.model_dump() for e in kg.edges],
            "validation_errors": kg.validation_errors,
            "validation_warnings": kg.validation_warnings,
            "is_consistent": kg.is_consistent,
            "metadata": kg.metadata,
        }

    def _serialize_node(self, node: BaseNode) -> Dict:
        """Serialize a node with its type."""
        data = node.model_dump()
        data["_node_class"] = node.__class__.__name__
        return data

    def _deserialize_graph(self, data: Dict) -> KnowledgeGraph:
        """Reconstruct KnowledgeGraph from dict."""
        # Deserialize nodes
        nodes = []
        for node_data in data.get("nodes", []):
            node = self._deserialize_node(node_data)
            if node:
                nodes.append(node)

        # Deserialize edges
        edges = []
        for edge_data in data.get("edges", []):
            try:
                edge = Edge.model_validate(edge_data)
                edges.append(edge)
            except Exception as e:
                logger.warning("edge_deserialize_failed", error=str(e))

        return KnowledgeGraph(
            graph_id=data.get("graph_id", ""),
            case_id=data.get("case_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            nodes=nodes,
            edges=edges,
            validation_errors=data.get("validation_errors", []),
            validation_warnings=data.get("validation_warnings", []),
            is_consistent=data.get("is_consistent", True),
            metadata=data.get("metadata", {}),
        )

    def _deserialize_node(self, data: Dict) -> Optional[BaseNode]:
        """Deserialize a node based on its class."""
        node_class_name = data.pop("_node_class", None)
        node_type = data.get("node_type")

        # Map class names to classes
        class_map = {
            "PartyNode": PartyNode,
            "PropertyNode": PropertyNode,
            "LeaseNode": LeaseNode,
            "EvidenceNode": EvidenceNode,
            "EventNode": EventNode,
            "IssueNode": IssueNode,
            "ClaimedAmountNode": ClaimedAmountNode,
        }

        # Map node types to classes
        type_map = {
            "party": PartyNode,
            "property": PropertyNode,
            "lease": LeaseNode,
            "evidence": EvidenceNode,
            "event": EventNode,
            "issue": IssueNode,
            "claimed_amount": ClaimedAmountNode,
        }

        # Try class name first, then type
        node_class = class_map.get(node_class_name)
        if not node_class and node_type:
            node_class = type_map.get(node_type)

        if not node_class:
            logger.warning(
                "unknown_node_type",
                class_name=node_class_name,
                node_type=node_type,
            )
            return None

        try:
            return node_class.model_validate(data)
        except Exception as e:
            logger.warning("node_deserialize_failed", error=str(e))
            return None
