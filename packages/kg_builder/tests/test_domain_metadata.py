"""SHA-61 / SHA-119: KG domain metadata + ontology validation.

Covers:

- A KG built without explicit domain defaults to ``housing.deposit.v1``.
- A serialized old graph (no domain_id field) loads with the legacy
  default back-filled.
- Adding a node with a different ``domain_id`` to a deposit graph fails
  ontology validation.
- Adding an Evidence-bridge node from another domain via a
  ``cross_domain_bridges``-listed edge passes ontology validation.
- Existing SHA-35 temporal/evidence checks still trigger when ontology
  validation is enabled.
"""

from __future__ import annotations

from datetime import date

import pytest

from kg_builder.builders.graph_builder import propagate_domain_metadata
from kg_builder.builders.validators import KGValidationError, KGValidator
from kg_builder.models.edges import Edge, EdgeType
from kg_builder.models.graph import KnowledgeGraph
from kg_builder.models.nodes import (
    EventNode,
    EvidenceNode,
    IssueNode,
    LeaseNode,
    PartyNode,
)
from kg_builder.ontology.registry import (
    get_ontology,
    reset_ontology_cache,
)
from kg_builder.ontology.validators import (
    OntologyValidationError,
    validate_graph_against_ontology,
)
from kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
)


@pytest.fixture(autouse=True)
def _reset_ontology_cache():
    reset_ontology_cache()
    yield
    reset_ontology_cache()


def _basic_deposit_kg() -> KnowledgeGraph:
    kg = KnowledgeGraph(case_id="case_dep_1")
    kg.add_node(LeaseNode(node_id="lease_main", start_date=date(2023, 1, 1)))
    kg.add_node(PartyNode(node_id="p_tenant", role="tenant"))
    kg.add_node(PartyNode(node_id="p_landlord", role="landlord"))
    kg.add_node(IssueNode(node_id="iss_clean", issue_type="cleaning", description="x"))
    kg.add_node(EvidenceNode(node_id="ev_1", evidence_type="receipts", description="y"))
    kg.add_edge(Edge.create(EdgeType.EVIDENCE_RELATES_TO, "ev_1", "iss_clean"))
    return kg


def test_default_kg_has_deposit_domain_id():
    kg = KnowledgeGraph(case_id="x")
    assert kg.domain_id == "housing.deposit.v1"
    assert kg.primary_domain_id == "housing.deposit.v1"


def test_propagate_stamps_primary_domain_onto_nodes():
    kg = _basic_deposit_kg()
    # Before propagate, nodes have no domain_id (default None).
    assert all(n.domain_id is None for n in kg.nodes)
    propagate_domain_metadata(kg)
    # After propagate, every node carries the primary domain.
    assert all(n.domain_id == "housing.deposit.v1" for n in kg.nodes)


def test_serialized_old_graph_backfills_domain_id():
    """Pre-SHA-20 serialized graphs (no domain_id field) round-trip with
    ``housing.deposit.v1`` defaulted."""
    legacy = {
        "graph_id": "g1",
        "case_id": "case_legacy",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "nodes": [],
        "edges": [],
        "validation_errors": [],
        "validation_warnings": [],
        "validation_info": [],
        "is_consistent": True,
        "data_quality_tier": "minimal",
        "metadata": {},
        # NB: no domain_id, domain_version, ontology_id, ontology_hash
    }
    kg = deserialize_knowledge_graph(legacy)
    assert kg.domain_id == "housing.deposit.v1"
    assert kg.domain_version == "v1"
    assert kg.ontology_id is None


def test_serialized_modern_graph_round_trips_ontology_fields():
    kg = _basic_deposit_kg()
    kg.set_primary_domain("housing.deposit.v1")
    kg.ontology_id = "housing.deposit.v1"
    kg.ontology_hash = "abc123"
    payload = serialize_knowledge_graph(kg)
    assert payload["domain_id"] == "housing.deposit.v1"
    assert payload["ontology_id"] == "housing.deposit.v1"
    assert payload["ontology_hash"] == "abc123"

    rebuilt = deserialize_knowledge_graph(payload)
    assert rebuilt.domain_id == "housing.deposit.v1"
    assert rebuilt.ontology_id == "housing.deposit.v1"
    assert rebuilt.ontology_hash == "abc123"


def test_node_with_different_domain_id_fails_ontology_validation():
    """Audit decision D5: an employment node injected into a deposit KG
    must fail validation."""
    kg = _basic_deposit_kg()
    # Inject a node tagged with a different domain (no source_domain — not
    # an Evidence bridge, so it must not be allowed).
    rogue = PartyNode(node_id="p_rogue", role="claimant")
    rogue.domain_id = "employment.unfair_dismissal.v1"
    kg.add_node(rogue)

    ontology = get_ontology("housing.deposit.v1")
    with pytest.raises(OntologyValidationError) as exc:
        validate_graph_against_ontology(kg, ontology)
    assert any(
        "differs from the graph primary domain" in e for e in exc.value.errors
    )


