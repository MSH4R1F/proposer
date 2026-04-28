"""Golden test: KG facts must measurably reach the IRAC prompt (SHA-33 Task 7).

This is the regression guard for SHA-33 DoD #1 ("PredictionEngineV2 receives
the built KG as structured input"). It builds a real KG with deliberately-
late deposit protection, runs HYBRID mode end-to-end against a mock LLM,
and asserts that the typed fact card surfaces in the user prompt that
hits the model.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_orchestrator.models.prediction_v2 import (
    IssueContext,
    IssueType,
    PredictionMode,
)
from llm_orchestrator.pipeline.kg_facts import derive_kg_facts


def _make_case_file_stub(case_id: str):
    """SimpleNamespace-based stub — explicit attribute control (no MagicMock auto-attrs)."""
    return SimpleNamespace(
        case_id=case_id,
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


def _build_late_protection_kg():
    from kg_builder.builders.graph_builder import GraphBuilder
    from kg_builder.models.graph import KnowledgeGraph
    from kg_builder.models.nodes import (
        IssueNode,
        LeaseNode,
        PartyNode,
    )

    kg = KnowledgeGraph(case_id="case_late")
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


@pytest.mark.asyncio
async def test_kg_typed_facts_surface_in_irac_prompt_under_hybrid():
    """End-to-end: HYBRID mode with a late-protection KG must put
    'deposit_protection_status: protected_late' into the IRAC user prompt."""
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    kg = _build_late_protection_kg()
    issue_type = IssueType.DEPOSIT_PROTECTION

    # Sanity-check derive_kg_facts against the fixture KG before going through the engine
    facts = derive_kg_facts(kg, issue_type)
    assert facts.deposit_protection_status == "protected_late"
    assert facts.deposit_late_by_days == 90

    captured_prompts = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured_prompts.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    llm = MagicMock()
    llm.generate = fake_generate

    rag = AsyncMock()
    rag.retrieve = AsyncMock(return_value={
        "results": [
            {
                "case_reference": "P1",
                "year": 2023,
                "semantic_score": 0.8,
                "bm25_score": 0.0,
                "text": "deposit protected after 60 days, 2x penalty awarded",
                "chunk_text": "deposit protected after 60 days, 2x penalty awarded",
            }
        ] * 3,  # ≥ min_cases_required=3
        "confidence": 0.8,
    })

    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag, min_cases_required=3)

    case_file = _make_case_file_stub("case_late")

    fake_issue = IssueContext(
        issue_type=issue_type,
        issue_description="late deposit protection",
        kg_constraints=[],
        data_completeness=0.7,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.HYBRID,
    )

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # The typed KG fact card must appear in the IRAC user prompt
    assert "KEY KG FACTS (typed):" in prompt, f"fact card missing — prompt was:\n{prompt}"
    assert "deposit_protection_status: protected_late" in prompt
    assert "late by 90 days" in prompt
    assert "scheme: DPS" in prompt


@pytest.mark.asyncio
async def test_kg_fact_card_absent_in_rag_only_mode():
    """RAG_ONLY mode must NOT render the KG fact card even when KG is passed."""
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    kg = _build_late_protection_kg()

    captured_prompts = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured_prompts.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    llm = MagicMock()
    llm.generate = fake_generate

    rag = AsyncMock()
    rag.retrieve = AsyncMock(return_value={
        "results": [
            {"case_reference": "P1", "year": 2023, "semantic_score": 0.8,
             "bm25_score": 0.0, "text": "x", "chunk_text": "x"}
        ] * 3,
        "confidence": 0.8,
    })

    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag, min_cases_required=3)

    case_file = _make_case_file_stub("case_late_rag")

    fake_issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.RAG_ONLY,
    )

    prompt = captured_prompts[0]
    assert "KEY KG FACTS (typed):" not in prompt, (
        "RAG_ONLY must hide KG fact card; got prompt:\n" + prompt
    )
