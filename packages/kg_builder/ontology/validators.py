"""Ontology-aware validation for KnowledgeGraphs.

This validator layer is *additive* on top of the existing
:class:`packages.kg_builder.builders.validators.KGValidator` — it does not
replace temporal / evidence-chain checks. Callers that want both should
run :func:`validate_graph_against_ontology` after the KGValidator has
populated ``kg.is_consistent``.

Rules enforced here (SHA-61):
- A graph has exactly one ``primary_domain_id`` (taken from the KG itself).
- Every node's ``domain_id`` (when set) equals the graph's domain, OR the
  node is an ``Evidence`` bridge that explicitly carries ``source_domain``
  and is referenced by an edge whose name is in
  ``ontology.cross_domain_bridges``.
- Every edge's source/target node-kind tuple matches one of the
  ontology's :class:`AllowedEdgeKind` definitions.
- Cross-domain edges (``edge.source_domain`` set, or its endpoints span
  two domains) MUST be in ``ontology.cross_domain_bridges``.
- If a node carries ``source_ref``, it must include ``source_kind`` and
  ``forum`` (from its ``provenance`` dict) consistent with the domain's
  :class:`ForumProfile` from ``domain_core``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from kg_builder.ontology.spec import OntologySpec


# Map our internal NodeType (lowercase enum value) -> ontology PascalCase
# kind name. Domains may add domain-specific kinds beyond these.
_NODE_TYPE_TO_KIND = {
    "party": "Party",
    "property": "Property",
    "lease": "Lease",
    "evidence": "Evidence",
    "event": "Event",
    "issue": "Issue",
    "claimed_amount": "ClaimedAmount",
}


class OntologyValidationError(ValueError):
    """Raised when a KG violates its ontology contract.

    Carries the list of error strings for fine-grained logging.
    """

    def __init__(self, errors: List[str], graph_id: Optional[str] = None):
        self.errors = list(errors)
        self.graph_id = graph_id
        message = (
            f"KG {graph_id!r} failed ontology validation: "
            + "; ".join(errors)
        )
        super().__init__(message)


def _node_type_str(node: Any) -> str:
    nt = getattr(node, "node_type", None)
    if nt is None:
        return ""
    return getattr(nt, "value", str(nt))


def _node_ontology_kind(node: Any, ontology: OntologySpec) -> Optional[str]:
    """Resolve the ontology node-kind name for a KG node.

    Prefers an explicit ``ontology_kind`` in node.metadata if present.
    Otherwise falls back to ``_NODE_TYPE_TO_KIND[node.node_type.value]``.
    Returns None if the resolved kind is not declared in the ontology.
    """
    meta = getattr(node, "metadata", {}) or {}
    explicit = meta.get("ontology_kind") if isinstance(meta, dict) else None
    if isinstance(explicit, str) and explicit:
        if ontology.node_kind(explicit) is not None:
            return explicit
        # Explicit-but-unknown kind is a hard error caught later.
        return explicit

    base_kind = _NODE_TYPE_TO_KIND.get(_node_type_str(node))
    if base_kind is None:
        return None
    if ontology.node_kind(base_kind) is None:
        return None
    return base_kind


def _validate_nodes(
    kg: Any,
    ontology: OntologySpec,
    primary_domain_id: str,
) -> List[str]:
    errors: List[str] = []
    for node in getattr(kg, "nodes", []):
        kind = _node_ontology_kind(node, ontology)
        if kind is None:
            errors.append(
                f"Node {node.node_id!r} has node_type "
                f"{_node_type_str(node)!r} which is not declared in ontology "
                f"{ontology.id!r}"
            )
            continue
        if ontology.node_kind(kind) is None:
            errors.append(
                f"Node {node.node_id!r} declares ontology_kind {kind!r} "
                f"which is not in ontology {ontology.id!r}"
            )
            continue

        node_domain = getattr(node, "domain_id", None)
        if node_domain is not None and node_domain != primary_domain_id:
            # Allow Evidence nodes carrying source_domain as cross-domain
            # bridges; the edge-side check enforces the bridge whitelist.
            source_domain = getattr(node, "source_domain", None)
            is_evidence = _node_type_str(node) == "evidence"
            if not (is_evidence and source_domain):
                errors.append(
                    f"Node {node.node_id!r} has domain_id {node_domain!r} "
                    f"that differs from the graph primary domain "
                    f"{primary_domain_id!r}; only Evidence bridge nodes "
                    "with explicit source_domain are allowed"
                )
    return errors


def _validate_edges(
    kg: Any,
    ontology: OntologySpec,
    primary_domain_id: str,
) -> List[str]:
    errors: List[str] = []
    nodes_by_id: Dict[str, Any] = {n.node_id: n for n in getattr(kg, "nodes", [])}

    bridges: Set[str] = set(ontology.cross_domain_bridges)

    # Index allowed edge kinds by (from_kind, to_kind, name) for lookup.
    edge_index: Dict[Tuple[str, str, str], Any] = {}
    edge_by_name: Dict[str, List[Any]] = {}
    for ek in ontology.edge_kinds:
        edge_index[(ek.from_kind, ek.to_kind, ek.name)] = ek
        edge_by_name.setdefault(ek.name, []).append(ek)

    for edge in getattr(kg, "edges", []):
        edge_name = getattr(edge, "edge_type", None)
        edge_name = getattr(edge_name, "value", edge_name)
        if not isinstance(edge_name, str):
            errors.append(
                f"Edge {edge.edge_id!r} has unparseable edge_type"
            )
            continue

        src = nodes_by_id.get(edge.source_node_id)
        tgt = nodes_by_id.get(edge.target_node_id)
        if src is None or tgt is None:
            # KGValidator already reports missing endpoints; skip ontology
            # check rather than double-report.
            continue

        src_kind = _node_ontology_kind(src, ontology)
        tgt_kind = _node_ontology_kind(tgt, ontology)
        if src_kind is None or tgt_kind is None:
            # Already reported by _validate_nodes
            continue

        # Edge name must exist in ontology
        if edge_name not in edge_by_name:
            errors.append(
                f"Edge {edge.edge_id!r} kind {edge_name!r} is not declared "
                f"in ontology {ontology.id!r}"
            )
            continue

        # Some edge name with matching from/to must exist
        match = edge_index.get((src_kind, tgt_kind, edge_name))
        if match is None:
            allowed_for_name = [
                (ek.from_kind, ek.to_kind) for ek in edge_by_name[edge_name]
            ]
            errors.append(
                f"Edge {edge.edge_id!r} ({edge_name!r}) connects "
                f"{src_kind!r} -> {tgt_kind!r}; ontology declares "
                f"this edge between {allowed_for_name}"
            )
            continue

        # Cross-domain edge gating
        src_domain = getattr(src, "domain_id", None) or primary_domain_id
        tgt_domain = getattr(tgt, "domain_id", None) or primary_domain_id
        edge_source_domain = getattr(edge, "source_domain", None)
        is_cross_domain = (
            (src_domain != primary_domain_id)
            or (tgt_domain != primary_domain_id)
            or (edge_source_domain not in (None, primary_domain_id))
        )
        if is_cross_domain and edge_name not in bridges:
            errors.append(
                f"Edge {edge.edge_id!r} ({edge_name!r}) bridges domains "
                f"({src_domain!r} -> {tgt_domain!r}) but is not in "
                f"ontology.cross_domain_bridges={sorted(bridges)}"
            )

    return errors


def _validate_node_provenance_against_forum(
    kg: Any,
    primary_domain_id: str,
) -> List[str]:
    """Optional check: if a node has ``source_ref``, its provenance must
    declare ``source_kind`` and ``forum`` consistent with the domain's
    ForumProfile.

    Imports ``domain_core`` lazily so the ontology layer remains usable in
    test contexts that don't load the full domain registry.
    """
    errors: List[str] = []
    nodes_with_ref = [
        n for n in getattr(kg, "nodes", [])
        if getattr(n, "source_ref", None)
    ]
    if not nodes_with_ref:
        return errors

    try:
        from domain_core.registry import get_domain_spec
    except Exception:
        # domain_core unavailable — skip provenance check.
        return errors

    try:
        spec = get_domain_spec(primary_domain_id)
    except Exception:
        return errors

    forum_profiles = {p.forum.value: p for p in spec.forum_profiles}
    valid_forums = set(forum_profiles.keys())

    for node in nodes_with_ref:
        prov = getattr(node, "provenance", {}) or {}
        if not isinstance(prov, dict):
            errors.append(
                f"Node {node.node_id!r} has source_ref but provenance is "
                f"not a dict (got {type(prov).__name__})"
            )
            continue
        forum = prov.get("forum") or getattr(node, "forum", None)
        kind = prov.get("source_kind")
        if not forum:
            errors.append(
                f"Node {node.node_id!r} has source_ref but no forum in "
                "provenance/node.forum"
            )
            continue
        if not kind:
            errors.append(
                f"Node {node.node_id!r} has source_ref but no source_kind "
                "in provenance"
            )
            continue
        if forum not in valid_forums:
            errors.append(
                f"Node {node.node_id!r} cites forum {forum!r} which is not "
                f"a forum of domain {primary_domain_id!r} "
                f"(valid: {sorted(valid_forums)})"
            )
            continue
        profile = forum_profiles[forum]
        allowed_kinds = {sk.value for sk in profile.source_kinds}
        if kind not in allowed_kinds:
            errors.append(
                f"Node {node.node_id!r} has source_kind {kind!r}; "
                f"forum {forum!r} only permits {sorted(allowed_kinds)}"
            )

    return errors


def validate_graph_against_ontology(
    kg: Any,
    ontology: OntologySpec,
    *,
    raise_on_error: bool = True,
) -> List[str]:
    """Validate ``kg`` against ``ontology``.

    Args:
        kg: a :class:`packages.kg_builder.models.graph.KnowledgeGraph`.
        ontology: a resolved :class:`OntologySpec`.
        raise_on_error: when True, raise :class:`OntologyValidationError`
            if any errors are found. When False, return the list and let
            the caller decide.

    Returns:
        List of error strings (possibly empty).

    Raises:
        OntologyValidationError: when ``raise_on_error`` is True and
            errors were found.
    """
    primary_domain_id = (
        getattr(kg, "primary_domain_id", None)
        or getattr(kg, "domain_id", None)
        or "housing.deposit.v1"
    )

    errors: List[str] = []
    errors.extend(_validate_nodes(kg, ontology, primary_domain_id))
    errors.extend(_validate_edges(kg, ontology, primary_domain_id))
    errors.extend(
        _validate_node_provenance_against_forum(kg, primary_domain_id)
    )

    if errors and raise_on_error:
        raise OntologyValidationError(errors, graph_id=getattr(kg, "graph_id", None))
    return errors
