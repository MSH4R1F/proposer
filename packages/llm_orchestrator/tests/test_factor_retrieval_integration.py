"""Integration tests for FACTOR_CONSTRAINED retrieval routing (Stream C PR 5 — Task 5.5).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §9, §19 PR 5.

These tests cover the wiring added in Task 5.5:
- ``RetrievalStrategy.FACTOR_CONSTRAINED`` enum value exists.
- ``PredictionEngineV2`` flips the active strategy to FACTOR_CONSTRAINED when
  ``STREAM_C_FACTOR_RETRIEVAL=1`` is set and the mode + base strategy permit.
- ``IssueRetriever._retrieve_for_issue`` invokes ``FactorRetriever.build_comparator_pack``
  when asserted_factors are present and falls back to chunk-RAG when they are not.
- ``RetrievalStrategy.PROPOSITION_PAGERANK`` regression — the env flag must NOT
  override an explicit PageRank selection (Hard Constraint #11).

Tests are async and use AsyncMock + MagicMock. No real LLM / RAG calls are
performed.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llm_orchestrator.models.prediction_v2 import (
    IssueContext,
    IssueRetrievalResult,
    IssueType,
    PredictionMode,
    RetrievalStrategy,
)
from llm_orchestrator.pipeline.issue_retrieval import IssueRetriever
from llm_orchestrator.pipeline.kg_facts import KGFacts
from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_factor_assertion(factor_id: str = "repair_responsibility_established"):
    from legal_core.graph.factor_assertion import (
        ExtractionMethod,
        FactorAssertion,
        FactorPolarity,
    )
    from legal_core.graph.factor_value import FactorValue, FactorValueType

    return FactorAssertion(
        factor_assertion_id=f"fa_{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.9,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=["span_1"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="test_v1",
        verifier_version="test_v1",
    )


def _make_issue() -> IssueContext:
    return IssueContext(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        issue_description="Long-running disrepair complaint.",
    )


class _FakeCaseFile:
    """Minimal case-file stand-in for IssueRetriever tests.

    The real ``CaseFile`` model has many required fields; the retriever only
    reaches for a handful of attributes via ``getattr``, so a duck-typed
    object is sufficient and keeps the test surface narrow.
    """

    def __init__(
        self,
        *,
        domain_id: str = "housing.repairs_social.v1",
        case_id: str = "ho-2024-test",
        forum: str = "ombudsman",
    ):
        self.domain_id = domain_id
        self.case_id = case_id
        self.forum = forum
        self.metadata: Dict[str, Any] = {"domain_id": domain_id}
        # tenant/landlord narratives + claims used by chunk-RAG fall-through:
        self.tenant_narrative = "damp and mould for 14 months"
        self.landlord_narrative = "repairs attempted multiple times"

        # Property region used by chunk-RAG fallback path.
        class _Property:
            region = None

        self.property = _Property()

        class _Tenancy:
            deposit_amount = None
            start_date = None
            end_date = None

        self.tenancy = _Tenancy()
        self.dispute_amount = None


class _FakeCaseGraphWithFactors:
    """Carries a ``factor_assertions`` list, mirroring the repairs domain
    case_graph that the engine constructs at Task 4.5."""

    def __init__(self, factor_assertions: List[Any]):
        self.factor_assertions = factor_assertions


class _FakeCaseGraphEmpty:
    """No factor_assertions — exercises the D5 fallback path."""

    factor_assertions: List[Any] = []


class _FakeRAG:
    """Async stub for the chunk-RAG retrieve path (used as a fallback target)."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def retrieve(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        return {"results": [], "confidence": 0.0}


# ---------------------------------------------------------------------------
# 1. Enum value exists
# ---------------------------------------------------------------------------


def test_retrieval_strategy_factor_constrained_value():
    """RetrievalStrategy.FACTOR_CONSTRAINED is part of the enum."""
    assert RetrievalStrategy.FACTOR_CONSTRAINED.value == "factor_constrained"
    # Round-trip through the str enum.
    assert RetrievalStrategy("factor_constrained") is RetrievalStrategy.FACTOR_CONSTRAINED


