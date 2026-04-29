import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.kg_repo import KnowledgeGraphRepo
from packages.kg_builder.models.graph import KnowledgeGraph
from packages.kg_builder.models.nodes import (
    PartyNode, PropertyNode, LeaseNode, EvidenceNode, EventNode,
    IssueNode, ClaimedAmountNode,
)
from packages.kg_builder.models.edges import Edge, EdgeType


def _make_kg(case_id: str = "case-1") -> KnowledgeGraph:
    # graph_id is unique per case so the knowledge_graphs.graph_id UNIQUE constraint
    # is not violated when two graphs share the same node IDs across different cases.
    kg = KnowledgeGraph(case_id=case_id, graph_id=f"g-{case_id}",
                        created_at="2026-01-01T00:00:00")
    party = PartyNode(node_id="party_tenant", role="tenant",
                      confidence=1.0, source="user_input")
    prop = PropertyNode(node_id="property_main",
                        address="1 X St", postcode="X1 1XX",
                        confidence=1.0, source="user_input")
    lease = LeaseNode(node_id="lease_main", confidence=1.0, source="user_input")
    ev = EvidenceNode(node_id="evidence_1", evidence_type="receipts",
                      description="receipt", confidence=1.0, source="user_input")
    event = EventNode(node_id="event_1", event_type="checkout",
                      event_date="2025-12-01", description="moved out",
                      actors=[], confidence=1.0, source="user_input")
    issue = IssueNode(node_id="issue_cleaning", issue_type="cleaning",
                      description="dirty", disputed=True, severity="high",
                      confidence=1.0, source="user_input")
    claim = ClaimedAmountNode(node_id="claim_1", claimant="landlord",
                              amount=420.0, issue_type="cleaning",
                              description="cleaning cost",
                              confidence=1.0, source="user_input")
    # Deliberately not sorted by node_id: the repo must preserve JSON insertion order.
    for n in [party, prop, lease, ev, event, issue, claim]:
        kg.add_node(n)
    kg.add_edge(Edge(edge_id="e2", edge_type=EdgeType.ISSUE_INVOLVES,
                     source_node_id="issue_cleaning", target_node_id="claim_1",
                     confidence=1.0, source="user_input", description="x"))
    kg.add_edge(Edge(edge_id="e1", edge_type=EdgeType.PARTY_OWNS,
                     source_node_id="party_tenant", target_node_id="property_main",
                     confidence=1.0, source="user_input", description="x"))
    return kg


@pytest.mark.asyncio
async def test_kg_roundtrip_all_node_types(db_session: AsyncSession) -> None:
    repo = KnowledgeGraphRepo(db_session)
    kg = _make_kg()
    await repo.save(kg)
    await db_session.commit()
    loaded = await repo.get(kg.case_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == kg.model_dump(mode="json")


@pytest.mark.asyncio
async def test_two_graphs_with_same_node_ids(db_session: AsyncSession) -> None:
    """Composite (case_id, node_id) lets identical IDs coexist across cases."""
    repo = KnowledgeGraphRepo(db_session)
    a = _make_kg(case_id="case-A")
    b = _make_kg(case_id="case-B")
    await repo.save(a)
    await repo.save(b)
    await db_session.commit()
    la, lb = await repo.get("case-A"), await repo.get("case-B")
    assert la is not None and lb is not None
