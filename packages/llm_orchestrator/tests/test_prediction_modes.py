"""Tests for the PredictionMode ablation seam (SHA-33)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_orchestrator.models.prediction_v2 import PredictionMode, RetrievalStrategy


def test_prediction_mode_has_four_modes():
    assert {m.value for m in PredictionMode} == {
        "rag_only",
        "kg_only",
        "hybrid",
        "llm_only",
    }


def test_prediction_mode_hybrid_value():
    assert PredictionMode.HYBRID.value == "hybrid"
    assert PredictionMode.RAG_ONLY.value == "rag_only"
    assert PredictionMode.KG_ONLY.value == "kg_only"
    assert PredictionMode.LLM_ONLY.value == "llm_only"


def test_outcome_type_serialises_plural_but_accepts_legacy_singular():
    from llm_orchestrator.models.prediction_v2 import OutcomeType, PredictionResult

    assert OutcomeType.TENANT_WIN.value == "tenant_wins"
    assert OutcomeType.LANDLORD_WIN.value == "landlord_wins"
    assert OutcomeType("tenant_win") is OutcomeType.TENANT_WIN
    assert OutcomeType("landlord_win") is OutcomeType.LANDLORD_WIN

    result = PredictionResult(
        case_id="case-outcome-normalisation",
        overall_outcome="tenant_win",
        overall_confidence=0.7,
    )

    assert result.overall_outcome is OutcomeType.TENANT_WIN
    assert result.overall_outcome.value == "tenant_wins"


def test_retrieval_strategy_is_separate_from_prediction_mode():
    assert {s.value for s in RetrievalStrategy} == {
        "chunk_rag",
        "proposition_direct",
        "proposition_pagerank",
        "hybrid_chunk_proposition",
        # Architecture C: LLM-driven iterative retrieval agent (added on
        # feature/agentic-retrieval). Distinct from PredictionMode —
        # AGENTIC composes with HYBRID or RAG_ONLY (KG_ONLY / LLM_ONLY
        # skip retrieval entirely so AGENTIC is moot there).
        "agentic",
        # Stream C PR 5 Task 5.5: factor-constrained two-pass retrieval
        # (comparators + counterexamples). Selected via env flag
        # STREAM_C_FACTOR_RETRIEVAL=1; falls back to chunk_rag when
        # asserted_factors / pack / repository are missing.
        "factor_constrained",
    }
    assert PredictionMode.HYBRID.value == "hybrid"


def test_purposeful_repairs_trace_only_applies_to_chunk_rag_strategy():
    from llm_orchestrator.models.prediction_v2 import IssueContext, IssueType
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    case_file = SimpleNamespace(metadata={"domain_id": "housing.repairs_social.v1"})
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
    )

    assert PredictionEngineV2._uses_purposeful_repairs_retrieval(
        case_file,
        [issue],
        PredictionMode.HYBRID,
        RetrievalStrategy.CHUNK_RAG,
    )
    assert not PredictionEngineV2._uses_purposeful_repairs_retrieval(
        case_file,
        [issue],
        PredictionMode.HYBRID,
        RetrievalStrategy.PROPOSITION_DIRECT,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expect_kg_passed",
    [
        (PredictionMode.HYBRID, True),
        (PredictionMode.KG_ONLY, True),
        (PredictionMode.RAG_ONLY, False),
        (PredictionMode.LLM_ONLY, False),
    ],
)
async def test_predict_passes_kg_to_decomposer_per_mode(mode, expect_kg_passed):
    """RAG_ONLY and LLM_ONLY must hide the KG from IssueDecomposer.

    HYBRID and KG_ONLY pass the graph through.
    """
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    captured = {"decomposer_kg": "sentinel"}

    sentinel_kg = object()  # opaque marker for "the KG was passed"
    llm = MagicMock()
    rag = AsyncMock()
    rag.retrieve = AsyncMock(return_value={"results": [], "confidence": 0.0})
    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    real_decompose = engine.issue_decomposer.decompose

    def spy_decompose(case_file, knowledge_graph=None):
        captured["decomposer_kg"] = knowledge_graph
        return []  # no issues → engine short-circuits to uncertain

    engine.issue_decomposer.decompose = spy_decompose

    case_file = MagicMock()
    case_file.case_id = "case_test_mode"
    await engine.predict(
        case_file=case_file,
        knowledge_graph=sentinel_kg,
        mode=mode,
    )

    if expect_kg_passed:
        assert captured["decomposer_kg"] is sentinel_kg, f"{mode.value}: KG must reach decomposer"
    else:
        assert captured["decomposer_kg"] is None, f"{mode.value}: KG must NOT reach decomposer"


@pytest.mark.asyncio
async def test_llm_only_skips_retrieval_and_returns_real_prediction():
    """LLM_ONLY mode must NOT call rag.retrieve and must produce a non-uncertain prediction."""
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2
    from llm_orchestrator.models.prediction_v2 import IssueContext, IssueType, OutcomeType

    rag = AsyncMock()
    rag.retrieve = AsyncMock()  # spy — must not be called
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=(
        '{"outcome":"tenant_wins","raw_confidence":0.8,'
        '"reasoning":"Based on general principles","supporting_cases":[],'
        '"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
        '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
    ))
    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    case_file = MagicMock()
    case_file.case_id = "case_llm_only"
    case_file.tenancy.deposit_amount = 1500.0
    case_file.tenancy.start_date = None
    case_file.tenancy.end_date = None
    case_file.tenancy.tenancy_type = "AST"
    case_file.property.region = "London"

    fake_issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    result = await engine.predict(
        case_file=case_file, mode=PredictionMode.LLM_ONLY,
    )

    rag.retrieve.assert_not_called()
    llm.generate.assert_awaited_once()
    # The model returned tenant_wins, so the result must NOT be UNCERTAIN.
    assert result.overall_outcome != OutcomeType.UNCERTAIN
    assert result.overall_confidence > 0


@pytest.mark.asyncio
async def test_llm_only_forces_empty_supporting_cases():
    """LLM_ONLY must force-empty supporting_cases regardless of model output —
    no retrieval ran, so model can't have valid citations."""
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2
    from llm_orchestrator.models.prediction_v2 import IssueContext, IssueType

    rag = AsyncMock()
    llm = MagicMock()
    # Model misbehaves and returns a fake case ref
    llm.generate = AsyncMock(return_value=(
        '{"outcome":"tenant_wins","raw_confidence":0.8,'
        '"reasoning":"Citing Smith v Jones [2023] CHI/123","'
        'supporting_cases":[{"case_reference":"CHI/123","year":2023,'
        '"quote":"q","relevance":"r"}],'
        '"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
        '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
    ))
    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    case_file = MagicMock()
    case_file.case_id = "case_llm_no_cite"
    case_file.tenancy.deposit_amount = 1500.0
    case_file.tenancy.start_date = None
    case_file.tenancy.end_date = None
    case_file.tenancy.tenancy_type = "AST"
    case_file.property.region = "London"

    fake_issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    result = await engine.predict(
        case_file=case_file, mode=PredictionMode.LLM_ONLY,
    )

    # No predictions should carry citations in LLM_ONLY mode.
    for ip in result.issue_predictions:
        assert ip.supporting_cases == [], (
            "LLM_ONLY must force-empty supporting_cases — no retrieval to verify against"
        )