# ---------------------------------------------------------------------------
# 2. Engine routing — flag flips strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_routes_to_factor_constrained_when_flag_set(monkeypatch):
    """STREAM_C_FACTOR_RETRIEVAL=1 + HYBRID + CHUNK_RAG default → strategy is flipped
    to FACTOR_CONSTRAINED before retrieve_all is called."""
    monkeypatch.setenv("STREAM_C_FACTOR_RETRIEVAL", "1")

    rag = _FakeRAG()
    engine = PredictionEngineV2(
        llm_client=MagicMock(),
        rag_pipeline=rag,
    )

    # Force the engine to short-circuit before LLM calls by stubbing the
    # decomposer to return no issues — this exits via create_uncertain
    # WITHOUT touching LLMs but only AFTER the strategy override has been
    # computed and stamped onto the metadata.
    captured = {}

    original_predict = engine.predict

    async def predict_and_capture(*args, **kwargs):
        # We want to intercept just after the override happens. The simplest
        # observable is the IssueRetriever.retrieve_all kwarg, which sees the
        # final ``strategy``. So we monkeypatch retrieve_all:
        return await original_predict(*args, **kwargs)

    engine.issue_decomposer.decompose = MagicMock(return_value=[_make_issue()])

    async def fake_retrieve_all(*args, **kwargs):
        captured["strategy"] = kwargs.get("retrieval_strategy")
        return {
            IssueType.REPAIRS_DISREPAIR: IssueRetrievalResult(
                issue_type=IssueType.REPAIRS_DISREPAIR, is_sufficient=False
            )
        }

    engine.issue_retriever.retrieve_all = fake_retrieve_all  # type: ignore[assignment]

    case_file = _FakeCaseFile()
    await engine.predict(case_file=case_file, mode=PredictionMode.HYBRID)

    assert captured["strategy"] == RetrievalStrategy.FACTOR_CONSTRAINED


@pytest.mark.asyncio
async def test_engine_uses_legacy_strategy_when_flag_unset(monkeypatch):
    """STREAM_C_FACTOR_RETRIEVAL=0 (default) → engine keeps its existing
    chunk-RAG default and never flips to FACTOR_CONSTRAINED."""
    monkeypatch.setenv("STREAM_C_FACTOR_RETRIEVAL", "0")

    rag = _FakeRAG()
    engine = PredictionEngineV2(
        llm_client=MagicMock(),
        rag_pipeline=rag,
    )
    engine.issue_decomposer.decompose = MagicMock(return_value=[_make_issue()])

    captured: Dict[str, Any] = {}

    async def fake_retrieve_all(*args, **kwargs):
        captured["strategy"] = kwargs.get("retrieval_strategy")
        return {
            IssueType.REPAIRS_DISREPAIR: IssueRetrievalResult(
                issue_type=IssueType.REPAIRS_DISREPAIR, is_sufficient=False
            )
        }

    engine.issue_retriever.retrieve_all = fake_retrieve_all  # type: ignore[assignment]

    case_file = _FakeCaseFile()
    await engine.predict(case_file=case_file, mode=PredictionMode.HYBRID)

    assert captured["strategy"] != RetrievalStrategy.FACTOR_CONSTRAINED
    assert captured["strategy"] == RetrievalStrategy.CHUNK_RAG


