"""Polymorphic KG serialization helpers extracted from JSONGraphStore.

These functions allow Postgres-backed and JSON-backed graph stores, plus the
audit tooling, to share the same polymorphic node round-trip logic.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import structlog

from kg_builder.models.edges import Edge
from kg_builder.models.graph import KnowledgeGraph
from kg_builder.models.nodes import (
    BaseNode,
    ClaimedAmountNode,
    EventNode,
    EvidenceNode,
    IssueNode,
    LeaseNode,
    PartyNode,
    PropertyNode,
)

logger = structlog.get_logger()

# Maps class names to node classes (for _node_class-tagged dicts)
_CLASS_MAP: dict[str, type[BaseNode]] = {
    "PartyNode": PartyNode,
    "PropertyNode": PropertyNode,
    "LeaseNode": LeaseNode,
    "EvidenceNode": EvidenceNode,
    "EventNode": EventNode,
    "IssueNode": IssueNode,
    "ClaimedAmountNode": ClaimedAmountNode,
}

# Maps node_type string values to node classes
_TYPE_MAP: dict[str, type[BaseNode]] = {
    "party": PartyNode,
    "property": PropertyNode,
    "lease": LeaseNode,
    "evidence": EvidenceNode,
    "event": EventNode,
    "issue": IssueNode,
    "claimed_amount": ClaimedAmountNode,
}


def serialize_node(node: BaseNode) -> dict[str, Any]:
    """Serialize a node with its type discriminator tag.

    Adds ``_node_class`` to the dict so that :func:`deserialize_node` can
    reconstruct the concrete subclass on the way back.

    Uses ``mode="json"`` so that date/datetime values are ISO strings
    rather than Python objects, making the result directly JSONB-safe.
    """
    data = node.model_dump(mode="json")
    data["_node_class"] = node.__class__.__name__
    return data


def deserialize_node(data: dict[str, Any]) -> Optional[BaseNode]:
    """Deserialize a node based on its ``_node_class`` tag or ``node_type`` value.

    The ``_node_class`` key is *popped* from the dict before validation so that
    it does not interfere with Pydantic field validation.
    """
    # Work on a copy so the caller's dict is not mutated
    data = dict(data)
    node_class_name = data.pop("_node_class", None)
    node_type = data.get("node_type")

    # Try class name first, then fall back to node_type string
    node_class = _CLASS_MAP.get(node_class_name)
    if not node_class and node_type:
        node_class = _TYPE_MAP.get(node_type)

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


def _json_safe(value: Any) -> Any:
    """Match JSONGraphStore's json.dump(default=str) behavior for JSONB."""
    return json.loads(json.dumps(value, default=str))


_DEFAULT_DOMAIN_ID = "housing.deposit.v1"
_DEFAULT_DOMAIN_VERSION = "v1"


def serialize_knowledge_graph(kg: KnowledgeGraph) -> dict[str, Any]:
    """Convert a KnowledgeGraph to a fully serializable dict.

    All nested values are JSON-safe (dates are ISO strings, enums are their
    string values) so the result can be written directly to JSONB columns.
    """
    return {
        "graph_id": kg.graph_id,
        "case_id": kg.case_id,
        "created_at": kg.created_at,
        "updated_at": kg.updated_at,
        "nodes": [serialize_node(n) for n in kg.nodes],
        "edges": [e.model_dump(mode="json") for e in kg.edges],
        "validation_errors": _json_safe(kg.validation_errors),
        "validation_warnings": _json_safe(kg.validation_warnings),
        "validation_info": _json_safe(kg.validation_info),
        "is_consistent": kg.is_consistent,
        "data_quality_tier": kg.data_quality_tier,
        # SHA-20 Phase 3 + Phase 5: domain + ontology routing.
        "domain_id": kg.domain_id,
        "domain_version": kg.domain_version,
        "domain_spec_hash": kg.domain_spec_hash,
        "ontology_id": kg.ontology_id,
        "ontology_hash": kg.ontology_hash,
        "metadata": _json_safe(kg.metadata),
    }


def deserialize_knowledge_graph(data: dict[str, Any]) -> KnowledgeGraph:
    """Reconstruct a KnowledgeGraph from a serialized dict.

    Back-compat: serialized graphs that pre-date SHA-20 (no domain_id /
    ontology_id) get the legacy defaults (``housing.deposit.v1``, ``v1``)
    so callers don't have to special-case missing fields.
    """
    nodes: list[BaseNode] = []
    for node_data in data.get("nodes", []):
        node = deserialize_node(node_data)
        if node:
            nodes.append(node)

    edges: list[Edge] = []
    for edge_data in data.get("edges", []):
        try:
            edge = Edge.model_validate(edge_data)
            edges.append(edge)
        except Exception as e:
            logger.warning("edge_deserialize_failed", error=str(e))

    metadata = data.get("metadata", {}) or {}
    # Backfill domain_id from metadata mirror if top-level missing.
    legacy_meta_domain = (
        metadata.get("domain_id") if isinstance(metadata, dict) else None
    )
    domain_id = (
        data.get("domain_id")
        or legacy_meta_domain
        or _DEFAULT_DOMAIN_ID
    )
    domain_version = data.get("domain_version") or _DEFAULT_DOMAIN_VERSION

    return KnowledgeGraph(
        graph_id=data.get("graph_id", ""),
        case_id=data.get("case_id", ""),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        nodes=nodes,
        edges=edges,
        validation_errors=data.get("validation_errors", []),
        validation_warnings=data.get("validation_warnings", []),
        validation_info=data.get("validation_info", []),
        is_consistent=data.get("is_consistent", True),
        data_quality_tier=data.get("data_quality_tier", "minimal"),
        domain_id=domain_id,
        domain_version=domain_version,
        domain_spec_hash=data.get("domain_spec_hash"),
        ontology_id=data.get("ontology_id"),
        ontology_hash=data.get("ontology_hash"),
        metadata=metadata,
    )