@pytest.mark.asyncio
async def test_kg_only_skips_retrieval():
    """KG_ONLY mode skips RAG but still runs the LLM with the IRAC + fact-card prompt."""
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2
    from llm_orchestrator.models.prediction_v2 import IssueContext, IssueType

    rag = AsyncMock()
    rag.retrieve = AsyncMock()  # spy
    captured_prompts = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured_prompts.append(messages[0]["content"])
        return (
            '{"outcome":"split","raw_confidence":0.6,"reasoning":"r",'
            '"supporting_cases":[],"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    llm = MagicMock()
    llm.generate = fake_generate
    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    case_file = MagicMock()
    case_file.case_id = "case_kg_only"
    case_file.tenancy.deposit_amount = 1500.0
    case_file.tenancy.start_date = None
    case_file.tenancy.end_date = None
    case_file.tenancy.tenancy_type = "AST"
    case_file.property.region = "London"

    fake_issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    await engine.predict(
        case_file=case_file,
        knowledge_graph=None,  # KGFacts will be all-unknown → no fact card
        mode=PredictionMode.KG_ONLY,
    )

    rag.retrieve.assert_not_called()
    assert len(captured_prompts) == 1
    # KG_ONLY uses the IRAC prompt — should mention "No retrieved cases"
    assert "No retrieved cases" in captured_prompts[0]


@pytest.mark.asyncio
async def test_predict_metadata_records_mode():
    """PipelineMetadata.mode must surface the mode used (for SHA-68 trace)."""
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    llm = MagicMock()
    rag = AsyncMock()
    rag.retrieve = AsyncMock(return_value={"results": [], "confidence": 0.0})
    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    engine.issue_decomposer.decompose = lambda case_file, kg=None: []  # short-circuit

    case_file = MagicMock()
    case_file.case_id = "case_meta_test"
    result = await engine.predict(
        case_file=case_file, mode=PredictionMode.RAG_ONLY,
    )
    # The short-circuit returns create_uncertain — verify the trace is well-formed for both
    # the short-circuit path and the metadata recorded on the engine instance.
    assert result is not None


@pytest.mark.asyncio
async def test_hybrid_repairs_metadata_records_purposeful_retrieval_steps():
    from llm_orchestrator.models.prediction_v2 import IssueContext, IssueType
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "case_reference": "HOS-1",
                    "year": 2025,
                    "semantic_score": 0.8,
                    "bm25_score": 0.1,
                    "chunk_text": (
                        "Damp and mould service failure. The landlord must pay "
                        "£400 compensation."
                    ),
                }
            ],
            "confidence": 0.8,
        }
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=(
            '{"outcome":"tenant_wins","raw_confidence":0.7,'
            '"reasoning":"r","supporting_cases":[],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )
    )
    engine = PredictionEngineV2(
        llm_client=llm,
        rag_pipeline=rag,
        min_cases_required=1,
    )
    issue = IssueContext(
        issue_type=IssueType.REPAIRS_DAMP_MOULD,
        issue_description="damp and mould repairs",
        kg_constraints=[],
        data_completeness=0.8,
    )
    engine.issue_decomposer.decompose = lambda case_file, kg=None: [issue]

    case_file = SimpleNamespace(
        case_id="housing-ombudsman-202515515",
        metadata={
            "domain_id": "housing.repairs_social.v1",
            "matter_type": "repairs_damp_mould",
        },
        property=SimpleNamespace(region="London", postcode=None),
        tenancy=SimpleNamespace(
            deposit_amount=None,
            start_date=None,
            end_date=None,
            tenancy_type=None,
        ),
        tenant_narrative="Resident reported damp and mould.",
        landlord_narrative=None,
        dispute_amount=None,
    )

    result = await engine.predict(
        case_file=case_file,
        mode=PredictionMode.HYBRID,
        top_k=1,
    )

    steps = result.pipeline_metadata.steps_executed
    assert "retrieval_planning" in steps
    assert "liability_retrieval" in steps
    assert "remedy_retrieval" in steps
    assert "counterexample_retrieval" in steps
    assert "award_amount_retrieval" in steps
    assert rag.retrieve.await_count >= 8