@pytest.mark.asyncio
async def test_engine_pagerank_strategy_not_overridden_by_flag(monkeypatch):
    """Hard Constraint #11: explicit PROPOSITION_PAGERANK selection survives
    even when STREAM_C_FACTOR_RETRIEVAL=1. The flag only flips CHUNK_RAG."""
    monkeypatch.setenv("STREAM_C_FACTOR_RETRIEVAL", "1")

    rag = _FakeRAG()
    proposition_retriever = MagicMock()
    proposition_retriever.repository = AsyncMock()

    engine = PredictionEngineV2(
        llm_client=MagicMock(),
        rag_pipeline=rag,
        proposition_retriever=proposition_retriever,
        retrieval_strategy=RetrievalStrategy.PROPOSITION_PAGERANK,
    )
    engine.issue_decomposer.decompose = MagicMock(return_value=[_make_issue()])

    captured: Dict[str, Any] = {}

    async def fake_retrieve_all(*args, **kwargs):
        captured["strategy"] = kwargs.get("retrieval_strategy")
        return {
            IssueType.REPAIRS_DISREPAIR: IssueRetrievalResult(
                issue_type=IssueType.REPAIRS_DISREPAIR, is_sufficient=False
            )
        }

    engine.issue_retriever.retrieve_all = fake_retrieve_all  # type: ignore[assignment]

    case_file = _FakeCaseFile()
    await engine.predict(case_file=case_file, mode=PredictionMode.HYBRID)

    # PageRank survives — env flag did not promote it to FACTOR_CONSTRAINED.
    assert captured["strategy"] == RetrievalStrategy.PROPOSITION_PAGERANK


# ---------------------------------------------------------------------------
# 3. Retriever — FACTOR_CONSTRAINED with empty asserted_factors falls back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factor_constrained_falls_back_when_no_asserted_factors():
    """When the case_graph has no factor_assertions, the FACTOR_CONSTRAINED
    branch returns None from _retrieve_via_factor_retriever and the outer
    branch falls through to _retrieve_chunk_rag (D5)."""
    rag = _FakeRAG()
    proposition_retriever = MagicMock()
    proposition_retriever.repository = AsyncMock()

    retriever = IssueRetriever(
        rag_pipeline=rag,
        proposition_retriever=proposition_retriever,
    )

    issue = _make_issue()
    case_file = _FakeCaseFile()
    # Empty case-graph (no factor_assertions).
    retriever._case_graph_by_issue = {issue.issue_type: _FakeCaseGraphEmpty()}

    result = await retriever._retrieve_for_issue(
        issue=issue,
        case_file=case_file,
        top_k=5,
        kg_facts=KGFacts(),
        mode=PredictionMode.HYBRID,
        retrieval_strategy=RetrievalStrategy.FACTOR_CONSTRAINED,
    )

    # Fell through to chunk-RAG: the fake RAG.retrieve was invoked.
    assert len(rag.calls) >= 1
    # Result is the canonical IssueRetrievalResult shape (chunk-RAG path).
    assert isinstance(result, IssueRetrievalResult)
    assert result.issue_type == issue.issue_type


# ---------------------------------------------------------------------------
# 4. Retriever — FACTOR_CONSTRAINED with asserted_factors invokes FactorRetriever
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factor_constrained_invokes_factor_retriever_with_correct_input():
    """When the case_graph carries asserted_factors, FactorRetriever is
    constructed and its ``build_comparator_pack`` is invoked with a
    ``RetrievalControlInput`` whose ``asserted_factors`` match the input."""
    rag = _FakeRAG()
    repo = AsyncMock()
    proposition_retriever = MagicMock()
    proposition_retriever.repository = repo

    retriever = IssueRetriever(
        rag_pipeline=rag,
        proposition_retriever=proposition_retriever,
    )

    issue = _make_issue()
    case_file = _FakeCaseFile()
    fa = _make_factor_assertion("repair_responsibility_established")
    retriever._case_graph_by_issue = {
        issue.issue_type: _FakeCaseGraphWithFactors([fa])
    }

    # Capture the RetrievalControlInput passed to build_comparator_pack
    # by patching FactorRetriever where it is imported lazily.
    captured_input: Dict[str, Any] = {}

    from llm_orchestrator.pipeline.comparator_pack import (
        ComparatorPack,
        ComparatorPassMetadata,
        CounterexamplePassMetadata,
    )

    fake_pack = ComparatorPack(
        comparators=[],
        counterexamples=[],
        comparator_pass_metadata=ComparatorPassMetadata(
            n_retrieved=0,
            weights_used={},
        ),
        counterexample_pass_metadata=CounterexamplePassMetadata(
            n_retrieved=0,
            k_overlap_min=2,
            abstention_recommended=False,
        ),
    )

    async def fake_build_comparator_pack(self, control_input, *, primary_outcome=None):
        captured_input["control"] = control_input
        captured_input["primary_outcome"] = primary_outcome
        return fake_pack

    with patch(
        "llm_orchestrator.pipeline.factor_retrieval.FactorRetriever.build_comparator_pack",
        new=fake_build_comparator_pack,
    ):
        result = await retriever._retrieve_for_issue(
            issue=issue,
            case_file=case_file,
            top_k=5,
            kg_facts=KGFacts(),
            mode=PredictionMode.HYBRID,
            retrieval_strategy=RetrievalStrategy.FACTOR_CONSTRAINED,
        )

    # FactorRetriever.build_comparator_pack was invoked.
    assert "control" in captured_input
    control = captured_input["control"]
    assert control.domain_id == "housing.repairs_social.v1"
    assert control.claim_head_id == "ho-2024-test"
    # asserted_factors threaded through.
    assert len(control.asserted_factors) == 1
    assert control.asserted_factors[0].factor_id == "repair_responsibility_established"
    # issue id surfaces as the issue_type value.
    assert "repairs_disrepair" in control.issue_ids
    # Forum threaded.
    assert control.forum == "ombudsman"
    # Domain primary outcome.
    assert captured_input["primary_outcome"] == "fault_finding"

    # The empty pack still flows through the conversion helper.
    assert isinstance(result, IssueRetrievalResult)
    assert result.issue_type == issue.issue_type
    # No comparators / counterexamples in this fake pack → not sufficient.
    assert result.is_sufficient is False
    assert result.results == []
    # Chunk-RAG fallback was NOT invoked when FactorRetriever returned a pack.
    assert rag.calls == []


