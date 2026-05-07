"""End-to-end smoke test for PR 4 — pack-routed factor card in prompts.

Builds two end-to-end scenarios that exercise the full
``PredictionEngineV2.predict()`` entry point under PR 4 wiring:

1. ``housing.deposit.v1`` + ``KG_ONLY``: prompt contains the deposit pack's
   ``KEY KG FACTS (typed):`` header rendered from the typed deposit
   ``KGFacts`` adapter.
2. ``housing.repairs_social.v1`` + ``HYBRID``: prompt contains the repairs
   pack's ``KEY FACTORS (factor-graph derived):`` header rendered from
   the case-graph ``factor_assertions``.

These complement the unit tests in ``test_kg_fact_card.py`` and
``test_kg_in_prompt_golden.py`` by routing through ``PredictionEngineV2``
end-to-end (issue decomposition → KG-facts derivation → renderer dispatch
→ IRAC / repairs prompt assembly → mocked LLM call).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §19 PR 4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_orchestrator.models.prediction_v2 import (
    IssueContext,
    IssueRetrievalResult,
    IssueType,
    PredictionMode,
)
from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2


# ---------------------------------------------------------------------------
# Shared fixture helpers (duplicated from existing tests; keeps this file
# self-contained and decoupled from private helpers in sibling test modules).
# ---------------------------------------------------------------------------


def _build_late_protection_kg():
    """Deposit-domain KG with deliberately-late deposit protection.

    Mirrors ``_build_late_protection_kg_for_engine`` in
    ``test_prediction_engine_agentic.py``.
    """
    from kg_builder.models.graph import KnowledgeGraph
    from kg_builder.models.nodes import IssueNode, LeaseNode, PartyNode

    kg = KnowledgeGraph(case_id="case_pr4_integration_deposit")
    kg.add_node(PartyNode(node_id="party_tenant", role="tenant"))
    kg.add_node(PartyNode(node_id="party_landlord", role="landlord"))
    kg.add_node(
        LeaseNode(
            node_id="lease_main",
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
            deposit_amount=1500.0,
            deposit_protected=True,
            deposit_scheme="DPS",
            protection_date=date(2023, 4, 1),  # 90 days late
        )
    )
    kg.add_node(
        IssueNode(
            node_id="issue_deposit_protection",
            issue_type="deposit_protection",
            description="Deposit protection compliance issue",
        )
    )
    return kg


def _make_deposit_case_file(case_id: str = "case_pr4_deposit"):
    return SimpleNamespace(
        case_id=case_id,
        domain_id="housing.deposit.v1",
        tenant_narrative=None,
        landlord_narrative=None,
        tenancy=SimpleNamespace(
            deposit_amount=1500.0,
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
            tenancy_type="AST",
            deposit_protected=None,
            deposit_scheme=None,
            protection_date=None,
            prescribed_info_provided=None,
            prescribed_info_date=None,
        ),
        property=SimpleNamespace(region="London", postcode=None),
    )


# ---------------------------------------------------------------------------
# Repairs fixture (FactorAssertion-bearing fake KG).
# ---------------------------------------------------------------------------


@dataclass
class _FakeRepairsKG:
    """Stand-in for KnowledgeGraph carrying repairs ``factor_assertions`` and
    the auxiliary attributes the graph-quality heuristic reads
    (``dated_events``, ``issues``, ``candidate_outcomes``).

    Mirrors ``packages/domain_packs/tests/test_repairs_renderer.py:_FakeKG``
    plus the extra attrs read by
    ``IssuePredictor._compute_graph_quality_score`` and the
    ``get_nodes_by_type`` API used by ``derive_kg_facts`` (engines call it
    even for non-deposit domains; we return [] so deposit-typed facts are
    all "unknown" — repairs cards do not consume them).
    """

    factor_assertions: List = field(default_factory=list)
    dated_events: List = field(default_factory=list)
    issues: List = field(default_factory=list)
    candidate_outcomes: List = field(default_factory=list)

    def get_nodes_by_type(self, node_type):
        return []


def _make_repairs_factor_assertion(factor_id: str, value, supported_by=None):
    """Build a single FactorAssertion for the housing.repairs_social.v1 pack.

    Mirrors ``_make_fa`` in ``test_repairs_renderer.py``.
    """
    from legal_core.graph.factor_assertion import (
        ExtractionMethod,
        FactorAssertion,
        FactorPolarity,
    )

    return FactorAssertion(
        factor_assertion_id=f"fa_{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        value=value,
        value_type=value.value_type,
        confidence=0.92,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=list(supported_by) if supported_by else ["span_1"],
        requires_human_review=False,
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="test_extractor_v1",
        verifier_version="test_verifier_v1",
    )


def _build_repairs_kg_with_5_factors() -> _FakeRepairsKG:
    """Build a fake KG with 5 evidence-backed factor assertions (passes
    ``housing.repairs_social.v1`` graph_quality_gate: min 5 evidence-backed
    factors, min 2 dated events, min 1 issue, min 1 outcome candidate)."""
    from legal_core.graph.factor_value import FactorValue, FactorValueType

    factor_assertions = [
        _make_repairs_factor_assertion(
            "repair_responsibility_established",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
            supported_by=["span_resp_1"],
        ),
        _make_repairs_factor_assertion(
            "hazard_or_disrepair_reported",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
            supported_by=["span_report_1"],
        ),
        _make_repairs_factor_assertion(
            "landlord_notice_established",
            FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
            supported_by=["span_notice_1"],
        ),
        _make_repairs_factor_assertion(
            "repair_delay_days",
            FactorValue(value_type=FactorValueType.DURATION, duration_days=180),
            supported_by=["span_delay_1"],
        ),
        _make_repairs_factor_assertion(
            "impact_severity_reported",
            FactorValue(value_type=FactorValueType.ENUM, enum="severe"),
            supported_by=["span_impact_1"],
        ),
    ]
    return _FakeRepairsKG(
        factor_assertions=factor_assertions,
        dated_events=[
            SimpleNamespace(date=date(2023, 1, 1), description="report"),
            SimpleNamespace(date=date(2023, 6, 1), description="repair_attempt"),
        ],
        issues=[SimpleNamespace(issue_type="repairs_disrepair")],
        candidate_outcomes=[SimpleNamespace(outcome="maladministration")],
    )


def _make_repairs_case_file(case_id: str = "case_pr4_repairs"):
    return SimpleNamespace(
        case_id=case_id,
        domain_id="housing.repairs_social.v1",
        tenant_narrative=(
            "Damp and mould have persisted in the bedroom for 6 months despite "
            "repeated reports."
        ),
        landlord_narrative="An inspection was attempted but resident missed the slot.",
        tenancy=SimpleNamespace(
            deposit_amount=None,
            start_date=date(2022, 6, 1),
            end_date=None,
            tenancy_type="social",
            deposit_protected=None,
            deposit_scheme=None,
            protection_date=None,
            prescribed_info_provided=None,
            prescribed_info_date=None,
        ),
        property=SimpleNamespace(region="London", postcode=None),
    )


# ---------------------------------------------------------------------------
# Test 1: deposit + KG_ONLY → prompt contains "KEY KG FACTS (typed):"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deposit_kg_only_prompt_includes_factor_card(monkeypatch):
    """End-to-end: ``housing.deposit.v1`` + ``KG_ONLY`` mode produces a
    prompt that contains the deposit pack's ``KEY KG FACTS (typed):``
    header (rendered from the legacy ``KGFacts`` adapter via
    ``IssuePredictor._render_factor_card_via_pack``).
    """
    monkeypatch.setenv("STREAM_C_PR4", "1")

    captured: list = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[],'
            '"counterfactuals":[{"condition":"c","alternative_outcome":"o",'
            '"confidence_shift":-0.1}],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    llm = MagicMock()
    llm.generate = fake_generate

    rag = AsyncMock()
    # KG_ONLY must skip retrieval entirely; spy that the engine respects this.
    rag.retrieve = AsyncMock()

    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    kg = _build_late_protection_kg()
    case_file = _make_deposit_case_file()

    fake_issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="late deposit protection",
        kg_constraints=[],
        data_completeness=0.7,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.KG_ONLY,
    )

    rag.retrieve.assert_not_called()
    assert captured, "Mock LLM was not invoked"
    prompt = captured[0]
    assert "KEY KG FACTS (typed):" in prompt, (
        f"deposit pack header missing — prompt was:\n{prompt}"
    )
    assert "deposit_protection_status:" in prompt
    # Sanity: this is the typed-factor card, not a free-text summary.
    assert "protected_late" in prompt


# ---------------------------------------------------------------------------
# Test 2: repairs + HYBRID → prompt contains "KEY FACTORS (factor-graph derived):"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repairs_hybrid_prompt_includes_factor_card(monkeypatch):
    """End-to-end: ``housing.repairs_social.v1`` + ``HYBRID`` mode produces
    a prompt that contains the repairs pack's
    ``KEY FACTORS (factor-graph derived):`` header (rendered from
    ``case_graph.factor_assertions`` via the repairs renderer).

    The retriever is monkey-patched to return canned sufficient results so
    the test focuses on the prompt-assembly path; real retrieval is exercised
    elsewhere (eval harness).
    """
    monkeypatch.setenv("STREAM_C_PR4", "1")
    monkeypatch.setenv("STREAM_C_PR4_REPAIRS", "1")

    captured: list = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,'
            '"quote":"q","relevance":"r"}],'
            '"counterfactuals":[],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok",'
            '"predicted_determination":"maladministration",'
            '"amount_construct":null}'
        )

    llm = MagicMock()
    llm.generate = fake_generate

    rag = AsyncMock()
    rag.retrieve = AsyncMock()

    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag, min_cases_required=3)

    fake_issue = IssueContext(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        issue_description="damp and mould 6 months",
        kg_constraints=[],
        data_completeness=0.7,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    canned_retrieval = IssueRetrievalResult(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        query_used="damp mould response timelines",
        results=[
            {
                "case_reference": "P1",
                "year": 2023,
                "chunk_text": "compensation £700 for damp delay",
                "text": "compensation £700 for damp delay",
                "section_type": "orders",
                "combined_score": 0.85,
                "semantic_score": 0.85,
                "bm25_score": 0.0,
            }
        ]
        * 5,
        is_sufficient=True,
        rag_confidence=0.85,
    )

    async def fake_retrieve_all(
        issues, case_file, top_k, *, kg_facts_by_issue=None, mode=None,
        retrieval_strategy=None,
    ):
        return {issue.issue_type: canned_retrieval for issue in issues}

    engine.issue_retriever.retrieve_all = fake_retrieve_all  # type: ignore[assignment]

    kg = _build_repairs_kg_with_5_factors()
    case_file = _make_repairs_case_file()

    await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.HYBRID,
    )

    assert captured, "Mock LLM was not invoked"
    prompt = captured[0]
    assert "KEY FACTORS (factor-graph derived):" in prompt, (
        f"repairs pack header missing — prompt was:\n{prompt}"
    )
    # Spot-check that at least one factor was rendered into the card.
    assert "repair_responsibility_established" in prompt
