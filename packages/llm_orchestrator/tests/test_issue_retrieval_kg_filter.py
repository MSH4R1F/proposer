"""Tests for KG-aware retrieval filter / re-rank (SHA-33)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_orchestrator.models.prediction_v2 import (
    IssueContext,
    IssueType,
    PredictionMode,
)
from llm_orchestrator.pipeline.issue_retrieval import IssueRetriever, RagQuerySpec
from llm_orchestrator.pipeline.kg_facts import KGFacts


def _stub_case_file():
    cf = MagicMock()
    cf.tenancy.deposit_amount = 1500.0
    cf.tenancy.start_date = None
    cf.tenancy.end_date = None
    cf.property.region = "London"
    cf.dispute_amount = None
    cf.tenant_narrative = None
    cf.metadata = {}
    return cf


def _make_results(*pairs):
    """pairs: (case_reference, semantic_score, text)."""
    return [
        {
            "case_reference": ref,
            "year": 2023,
            "semantic_score": score,
            "bm25_score": 0.0,
            "text": text,
            "chunk_text": text,
        }
        for ref, score, text in pairs
    ]


@pytest.mark.asyncio
async def test_kg_filter_demotes_on_time_protection_when_kg_says_late():
    """KG says protected_late → on-time precedents demoted below late ones."""
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": _make_results(
                ("ON_TIME", 0.9, "deposit was protected within 14 days, claim dismissed"),
                ("LATE", 0.7, "deposit protected after 60 days, 2x penalty awarded"),
            ),
            "confidence": 0.8,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="late deposit protection",
        kg_constraints=[],
        data_completeness=0.9,
    )
    kg_facts = KGFacts(
        deposit_protection_status="protected_late",
        deposit_late_by_days=60,
    )

    result = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2, kg_facts=kg_facts, mode=PredictionMode.HYBRID,
    )

    refs = [r["case_reference"] for r in result.results]
    assert refs == ["LATE", "ON_TIME"], (
        f"KG-aware reranker should put LATE first when KG says protected_late, got {refs}"
    )
    on_time_chunk = next(r for r in result.results if r["case_reference"] == "ON_TIME")
    late_chunk = next(r for r in result.results if r["case_reference"] == "LATE")
    assert on_time_chunk["kg_filter_penalty"] < 0
    assert late_chunk["kg_filter_penalty"] == 0  # LATE is not contradicted
    # combined_score is what IssuePredictor reads — must reflect the penalty.
    # ON_TIME's combined_score must be lower than LATE's after the filter.
    assert on_time_chunk["combined_score"] < late_chunk["combined_score"]


@pytest.mark.asyncio
async def test_kg_filter_disabled_in_rag_only_mode():
    """RAG_ONLY mode bypasses the KG filter — original ranking preserved."""
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": _make_results(
                ("ON_TIME", 0.9, "deposit was protected within 14 days, claim dismissed"),
                ("LATE", 0.7, "deposit protected after 60 days, 2x penalty awarded"),
            ),
            "confidence": 0.8,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="late deposit protection",
        kg_constraints=[],
        data_completeness=0.9,
    )
    kg_facts = KGFacts(deposit_protection_status="protected_late")

    result = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2, kg_facts=kg_facts, mode=PredictionMode.RAG_ONLY,
    )

    refs = [r["case_reference"] for r in result.results]
    # ON_TIME has higher semantic_score, so without KG filter it stays ranked first.
    assert refs[0] == "ON_TIME"


@pytest.mark.asyncio
async def test_kg_filter_noop_when_kg_facts_empty():
    """All-unknown KGFacts must produce identical results to RAG_ONLY."""
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": _make_results(
                ("A", 0.9, "deposit was protected within 14 days"),
                ("B", 0.7, "different precedent"),
            ),
            "confidence": 0.8,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )

    hybrid = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2,
        kg_facts=KGFacts(), mode=PredictionMode.HYBRID,
    )
    rag_only = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2,
        kg_facts=KGFacts(), mode=PredictionMode.RAG_ONLY,
    )

    assert [r["case_reference"] for r in hybrid.results] == \
           [r["case_reference"] for r in rag_only.results]
    assert "kg_filter_penalty" not in hybrid.results[0]


@pytest.mark.asyncio
async def test_empty_kg_hybrid_byte_identical_to_rag_only():
    """Regression guard: when KGFacts is all-unknown (empty/missing KG),
    HYBRID mode produces results identical to RAG_ONLY for the same case."""
    rag_calls = []

    async def fake_retrieve(query, top_k, query_region):
        rag_calls.append(query)
        return {
            "results": _make_results(
                ("X", 0.8, "some precedent"),
                ("Y", 0.6, "another precedent"),
            ),
            "confidence": 0.7,
        }

    rag = AsyncMock()
    rag.retrieve = fake_retrieve
    retriever = IssueRetriever(rag, min_cases_required=1)

    issue = IssueContext(
        issue_type=IssueType.DAMAGE,
        issue_description="damage",
        kg_constraints=[],
        data_completeness=0.5,
    )

    hybrid = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2,
        kg_facts=KGFacts(), mode=PredictionMode.HYBRID,
    )
    rag_only = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2,
        kg_facts=KGFacts(), mode=PredictionMode.RAG_ONLY,
    )

    assert [r["case_reference"] for r in hybrid.results] == \
           [r["case_reference"] for r in rag_only.results]
    # No kg_filter_penalty key written when filter is a no-op
    assert "kg_filter_penalty" not in hybrid.results[0]


@pytest.mark.asyncio
async def test_kg_filter_demotes_inventory_present_chunks_when_baseline_absent():
    """KG says no check-in inventory → precedents praising inventory get demoted."""
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": _make_results(
                ("WITH_INV", 0.85, "the check-in inventory clearly recorded the condition"),
                ("NO_INV", 0.65, "without baseline evidence, landlord deduction failed"),
            ),
            "confidence": 0.7,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.CLEANING,
        issue_description="cleaning charges disputed",
        kg_constraints=[],
        data_completeness=0.7,
    )
    kg_facts = KGFacts(check_in_inventory_baseline="absent")

    result = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2, kg_facts=kg_facts, mode=PredictionMode.HYBRID,
    )

    refs = [r["case_reference"] for r in result.results]
    assert refs[0] == "NO_INV", (
        f"KG-aware reranker should put NO_INV first when KG says inventory absent, got {refs}"
    )


@pytest.mark.asyncio
async def test_repairs_rerank_promotes_issue_and_outcome_chunks():
    """Ombudsman retrieval should prefer outcome-bearing on-issue chunks.

    A very semantic generic background chunk is less useful to the prediction
    prompt than a slightly lower-semantic chunk that mentions damp/mould plus
    the Ombudsman finding/remedy.
    """
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": _make_results(
                (
                    "BACKGROUND",
                    0.95,
                    "The resident lives in a two bedroom flat and contacted the landlord.",
                ),
                (
                    "OUTCOME",
                    0.65,
                    "The damp and mould complaint led to a service failure finding. "
                    "The landlord must pay compensation.",
                ),
            ),
            "confidence": 0.8,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        kg_constraints=[],
        data_completeness=0.9,
    )

    result = await retriever._retrieve_for_issue(
        issue, _stub_case_file(), top_k=2, kg_facts=KGFacts(), mode=PredictionMode.HYBRID,
    )

    refs = [r["case_reference"] for r in result.results]
    assert refs[0] == "OUTCOME"
    assert result.results[0]["repairs_issue_match_score"] > 0
    assert result.results[0]["ombudsman_outcome_signal_score"] == 1.0
    assert rag.retrieve.await_count >= 7
    assert all(call.kwargs["top_k"] >= 8 for call in rag.retrieve.await_args_list)
    assert "liability:" in result.query_used
    assert "award_amount:" in result.query_used
    assert "counterexample:" in result.query_used
    assert "retrieval_purposes" in result.results[0]


@pytest.mark.asyncio
async def test_repairs_retrieval_runs_remedy_pass_and_keeps_order_chunk():
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        side_effect=[
            {
                "results": _make_results(
                    (
                        "BACKGROUND",
                        0.95,
                        "The resident lives in a flat and contacted the landlord.",
                    ),
                ),
                "confidence": 0.7,
            },
            {
                "results": _make_results(
                    (
                        "ORDER",
                        0.55,
                        "What the landlord must do: ordered the landlord to pay "
                        "£600 compensation for maladministration.",
                    ),
                ),
                "confidence": 0.8,
            },
        ]
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        issue_description="repairs and complaint handling",
        kg_constraints=[],
        data_completeness=0.8,
    )

    result = await retriever._retrieve_for_issue(
        issue,
        _stub_case_file(),
        top_k=2,
        kg_facts=KGFacts(),
        mode=PredictionMode.RAG_ONLY,
    )

    refs = [r["case_reference"] for r in result.results]
    assert refs[0] == "ORDER"
    assert rag.retrieve.await_count == 2
    assert "ordered the landlord" in rag.retrieve.await_args_list[1].kwargs["query"]


@pytest.mark.asyncio
async def test_deposit_retrieval_does_not_run_remedy_pass():
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": _make_results(
                ("A", 0.8, "deposit protected late"),
                ("B", 0.7, "deposit protected on time"),
            ),
            "confidence": 0.7,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="deposit protection",
        kg_constraints=[],
        data_completeness=0.8,
    )

    await retriever._retrieve_for_issue(
        issue,
        _stub_case_file(),
        top_k=2,
        kg_facts=KGFacts(),
        mode=PredictionMode.RAG_ONLY,
    )

    rag.retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_repairs_hybrid_passes_target_exclusion_filters():
    calls = []

    async def fake_retrieve(**kwargs):
        calls.append(kwargs)
        return {
            "results": _make_results(
                (
                    "CASE_A",
                    0.8,
                    "Damp and mould service failure. The landlord must pay "
                    "£400 compensation.",
                ),
            ),
            "confidence": 0.8,
        }

    rag = AsyncMock()
    rag.retrieve = fake_retrieve
    retriever = IssueRetriever(rag, min_cases_required=1)
    case_file = SimpleNamespace(
        case_id="housing-ombudsman-202515515",
        property=SimpleNamespace(region="London"),
        metadata={
            "domain_id": "housing.repairs_social.v1",
            "matter_type": "repairs_damp_mould",
            "target_source_id": "202515515",
        },
        tenant_narrative="Resident reported damp and mould.",
        landlord_narrative=None,
        dispute_amount=None,
    )
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        kg_constraints=[],
        data_completeness=0.8,
    )

    await retriever._retrieve_for_issue(
        issue,
        case_file,
        top_k=1,
        kg_facts=KGFacts(),
        mode=PredictionMode.HYBRID,
    )

    assert len(calls) >= 8
    first_filter = calls[0]["filters"]
    assert first_filter.matter_type == "repairs_damp_mould"
    assert "202515515" in first_filter.excluded_source_ids
    assert "housing-ombudsman-202515515" in first_filter.excluded_source_ids


@pytest.mark.asyncio
async def test_purposeful_query_annotates_pydantic_retrieval_result_cards():
    from rag_engine.config import RetrievalResult

    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": [
                RetrievalResult(
                    chunk_id="chunk-1",
                    case_reference="HOS-1",
                    chunk_text=(
                        "The damp and mould complaint led to a service failure. "
                        "The landlord must pay £400 compensation."
                    ),
                    section_type="decision",
                    semantic_score=0.8,
                    semantic_rank=1,
                    bm25_score=1.0,
                    bm25_rank=1,
                    combined_score=0.9,
                    year=2025,
                    region="London",
                    case_type=None,
                )
            ],
            "confidence": 0.8,
        }
    )
    retriever = IssueRetriever(rag, min_cases_required=1)
    spec = RagQuerySpec(
        purpose="award_amount",
        query="damp mould compensation award",
        top_k=8,
        require_amount=True,
    )

    response = await retriever._retrieve_rag_query_spec(spec, _stub_case_file())

    card = response["results"][0]
    assert isinstance(card, dict)
    assert card["case_reference"] == "HOS-1"
    assert card["retrieval_purpose"] == "award_amount"
    assert card["retrieval_purposes"] == ["award_amount"]
    assert card["has_award_amount"] is True
    assert card["ombudsman_finding_signal"] == "service_failure"