@pytest.mark.asyncio
async def test_factor_constrained_falls_back_when_no_repository():
    """Without a proposition_retriever (and therefore no repository), the
    FACTOR_CONSTRAINED branch returns None and falls through to chunk-RAG."""
    rag = _FakeRAG()
    retriever = IssueRetriever(
        rag_pipeline=rag,
        proposition_retriever=None,  # no repository available
    )

    issue = _make_issue()
    case_file = _FakeCaseFile()
    fa = _make_factor_assertion("repair_responsibility_established")
    retriever._case_graph_by_issue = {
        issue.issue_type: _FakeCaseGraphWithFactors([fa])
    }

    result = await retriever._retrieve_for_issue(
        issue=issue,
        case_file=case_file,
        top_k=5,
        kg_facts=KGFacts(),
        mode=PredictionMode.HYBRID,
        retrieval_strategy=RetrievalStrategy.FACTOR_CONSTRAINED,
    )

    # Fell through to chunk-RAG (no repository → cannot construct retriever).
    assert len(rag.calls) >= 1
    assert isinstance(result, IssueRetrievalResult)


@pytest.mark.asyncio
async def test_factor_constrained_falls_back_when_no_domain_id():
    """When the case_file has no domain_id, _retrieve_via_factor_retriever
    returns None and the FACTOR_CONSTRAINED branch falls back to chunk-RAG."""
    rag = _FakeRAG()
    repo = AsyncMock()
    proposition_retriever = MagicMock()
    proposition_retriever.repository = repo

    retriever = IssueRetriever(
        rag_pipeline=rag,
        proposition_retriever=proposition_retriever,
    )

    issue = _make_issue()
    case_file = _FakeCaseFile(domain_id="")
    case_file.domain_id = None  # type: ignore[assignment]
    retriever._case_graph_by_issue = {
        issue.issue_type: _FakeCaseGraphWithFactors(
            [_make_factor_assertion()]
        )
    }

    result = await retriever._retrieve_for_issue(
        issue=issue,
        case_file=case_file,
        top_k=5,
        kg_facts=KGFacts(),
        mode=PredictionMode.HYBRID,
        retrieval_strategy=RetrievalStrategy.FACTOR_CONSTRAINED,
    )

    # Fell through to chunk-RAG.
    assert len(rag.calls) >= 1
    assert isinstance(result, IssueRetrievalResult)


