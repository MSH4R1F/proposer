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
from .graph_serialization import (
    deserialize_knowledge_graph as _deserialize_graph_helper,
    deserialize_node as _deserialize_node_helper,
    serialize_knowledge_graph as _serialize_graph_helper,
    serialize_node as _serialize_node_helper,
)

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
        return _serialize_graph_helper(kg)

    def _serialize_node(self, node: BaseNode) -> Dict:
        """Serialize a node with its type."""
        return _serialize_node_helper(node)

    def _deserialize_graph(self, data: Dict) -> KnowledgeGraph:
        """Reconstruct KnowledgeGraph from dict."""
        return _deserialize_graph_helper(data)

    def _deserialize_node(self, data: Dict) -> Optional[BaseNode]:
        """Deserialize a node based on its class."""
        return _deserialize_node_helper(data)
