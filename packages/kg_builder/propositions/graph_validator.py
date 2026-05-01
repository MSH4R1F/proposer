"""Graph-level validator for proposition edges (SHA-36 Task 7).

Pure function (no LLM, no I/O). Applies semantic constraints AFTER the
edge extractor's per-item filtering, treating the full graph as the
input.

Phase 1 rules (intentionally strict — relax later if rejection rates
are too high downstream):

  * All edges must have ``document_id == expected_document_id``;
    cross-document edges are rejected.
  * ``applies_rule_to_fact``: ``from`` must be type ``rule``,
    ``to`` must be type ``fact``.
  * ``cites``: ``to`` must be type ``authority`` (HARD reject in Phase 1
    per the SHA-36 spec).
  * ``temporal_before``: both endpoints must be type ``fact`` or
    ``outcome`` (rule / authority don't have a temporal position).

Endpoints are normally pre-filtered by the extractor against the input
proposition set, but this validator can be called standalone, so a
defensive ``unknown_endpoint`` rejection is emitted if a referenced id
is missing from the proposition list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence
from uuid import UUID

from kg_builder.propositions.models import (
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    PropositionType,
)


@dataclass(frozen=True)
class GraphValidationRejection:
    """One rejected edge, with a reason code for telemetry.

    Reason codes are a closed enum (string literals) so callers can
    aggregate counts without introspecting message text.
    """

    edge_id: UUID
    reason: str  # one of:
                 #   "cross_document"
                 #   "unknown_endpoint"
                 #   "applies_rule_to_fact_endpoint_types"
                 #   "cites_target_not_authority"
                 #   "temporal_before_endpoint_types"


def validate_graph(
    edges: Sequence[PropositionEdge],
    propositions: Sequence[Proposition],
    *,
    expected_document_id: UUID,
) -> tuple[list[PropositionEdge], list[GraphValidationRejection]]:
    """Apply graph-level semantic constraints.

    Returns ``(accepted_edges, rejections)``. Order of accepted edges
    matches the input order.
    """
    type_by_id: Mapping[UUID, PropositionType] = {
        p.proposition_id: p.proposition_type for p in propositions
    }
    accepted: list[PropositionEdge] = []
    rejections: list[GraphValidationRejection] = []

    for edge in edges:
        # Cross-document
        if edge.document_id != expected_document_id:
            rejections.append(GraphValidationRejection(
                edge_id=edge.edge_id, reason="cross_document",
            ))
            continue

        from_type = type_by_id.get(edge.from_proposition_id)
        to_type = type_by_id.get(edge.to_proposition_id)

        # Defensive: endpoints unknown to the proposition list. The
        # extractor pre-filters these, but a standalone caller might not.
        if from_type is None or to_type is None:
            rejections.append(GraphValidationRejection(
                edge_id=edge.edge_id, reason="unknown_endpoint",
            ))
            continue

        if edge.edge_type == PropositionEdgeType.applies_rule_to_fact:
            if (
                from_type != PropositionType.rule
                or to_type != PropositionType.fact
            ):
                rejections.append(GraphValidationRejection(
                    edge_id=edge.edge_id,
                    reason="applies_rule_to_fact_endpoint_types",
                ))
                continue

        elif edge.edge_type == PropositionEdgeType.cites:
            # Spec calls this a soft constraint, but Phase 1 hard-rejects
            # to keep the graph clean. Relax to a warning if rejection
            # rate is unworkable in production.
            if to_type != PropositionType.authority:
                rejections.append(GraphValidationRejection(
                    edge_id=edge.edge_id,
                    reason="cites_target_not_authority",
                ))
                continue

        elif edge.edge_type == PropositionEdgeType.temporal_before:
            allowed = {PropositionType.fact, PropositionType.outcome}
            if from_type not in allowed or to_type not in allowed:
                rejections.append(GraphValidationRejection(
                    edge_id=edge.edge_id,
                    reason="temporal_before_endpoint_types",
                ))
                continue

        # supports / contradicts have no endpoint-type constraint at this
        # stage (any pair within the same document is allowed).
        accepted.append(edge)

    return accepted, rejections


__all__ = [
    "GraphValidationRejection",
    "validate_graph",
]