# ---------------------------------------------------------------------------
# 5. Task 5.6 — abstention warning surfaces in IRAC prompt when recommended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abstention_warning_in_prompt_when_recommended():
    """When ``ComparatorPack.counterexample_pass_metadata.abstention_recommended``
    is True, the IRAC user prompt contains the low-confidence warning.

    Spec §9.3 / Task 5.6: the predictor reads
    ``self._comparator_pack_by_issue`` (populated by the engine after
    retrieval) and emits a warning string into the prompt whenever the
    counterexample pass found no differential cases.
    """
    from llm_orchestrator.models.prediction_v2 import (
        IssueContext,
        IssueRetrievalResult,
        IssueType,
    )
    from llm_orchestrator.pipeline.comparator_pack import (
        ComparatorPack,
        ComparatorPassMetadata,
        CounterexamplePassMetadata,
    )
    from llm_orchestrator.pipeline.issue_predictor import IssuePredictor

    class _DummyLLM:
        async def generate(self, messages, system_prompt, max_tokens, temperature):
            raise AssertionError("LLM.generate must not be invoked here")

    predictor = IssuePredictor(_DummyLLM())

    # Pack with abstention_recommended=True for our issue.
    pack = ComparatorPack(
        comparators=[],
        counterexamples=[],
        comparator_pass_metadata=ComparatorPassMetadata(
            n_retrieved=0,
            weights_used={},
        ),
        counterexample_pass_metadata=CounterexamplePassMetadata(
            n_retrieved=0,
            k_overlap_min=2,
            abstention_recommended=True,
        ),
    )
    predictor._comparator_pack_by_issue = {IssueType.DEPOSIT_PROTECTION: pack}

    # Capture the IRAC prompt.
    captured: list[str] = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured.append(messages[0]["content"])
        # Return a definite (non-uncertain) outcome so the predictor does
        # not retry — we only want to assert against a single prompt.
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.4,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[],'
            '"evidence_strength":"weak","data_completeness_impact":"ok"}'
        )

    predictor.llm.generate = fake_generate  # type: ignore[assignment]

    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="late deposit protection",
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

    await predictor._predict_issue(issue, retrieval, prompt_mode="hybrid")

    assert len(captured) == 1
    prompt = captured[0]
    assert "Counterexample retrieval found no differential cases" in prompt
    assert "low-confidence" in prompt


@pytest.mark.asyncio
async def test_no_abstention_warning_when_flag_false():
    """Sanity check: when abstention_recommended=False, the warning string
    is absent from the IRAC prompt (placeholder resolves to '')."""
    from llm_orchestrator.models.prediction_v2 import (
        IssueContext,
        IssueRetrievalResult,
        IssueType,
    )
    from llm_orchestrator.pipeline.comparator_pack import (
        ComparatorPack,
        ComparatorPassMetadata,
        CounterexamplePassMetadata,
    )
    from llm_orchestrator.pipeline.issue_predictor import IssuePredictor

    class _DummyLLM:
        async def generate(self, messages, system_prompt, max_tokens, temperature):
            raise AssertionError("LLM.generate must not be invoked here")

    predictor = IssuePredictor(_DummyLLM())

    pack = ComparatorPack(
        comparators=[],
        counterexamples=[],
        comparator_pass_metadata=ComparatorPassMetadata(
            n_retrieved=0,
            weights_used={},
        ),
        counterexample_pass_metadata=CounterexamplePassMetadata(
            n_retrieved=2,
            k_overlap_min=2,
            abstention_recommended=False,
        ),
    )
    predictor._comparator_pack_by_issue = {IssueType.DEPOSIT_PROTECTION: pack}

    captured: list[str] = []

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        captured.append(messages[0]["content"])
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[],"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    predictor.llm.generate = fake_generate  # type: ignore[assignment]

    issue = IssueContext(
        issue_type=IssueType.DEPOSIT_PROTECTION,
        issue_description="late deposit protection",
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

    await predictor._predict_issue(issue, retrieval, prompt_mode="hybrid")

    assert len(captured) == 1
    prompt = captured[0]
    assert "Counterexample retrieval found no differential cases" not in prompt
    assert "low-confidence" not in prompt
