"""Tests for the typed KG fact card renderer (SHA-33 Task 3a)."""

from types import SimpleNamespace

import pytest

from llm_orchestrator.pipeline.issue_predictor import IssuePredictor
from llm_orchestrator.pipeline.kg_facts import KGFacts


class _DummyLLM:
    """Minimal stand-in LLM client. No real generate is called by these tests."""

    async def generate(self, messages, system_prompt, max_tokens, temperature):
        raise AssertionError("LLM.generate must not be invoked in these tests")


def _make_predictor() -> IssuePredictor:
    return IssuePredictor(_DummyLLM())


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


# ---------------------------------------------------------------------------
# Stream C PR 4 Task 4.4: pack-routed factor card rendering
# ---------------------------------------------------------------------------


def test_predictor_uses_pack_renderer_when_flag_set(monkeypatch):
    """STREAM_C_PR4=1 routes through the deposit pack; output matches legacy."""
    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(domain_id="housing.deposit.v1")
    facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_scheme="DPS",
        deposit_late_by_days=90,
    )
    card, meta = pred._render_factor_card_via_pack(pred._case_file, facts)
    legacy = pred._format_kg_fact_card(facts)
    assert card == legacy
    assert meta["kg_used_for_prediction"] is True


def test_predictor_uses_legacy_when_flag_unset(monkeypatch):
    """STREAM_C_PR4=0 returns the legacy _format_kg_fact_card output."""
    monkeypatch.setenv("STREAM_C_PR4", "0")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(domain_id="housing.deposit.v1")
    facts = KGFacts(deposit_protection_status="protected_late")
    card, meta = pred._render_factor_card_via_pack(pred._case_file, facts)
    legacy = pred._format_kg_fact_card(facts)
    assert card == legacy


def test_predictor_returns_empty_card_when_pack_unknown(monkeypatch):
    """Unknown domain id -> empty card, structured fallback metadata, no crash."""
    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(domain_id="unknown.domain.v99")
    facts = KGFacts(deposit_protection_status="protected_late")
    card, meta = pred._render_factor_card_via_pack(pred._case_file, facts)
    assert card == ""
    assert meta["kg_used_for_prediction"] is False
    assert meta["kg_fallback_mode"] == "rag_only"
    assert meta["kg_gate_failure_reasons"]


def test_predictor_returns_empty_card_when_no_domain_id(monkeypatch):
    """case_file.domain_id=None -> fallback metadata, doesn't crash."""
    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(domain_id=None)
    facts = KGFacts(deposit_protection_status="protected_late")
    card, meta = pred._render_factor_card_via_pack(pred._case_file, facts)
    # Without a domain_id we cannot resolve a pack; the renderer should
    # report this as a fallback regardless of legacy parity.
    assert meta["kg_used_for_prediction"] is False
    assert meta["kg_fallback_mode"] == "legacy_no_domain_id"


def test_render_via_pack_falls_back_to_kg_facts_when_case_graph_missing(monkeypatch):
    """When _case_graph_by_issue is empty (Task 4.5 hasn't landed), fall back
    to _kg_facts_by_issue. The deposit renderer accepts KGFacts directly."""
    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(domain_id="housing.deposit.v1")
    facts = KGFacts(deposit_protection_status="protected_late")
    card, _ = pred._render_factor_card_via_pack(pred._case_file, facts)
    assert "deposit_protection_status: protected_late" in card


def test_render_via_pack_handles_none_case_graph(monkeypatch):
    """case_graph=None -> empty card with structured failure metadata."""
    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(domain_id="housing.deposit.v1")
    card, meta = pred._render_factor_card_via_pack(pred._case_file, None)
    assert card == ""
    assert meta["kg_used_for_prediction"] is False


# ---------------------------------------------------------------------------
# Spec §19 PR 4: rag_only must hide the factor card; hybrid must include it.
# We test the gate inside `_predict_issue` directly via captured prompts.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_predict_issue_rag_only_renders_empty_card(monkeypatch):
    """Spec §19 PR 4: when prompt_mode='rag_only', no factor card injection
    even with populated _kg_facts_by_issue."""
    from llm_orchestrator.models.prediction_v2 import (
        IssueContext,
        IssueRetrievalResult,
        IssueType,
    )

    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(
        domain_id="housing.deposit.v1",
        case_id="c1",
        tenancy=None,
        property=None,
        tenant_narrative=None,
        landlord_narrative=None,
    )
    pred._kg_facts_by_issue = {
        IssueType.DEPOSIT_PROTECTION: KGFacts(
            deposit_protection_status="protected_late"
        ),
    }

    captured: list[str] = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[],"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    pred.llm.generate = fake_generate

    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    retrieval = IssueRetrievalResult(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        results=[
            {
                "case_reference": "P1",
                "year": 2023,
                "chunk_text": "x",
                "combined_score": 0.8,
            }
        ],
        is_sufficient=True,
        confidence=0.8,
    )
    await pred._predict_issue(issue, retrieval, prompt_mode="rag_only")
    assert len(captured) == 1
    assert "KEY KG FACTS (typed):" not in captured[0]
    assert "deposit_protection_status: protected_late" not in captured[0]


@pytest.mark.asyncio
async def test_predict_issue_hybrid_includes_card_when_pack_returns_card(
    monkeypatch,
):
    """Spec §19 PR 4: when prompt_mode='hybrid', the factor card IS in the prompt
    when KG is populated."""
    from llm_orchestrator.models.prediction_v2 import (
        IssueContext,
        IssueRetrievalResult,
        IssueType,
    )

    monkeypatch.setenv("STREAM_C_PR4", "1")
    pred = _make_predictor()
    pred._case_file = SimpleNamespace(
        domain_id="housing.deposit.v1",
        case_id="c1",
        tenancy=None,
        property=None,
        tenant_narrative=None,
        landlord_narrative=None,
    )
    pred._kg_facts_by_issue = {
        IssueType.DEPOSIT_PROTECTION: KGFacts(
            deposit_protection_status="protected_late",
            deposit_late_by_days=14,
        ),
    }

    captured: list[str] = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[],"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    pred.llm.generate = fake_generate

    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    retrieval = IssueRetrievalResult(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        results=[
            {
                "case_reference": "P1",
                "year": 2023,
                "chunk_text": "x",
                "combined_score": 0.8,
            }
        ],
        is_sufficient=True,
        confidence=0.8,
    )
    await pred._predict_issue(issue, retrieval, prompt_mode="hybrid")
    assert len(captured) == 1
    assert "KEY KG FACTS (typed):" in captured[0]
    assert "deposit_protection_status: protected_late" in captured[0]
