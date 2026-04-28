"""Tests for the typed KG fact card renderer (SHA-33 Task 3a)."""

from llm_orchestrator.pipeline.issue_predictor import IssuePredictor
from llm_orchestrator.pipeline.kg_facts import KGFacts


def test_fact_card_empty_when_kg_facts_is_none():
    assert IssuePredictor._format_kg_fact_card(None) == ""


def test_fact_card_empty_when_all_unknown():
    assert IssuePredictor._format_kg_fact_card(KGFacts()) == ""


def test_fact_card_renders_late_protection_with_days():
    facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_late_by_days=90,
        deposit_scheme="DPS",
    )
    card = IssuePredictor._format_kg_fact_card(facts)
    assert "KEY KG FACTS (typed):" in card
    assert "deposit_protection_status: protected_late" in card
    assert "scheme: DPS" in card
    assert "late by 90 days" in card


def test_fact_card_renders_not_protected():
    facts = KGFacts(deposit_protection_status="not_protected")
    card = IssuePredictor._format_kg_fact_card(facts)
    assert "deposit_protection_status: not_protected" in card
    assert "prescribed_information_status" not in card  # only known facts shown


def test_fact_card_renders_prescribed_info_late():
    facts = KGFacts(
        prescribed_information_status="provided_late",
        prescribed_late_by_days=45,
    )
    card = IssuePredictor._format_kg_fact_card(facts)
    assert "prescribed_information_status: provided_late" in card
    assert "late by 45 days" in card


def test_fact_card_renders_inventory_absent():
    facts = KGFacts(check_in_inventory_baseline="absent")
    card = IssuePredictor._format_kg_fact_card(facts)
    assert "check_in_inventory_baseline: absent" in card


def test_fact_card_does_not_promote_free_text():
    """Critical: only typed enums in the card, no free-text descriptions
    from KG nodes (which would carry source='user_input' strings)."""
    facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_scheme="DPS",
        deposit_late_by_days=60,
    )
    card = IssuePredictor._format_kg_fact_card(facts)
    # Must NOT contain anything that looks like a node description or claim text
    assert "Tenant claims" not in card
    assert "Landlord claims" not in card
    assert "description" not in card.lower()


def test_fact_card_combines_multiple_facts():
    facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_late_by_days=60,
        prescribed_information_status="not_provided",
        check_in_inventory_baseline="absent",
    )
    card = IssuePredictor._format_kg_fact_card(facts)
    assert card.count("\n- ") == 3  # three facts
    assert "deposit_protection_status: protected_late" in card
    assert "prescribed_information_status: not_provided" in card
    assert "check_in_inventory_baseline: absent" in card
