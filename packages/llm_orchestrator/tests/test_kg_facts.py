"""Tests for typed KGFacts extraction (SHA-33)."""

from datetime import date

import pytest

from llm_orchestrator.models.prediction_v2 import IssueType
from llm_orchestrator.pipeline.kg_facts import KGFacts, derive_kg_facts


def test_derive_kg_facts_with_none_kg_returns_empty():
    facts = derive_kg_facts(None, IssueType.DEPOSIT_PROTECTION)
    assert facts.is_empty()
    assert facts.deposit_protection_status == "unknown"
    assert facts.prescribed_information_status == "unknown"
    assert facts.check_in_inventory_baseline == "unknown"


def test_kg_facts_is_empty_with_all_unknown():
    assert KGFacts().is_empty()


def test_kg_facts_not_empty_when_one_field_set():
    assert not KGFacts(deposit_protection_status="protected_late").is_empty()


def test_derive_kg_facts_late_protection():
    """LeaseNode with protection_date 90 days after start_date → protected_late."""
    from kg_builder.models.nodes import LeaseNode, NodeType
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_late")
    kg.add_node(
        LeaseNode(
            node_id="lease_main",
            start_date=date(2023, 1, 1),
            protection_date=date(2023, 4, 1),  # 90 days late
            deposit_protected=True,
            deposit_scheme="DPS",
        )
    )
    facts = derive_kg_facts(kg, IssueType.DEPOSIT_PROTECTION)
    assert facts.deposit_protection_status == "protected_late"
    assert facts.deposit_late_by_days == 90
    assert facts.deposit_scheme == "DPS"


def test_derive_kg_facts_on_time_protection():
    from kg_builder.models.nodes import LeaseNode
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_ontime")
    kg.add_node(
        LeaseNode(
            node_id="lease_main",
            start_date=date(2023, 1, 1),
            protection_date=date(2023, 1, 14),  # 13 days, on time
            deposit_protected=True,
        )
    )
    facts = derive_kg_facts(kg, IssueType.DEPOSIT_PROTECTION)
    assert facts.deposit_protection_status == "protected_on_time"
    assert facts.deposit_late_by_days is None


def test_derive_kg_facts_not_protected():
    from kg_builder.models.nodes import LeaseNode
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_unprotected")
    kg.add_node(LeaseNode(node_id="lease_main", deposit_protected=False))
    facts = derive_kg_facts(kg, IssueType.DEPOSIT_PROTECTION)
    assert facts.deposit_protection_status == "not_protected"


def test_derive_kg_facts_prescribed_info_late():
    from kg_builder.models.nodes import LeaseNode
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_prescribed")
    kg.add_node(
        LeaseNode(
            node_id="lease_main",
            start_date=date(2023, 1, 1),
            prescribed_info_provided=True,
            prescribed_info_date=date(2023, 3, 1),  # 59 days, late
        )
    )
    facts = derive_kg_facts(kg, IssueType.DEPOSIT_PROTECTION)
    assert facts.prescribed_information_status == "provided_late"
    assert facts.prescribed_late_by_days == 59


def test_derive_kg_facts_inventory_absent_for_inventory_issue():
    """Cleaning/damage/wear-and-tear issues set inventory baseline to absent
    when no inventory_checkin evidence node is present."""
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_no_inventory")
    facts = derive_kg_facts(kg, IssueType.CLEANING)
    assert facts.check_in_inventory_baseline == "absent"


def test_derive_kg_facts_inventory_unknown_for_non_inventory_issue():
    """deposit_protection issues don't trigger inventory derivation."""
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_dp")
    facts = derive_kg_facts(kg, IssueType.DEPOSIT_PROTECTION)
    assert facts.check_in_inventory_baseline == "unknown"


def test_derive_kg_facts_inventory_present_when_checkin_evidence_exists():
    from kg_builder.models.nodes import EvidenceNode
    from kg_builder.models.graph import KnowledgeGraph

    kg = KnowledgeGraph(case_id="test_with_inventory")
    kg.add_node(
        EvidenceNode(
            node_id="ev_1",
            evidence_type="inventory_checkin",
            description="check-in inventory",
        )
    )
    facts = derive_kg_facts(kg, IssueType.DAMAGE)
    assert facts.check_in_inventory_baseline == "present"