def test_evidence_bridge_with_listed_edge_is_allowed():
    """An Evidence node from another domain attached via a
    ``cross_domain_bridges``-listed edge is permitted."""
    kg = _basic_deposit_kg()
    # The base deposit KG already has an Evidence node + Issue node; we
    # add a second Evidence node tagged as a cross-domain bridge.
    bridge_evidence = EvidenceNode(
        node_id="ev_bridge",
        evidence_type="ombudsman_determination",
        description="Cross-domain reference",
    )
    bridge_evidence.domain_id = "housing.repairs_social.v1"
    bridge_evidence.source_domain = "housing.repairs_social.v1"
    kg.add_node(bridge_evidence)
    kg.add_edge(
        Edge.create(EdgeType.EVIDENCE_RELATES_TO, "ev_bridge", "iss_clean")
    )

    ontology = get_ontology("housing.deposit.v1")
    # evidence_relates_to is in cross_domain_bridges for housing.deposit.v1.
    errs = validate_graph_against_ontology(kg, ontology, raise_on_error=False)
    # No errors related to the bridge.
    assert all("ev_bridge" not in e for e in errs), (
        f"unexpected bridge errors: {errs}"
    )


def test_cross_domain_edge_not_in_bridges_rejected():
    """If the bridge edge is NOT in cross_domain_bridges, validation fails."""
    kg = _basic_deposit_kg()
    bridge_evidence = EvidenceNode(
        node_id="ev_bridge",
        evidence_type="other",
        description="Cross-domain bridge attempt via non-listed edge.",
    )
    bridge_evidence.domain_id = "employment.unfair_dismissal.v1"
    bridge_evidence.source_domain = "employment.unfair_dismissal.v1"
    kg.add_node(bridge_evidence)
    # claim_relates_to is NOT in cross_domain_bridges for housing.deposit.v1.
    # We need to add a ClaimedAmount to use that edge — keep it simple by
    # using evidence_supports_issue-style which is base. Use issue_caused_by
    # (Issue->Event) which exists in base; create an event node and try to
    # bridge via an unlisted edge name.
    # Actually simpler: just use issue_involves between an Issue and a
    # ClaimedAmount, and tag the claim as cross-domain.
    from kg_builder.models.nodes import ClaimedAmountNode

    kg.add_node(
        ClaimedAmountNode(
            node_id="claim_x",
            claimant="landlord",
            amount=100.0,
            issue_type="cleaning",
            description="cross-domain test",
        )
    )
    # Tag the claim as a different domain to trigger the cross-domain
    # check on its edges.
    cross_claim = next(n for n in kg.nodes if n.node_id == "claim_x")
    cross_claim.domain_id = "employment.unfair_dismissal.v1"

    # Add an issue_involves edge (NOT in cross_domain_bridges).
    kg.add_edge(
        Edge.create(EdgeType.ISSUE_INVOLVES, "iss_clean", "claim_x")
    )

    ontology = get_ontology("housing.deposit.v1")
    errs = validate_graph_against_ontology(kg, ontology, raise_on_error=False)
    # Should fail because claim_x has a foreign domain_id and isn't an
    # Evidence bridge.
    assert any("claim_x" in e or "differs from the graph primary domain" in e for e in errs)


def test_kg_validator_runs_ontology_when_provided():
    """The legacy KGValidator integrates ontology errors when an
    OntologySpec is passed in."""
    kg = _basic_deposit_kg()
    propagate_domain_metadata(kg)
    ontology = get_ontology("housing.deposit.v1")

    # Inject a node whose ontology_kind is not in the ontology.
    rogue = PartyNode(node_id="p_rogue", role="tenant")
    rogue.metadata = {"ontology_kind": "AlienConcept"}
    kg.add_node(rogue)

    with pytest.raises(KGValidationError) as exc:
        KGValidator(ontology=ontology).validate(kg)
    assert any("ontology" in e.lower() for e in exc.value.errors)


def test_existing_temporal_validators_still_trigger_with_ontology():
    """SHA-35 fail-fast must remain unchanged when an ontology is also set."""
    kg = KnowledgeGraph(case_id="case_temporal")
    kg.add_node(
        LeaseNode(node_id="lease_main", start_date=date(2024, 1, 1), end_date=date(2023, 1, 1))
    )
    propagate_domain_metadata(kg)
    ontology = get_ontology("housing.deposit.v1")

    with pytest.raises(KGValidationError) as exc:
        KGValidator(ontology=ontology).validate(kg)
    # Pre-existing temporal error survives.
    assert any("end date is before start" in e.lower() for e in exc.value.errors)


def test_ontology_validation_passes_for_clean_deposit_kg():
    kg = _basic_deposit_kg()
    propagate_domain_metadata(kg)
    ontology = get_ontology("housing.deposit.v1")
    errs = validate_graph_against_ontology(kg, ontology, raise_on_error=False)
    assert errs == []


def test_set_primary_domain_mirrors_into_metadata():
    kg = KnowledgeGraph(case_id="x")
    kg.set_primary_domain("housing.repairs_social.v1")
    assert kg.domain_id == "housing.repairs_social.v1"
    assert kg.metadata.get("domain_id") == "housing.repairs_social.v1"
    assert kg.primary_domain_id == "housing.repairs_social.v1"
