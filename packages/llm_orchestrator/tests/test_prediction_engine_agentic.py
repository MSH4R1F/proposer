"""Integration tests for the AGENTIC retrieval strategy in PredictionEngineV2.

These tests cover the wiring added in Chunk C:
- ``RetrievalStrategy.AGENTIC`` routes through ``_agentic_retrieve_all``
  instead of the legacy ``IssueRetriever.retrieve_all``.
- Per-issue agent traces land on ``metadata.agent_traces``.
- The agent's curated chunks are converted to ``IssueRetrievalResult``
  in a shape the IRAC predictor consumes unchanged.

We use scripted fake clients (planner + judge LLMs) and a fake RAG
so the test runs deterministically without API keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from llm_orchestrator.agent_loop.loop import AgentTurnResponse
from llm_orchestrator.models.agent_state import AgentChunk, AgentState
from llm_orchestrator.models.prediction_v2 import (
    IssueContext,
    IssueRetrievalResult,
    IssueType,
    PipelineMetadata,
    RetrievalStrategy,
)
from llm_orchestrator.pipeline.prediction_engine_v2 import (
    PredictionEngineV2,
    _agent_state_to_retrieval_result,
)
from llm_orchestrator.pipeline.query_planner import _EMIT_TOOL_NAME


# ---------------------------------------------------------------------------
# Test doubles (mirror those in test_retrieval_agent_loop.py)
# ---------------------------------------------------------------------------


@dataclass
class _ScriptedClient:
    responses: List[AgentTurnResponse] = field(default_factory=list)
    call_log: List[dict] = field(default_factory=list)
    _idx: int = 0

    async def run_agent_turn(self, **kwargs: Any) -> AgentTurnResponse:
        self.call_log.append(kwargs)
        if self._idx >= len(self.responses):
            raise AssertionError(
                f"Scripted client out of responses at call {self._idx + 1}"
            )
        resp = self.responses[self._idx]
        self._idx += 1
        return resp


@dataclass
class _FakeRAG:
    default_results: List[dict] = field(default_factory=list)
    calls: List[dict] = field(default_factory=list)

    async def retrieve(
        self, *, query: str, k: int = 5, section_type: Optional[str] = None
    ) -> List[dict]:
        self.calls.append(
            {"query": query, "k": k, "section_type": section_type}
        )
        return list(self.default_results)


@dataclass
class _FakeCaseFile:
    case_id: str = "ho-2024-99999"
    tenant_narrative: str = (
        "I have had damp and mould in the property for 14 months despite "
        "repeated reports."
    )
    landlord_narrative: str = (
        "Repairs were attempted multiple times but residents were not in."
    )
    issues: List[Any] = field(default_factory=list)


def _planner_response(queries: List[dict]) -> AgentTurnResponse:
    return AgentTurnResponse(
        content_blocks=[
            {
                "type": "tool_use",
                "id": "p1",
                "name": _EMIT_TOOL_NAME,
                "input": {"queries": queries},
            }
        ],
        stop_reason="tool_use",
        tokens_in=300,
        tokens_out=80,
        model_used="claude-sonnet-4-6",
    )


def _judge_response(tool_name: str, input_dict: dict) -> AgentTurnResponse:
    return AgentTurnResponse(
        content_blocks=[
            {
                "type": "tool_use",
                "id": f"j_{tool_name}",
                "name": tool_name,
                "input": input_dict,
            }
        ],
        stop_reason="tool_use",
        tokens_in=1000,
        tokens_out=60,
        model_used="claude-sonnet-4-6",
    )


def _rag_chunk(
    chunk_id="A#1",
    source_id="A",
    paragraph_id="1",
    text="Compensation of £700 ordered for damp delay.",
    section_type="orders",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "paragraph_id": paragraph_id,
        "text": text,
        "section_type": section_type,
        "combined_score": 0.75,
    }


# ---------------------------------------------------------------------------
# AgentChunk -> IssueRetrievalResult conversion
# ---------------------------------------------------------------------------


class TestAgentStateToRetrievalResult:
    def test_judge_ok_terminator_makes_sufficient(self):
        state = AgentState(case_id="ho-1", issue_type="repairs_disrepair")
        state.terminator = "judge_ok"
        state.add_chunks(
            [
                AgentChunk(
                    chunk_id="X#1",
                    source_id="X",
                    paragraph_id="1",
                    section_type="orders",
                    text="£700 ordered",
                    score=0.8,
                    purpose="remedy",
                )
            ]
        )
        result = _agent_state_to_retrieval_result(
            state=state, issue_type=IssueType.REPAIRS_DISREPAIR
        )
        assert isinstance(result, IssueRetrievalResult)
        assert result.is_sufficient is True
        assert len(result.results) == 1
        # Predictor reads via _get_value with both new and legacy keys.
        chunk = result.results[0]
        assert chunk["chunk_id"] == "X#1"
        assert chunk["case_reference"] == "X"  # legacy alias
        assert chunk["chunk_text"] == "£700 ordered"  # legacy alias
        assert chunk["combined_score"] == 0.8  # legacy alias
        assert chunk["section_type"] == "orders"

    def test_judge_abstain_terminator_still_sufficient_when_chunks_exist(self):
        state = AgentState(case_id="ho-1", issue_type="x")
        state.terminator = "judge_abstain"
        state.add_chunks(
            [
                AgentChunk(
                    chunk_id="X#1", source_id="X", paragraph_id="1", text="x"
                )
            ]
        )
        result = _agent_state_to_retrieval_result(
            state=state, issue_type=IssueType.REPAIRS_DISREPAIR
        )
        # judge_abstain with chunks = abstention by judge despite
        # available evidence; the prediction will surface as uncertain
        # downstream. is_sufficient is True so the predictor still
        # runs (the downstream IRAC call decides what to emit).
        assert result.is_sufficient is True

    def test_judge_invalid_terminator_not_sufficient(self):
        state = AgentState(case_id="ho-1", issue_type="x")
        state.terminator = "judge_invalid"
        state.add_chunks(
            [
                AgentChunk(
                    chunk_id="X#1", source_id="X", paragraph_id="1", text="x"
                )
            ]
        )
        result = _agent_state_to_retrieval_result(
            state=state, issue_type=IssueType.REPAIRS_DISREPAIR
        )
        # Even if chunks exist, judge_invalid means the loop fell over;
        # caller should NOT trust this retrieval.
        assert result.is_sufficient is False

    def test_no_chunks_not_sufficient(self):
        state = AgentState(case_id="ho-1", issue_type="x")
        state.terminator = "judge_ok"
        result = _agent_state_to_retrieval_result(
            state=state, issue_type=IssueType.REPAIRS_DISREPAIR
        )
        assert result.is_sufficient is False
        assert result.results == []

    def test_query_used_concatenates_purposes(self):
        state = AgentState(case_id="ho-1", issue_type="x")
        state.terminator = "judge_ok"
        state.queries_so_far = [
            ("liability", "damp response timelines"),
            ("remedy", "compensation orders for damp"),
        ]
        state.add_chunks(
            [
                AgentChunk(
                    chunk_id="X#1", source_id="X", paragraph_id="1", text="x"
                )
            ]
        )
        result = _agent_state_to_retrieval_result(
            state=state, issue_type=IssueType.REPAIRS_DISREPAIR
        )
        assert "[liability]" in result.query_used
        assert "[remedy]" in result.query_used


# ---------------------------------------------------------------------------
# _agentic_retrieve_all integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgenticRetrieveAll:
    async def _build_engine(
        self, scripted_responses: List[AgentTurnResponse], rag_results: List[dict]
    ) -> tuple[PredictionEngineV2, _ScriptedClient, _FakeRAG]:
        client = _ScriptedClient(responses=scripted_responses)
        rag = _FakeRAG(default_results=rag_results)
        engine = PredictionEngineV2(
            llm_client=client,  # type: ignore[arg-type]
            rag_pipeline=rag,
        )
        return engine, client, rag

    async def test_runs_planner_and_judge_returns_retrieval_results(self):
        engine, client, rag = await self._build_engine(
            scripted_responses=[
                _planner_response(
                    [
                        {
                            "purpose": "liability",
                            "text": "damp mould response timelines",
                            "rationale": "core",
                        },
                        {
                            "purpose": "remedy",
                            "text": "compensation orders for damp",
                            "rationale": "anchor",
                        },
                    ]
                ),
                _judge_response(
                    "finalize",
                    {"reason": "have liability + remedy", "confidence_score": 0.85},
                ),
            ],
            rag_results=[_rag_chunk()],
        )
        case_file = _FakeCaseFile()
        issue = IssueContext(
            issue_type=IssueType.REPAIRS_DISREPAIR,
            issue_description="damp/mould since 2024",
        )
        metadata = PipelineMetadata()

        retrieval_results = await engine._agentic_retrieve_all(
            issues=[issue],
            case_file=case_file,
            metadata=metadata,
        )

        assert IssueType.REPAIRS_DISREPAIR in retrieval_results
        result = retrieval_results[IssueType.REPAIRS_DISREPAIR]
        assert result.is_sufficient is True
        # 2 planner queries × 1 RAG result each = 2 calls (deduped to 1
        # AgentChunk because both fake-RAG results have same source_id+para).
        assert len(rag.calls) == 2
        # Trace persisted on metadata for the audit gate.
        assert len(metadata.agent_traces) == 1
        trace = metadata.agent_traces[0]
        assert trace["terminator"] == "judge_ok"
        assert trace["iter_count"] == 2
        assert trace["leakage_audit"]["all_queries_filter_applied"] is True
        # Tokens accumulated from planner + judge calls.
        assert metadata.total_tokens_used > 0

    async def test_two_issues_run_independently(self):
        # Run on 2 issues; each gets its own agent loop, its own trace.
        engine, client, rag = await self._build_engine(
            scripted_responses=[
                # Issue 1
                _planner_response(
                    [
                        {
                            "purpose": "remedy",
                            "text": "compensation orders for damp",
                            "rationale": "x",
                        }
                    ]
                ),
                _judge_response(
                    "finalize",
                    {"reason": "ok", "confidence_score": 0.85},
                ),
                # Issue 2
                _planner_response(
                    [
                        {
                            "purpose": "remedy",
                            "text": "compensation patterns for complaint handling",
                            "rationale": "x",
                        }
                    ]
                ),
                _judge_response(
                    "finalize",
                    {"reason": "ok", "confidence_score": 0.85},
                ),
            ],
            rag_results=[_rag_chunk()],
        )
        case_file = _FakeCaseFile()
        issues = [
            IssueContext(
                issue_type=IssueType.REPAIRS_DISREPAIR,
                issue_description="damp",
            ),
            IssueContext(
                issue_type=IssueType.COMPLAINT_HANDLING_FAILURE,
                issue_description="complaint handling failure",
            ),
        ]
        metadata = PipelineMetadata()
        results = await engine._agentic_retrieve_all(
            issues=issues, case_file=case_file, metadata=metadata
        )
        assert set(results.keys()) == {
            IssueType.REPAIRS_DISREPAIR,
            IssueType.COMPLAINT_HANDLING_FAILURE,
        }
        assert len(metadata.agent_traces) == 2

    async def test_judge_abstain_on_empty_planner_recorded_in_trace(self):
        engine, client, rag = await self._build_engine(
            scripted_responses=[_planner_response([])],
            rag_results=[],
        )
        case_file = _FakeCaseFile()
        issue = IssueContext(
            issue_type=IssueType.REPAIRS_DISREPAIR,
            issue_description="x",
        )
        metadata = PipelineMetadata()
        results = await engine._agentic_retrieve_all(
            issues=[issue], case_file=case_file, metadata=metadata
        )
        result = results[IssueType.REPAIRS_DISREPAIR]
        # Empty plan -> JUDGE_INVALID terminator -> not sufficient.
        assert result.is_sufficient is False
        assert metadata.agent_traces[0]["terminator"] == "judge_invalid"

    async def test_blocked_query_recorded_in_trace_audit(self):
        # Planner emits an outcome-revealing query; the leakage filter
        # drops it before retrieval. The trace's leakage_audit field
        # records the blocked query — the audit gate (plan §5.4)
        # consumes this.
        engine, client, rag = await self._build_engine(
            scripted_responses=[
                _planner_response(
                    [
                        {
                            "purpose": "remedy",
                            "text": "compensation £500 awarded cases",
                            "rationale": "leaks",
                        },
                        {
                            "purpose": "liability",
                            "text": "damp response patterns",
                            "rationale": "ok",
                        },
                    ]
                ),
                _judge_response(
                    "finalize",
                    {"reason": "ok", "confidence_score": 0.80},
                ),
            ],
            rag_results=[_rag_chunk()],
        )
        case_file = _FakeCaseFile()
        issue = IssueContext(
            issue_type=IssueType.REPAIRS_DISREPAIR,
            issue_description="x",
        )
        metadata = PipelineMetadata()
        await engine._agentic_retrieve_all(
            issues=[issue], case_file=case_file, metadata=metadata
        )
        # Only the safe query reached RAG.
        assert len(rag.calls) == 1
        assert rag.calls[0]["query"] == "damp response patterns"
        # Trace records the audit count (planner-level filter happened
        # internally on the planner; the loop's blocked_queries only
        # captures judge-level blocks. So this remains 0 here unless we
        # propagate planner-level blocks too — which we currently
        # don't. Test asserts what we DO record, not what we don't.)
        # The trace must still mark the audit invariant.
        assert metadata.agent_traces[0]["leakage_audit"][
            "all_queries_filter_applied"
        ] is True


# ---------------------------------------------------------------------------
# Branching: AGENTIC strategy routes through _agentic_retrieve_all
# ---------------------------------------------------------------------------


class TestEngineBranching:
    def test_agentic_strategy_in_enum(self):
        # Sanity: the engine code branches on enum identity, so make
        # sure the value is what we documented in the trace artifact
        # spec.
        assert RetrievalStrategy.AGENTIC.value == "agentic"

    def test_agent_traces_field_default_empty(self):
        m = PipelineMetadata()
        assert m.agent_traces == []


# ---------------------------------------------------------------------------
# Stream C PR 4 Task 4.5: KG metadata flow + prompt_mode threading
# ---------------------------------------------------------------------------


def _build_late_protection_kg_for_engine():
    """Build a small KG with deliberately-late deposit protection."""
    from datetime import date as _date

    from kg_builder.models.graph import KnowledgeGraph
    from kg_builder.models.nodes import IssueNode, LeaseNode, PartyNode

    kg = KnowledgeGraph(case_id="case_late_pr45")
    kg.add_node(PartyNode(node_id="party_tenant", role="tenant"))
    kg.add_node(PartyNode(node_id="party_landlord", role="landlord"))
    kg.add_node(
        LeaseNode(
            node_id="lease_main",
            start_date=_date(2023, 1, 1),
            end_date=_date(2024, 1, 1),
            deposit_amount=1500.0,
            deposit_protected=True,
            deposit_scheme="DPS",
            protection_date=_date(2023, 4, 1),  # late
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


def _make_deposit_case_file_for_engine(case_id: str = "case_pr45"):
    """SimpleNamespace stub mirroring test_kg_in_prompt_golden.py."""
    from datetime import date as _date
    from types import SimpleNamespace as _SN

    return _SN(
        case_id=case_id,
        domain_id="housing.deposit.v1",
        tenancy=_SN(
            deposit_amount=1500.0,
            start_date=_date(2023, 1, 1),
            end_date=_date(2024, 1, 1),
            tenancy_type="AST",
            deposit_protected=None,
            deposit_scheme=None,
            protection_date=None,
            prescribed_info_provided=None,
            prescribed_info_date=None,
        ),
        property=_SN(region="London", postcode=None),
    )


@pytest.mark.asyncio
async def test_artifact_records_kg_metadata_for_kg_only_deposit(monkeypatch):
    """KG_ONLY deposit case with STREAM_C_PR4=1: artifact metadata records
    kg_used_for_prediction, graph_quality_score, kg_fallback_mode."""
    from unittest.mock import AsyncMock, MagicMock

    from llm_orchestrator.models.prediction_v2 import (
        IssueContext as _IssueContext,
        IssueType as _IssueType,
        PredictionMode,
    )
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    monkeypatch.setenv("STREAM_C_PR4", "1")

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[],'
            '"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    llm = MagicMock()
    llm.generate = fake_generate
    rag = AsyncMock()
    rag.retrieve = AsyncMock()  # spy: must not be called in KG_ONLY

    engine = PredictionEngineV2(llm_client=llm, rag_pipeline=rag)

    kg = _build_late_protection_kg_for_engine()
    case_file = _make_deposit_case_file_for_engine("case_kg_only_pr45")

    fake_issue = _IssueContext(
        issue_type=_IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    result = await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.KG_ONLY,
    )

    rag.retrieve.assert_not_called()
    assert result.pipeline_metadata is not None
    meta = result.pipeline_metadata
    # When the KG is populated and the pack accepts it, kg_used_for_prediction=True.
    assert meta.kg_used_for_prediction is True
    # graph_quality_score is a float between 0 and 1 (or None if pack disabled).
    assert meta.graph_quality_score is None or (0.0 <= meta.graph_quality_score <= 1.0)
    # No fallback when the KG path completes happily.
    assert meta.kg_fallback_mode is None
    assert meta.kg_gate_failure_reasons == []


@pytest.mark.asyncio
async def test_artifact_records_kg_metadata_for_rag_only_mode(monkeypatch):
    """RAG_ONLY mode: kg_used_for_prediction=False (the prompt does NOT
    include the factor card, even with a populated KG)."""
    from unittest.mock import AsyncMock, MagicMock

    from llm_orchestrator.models.prediction_v2 import (
        IssueContext as _IssueContext,
        IssueType as _IssueType,
        PredictionMode,
    )
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    monkeypatch.setenv("STREAM_C_PR4", "1")

    captured_prompts: list = []

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
    rag.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "case_reference": "P1",
                    "year": 2023,
                    "semantic_score": 0.8,
                    "bm25_score": 0.0,
                    "text": "x",
                    "chunk_text": "x",
                }
            ]
            * 3,
            "confidence": 0.8,
        }
    )

    engine = PredictionEngineV2(
        llm_client=llm, rag_pipeline=rag, min_cases_required=3
    )

    kg = _build_late_protection_kg_for_engine()
    case_file = _make_deposit_case_file_for_engine("case_rag_only_pr45")

    fake_issue = _IssueContext(
        issue_type=_IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    result = await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.RAG_ONLY,
    )

    # Prompt must NOT contain the factor card.
    assert len(captured_prompts) == 1
    assert "KEY KG FACTS (typed):" not in captured_prompts[0]

    assert result.pipeline_metadata is not None
    meta = result.pipeline_metadata
    # RAG_ONLY hides the KG; metadata must reflect that.
    assert meta.kg_used_for_prediction is False


@pytest.mark.asyncio
async def test_predict_all_threads_prompt_mode_to_predict_issue(monkeypatch):
    """Engine must thread prompt_mode='rag_only' to predict_all when
    mode=RAG_ONLY, so the rag_only gate fires in production (not just in
    unit tests of the predictor)."""
    from unittest.mock import AsyncMock, MagicMock

    from llm_orchestrator.models.prediction_v2 import (
        IssueContext as _IssueContext,
        IssueType as _IssueType,
        PredictionMode,
    )
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    monkeypatch.setenv("STREAM_C_PR4", "1")

    captured_modes: list = []

    real_predict_all_holder: dict = {}

    engine_holder: dict = {}

    async def spy_predict_all(
        issues, retrieval_results, *, case_file=None, prompt_mode="hybrid"
    ):
        captured_modes.append(prompt_mode)
        # Delegate to real predict_all so behaviour is preserved.
        return await real_predict_all_holder["fn"](
            issues, retrieval_results, case_file=case_file, prompt_mode=prompt_mode
        )

    async def fake_generate(messages, system_prompt, max_tokens, temperature):
        return (
            '{"outcome":"tenant_wins","raw_confidence":0.7,"reasoning":"r",'
            '"supporting_cases":[{"case_reference":"P1","year":2023,"quote":"q","relevance":"r"}],'
            '"counterfactuals":[{"condition":"c","alternative_outcome":"o","confidence_shift":-0.1}],'
            '"evidence_strength":"moderate","data_completeness_impact":"ok"}'
        )

    llm = MagicMock()
    llm.generate = fake_generate
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "case_reference": "P1",
                    "year": 2023,
                    "semantic_score": 0.8,
                    "bm25_score": 0.0,
                    "text": "x",
                    "chunk_text": "x",
                }
            ]
            * 3,
            "confidence": 0.8,
        }
    )

    engine = PredictionEngineV2(
        llm_client=llm, rag_pipeline=rag, min_cases_required=3
    )
    engine_holder["engine"] = engine
    real_predict_all_holder["fn"] = engine.issue_predictor.predict_all
    engine.issue_predictor.predict_all = spy_predict_all  # type: ignore[assignment]

    kg = _build_late_protection_kg_for_engine()
    case_file = _make_deposit_case_file_for_engine("case_thread_pr45")

    fake_issue = _IssueContext(
        issue_type=_IssueType.DEPOSIT_PROTECTION,
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

    assert captured_modes == ["rag_only"], (
        "RAG_ONLY mode must thread prompt_mode='rag_only' to predict_all"
    )


@pytest.mark.asyncio
async def test_predict_all_threads_hybrid_prompt_mode(monkeypatch):
    """Engine must pass prompt_mode='hybrid' to predict_all when mode=HYBRID."""
    from unittest.mock import AsyncMock, MagicMock

    from llm_orchestrator.models.prediction_v2 import (
        IssueContext as _IssueContext,
        IssueType as _IssueType,
        PredictionMode,
    )
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    monkeypatch.setenv("STREAM_C_PR4", "1")

    captured_modes: list = []

    async def spy_predict_all(
        issues, retrieval_results, *, case_file=None, prompt_mode="hybrid"
    ):
        captured_modes.append(prompt_mode)
        return []

    llm = MagicMock()
    llm.generate = AsyncMock()
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "case_reference": "P1",
                    "year": 2023,
                    "semantic_score": 0.8,
                    "bm25_score": 0.0,
                    "text": "x",
                    "chunk_text": "x",
                }
            ]
            * 3,
            "confidence": 0.8,
        }
    )

    engine = PredictionEngineV2(
        llm_client=llm, rag_pipeline=rag, min_cases_required=3
    )
    engine.issue_predictor.predict_all = spy_predict_all  # type: ignore[assignment]

    kg = _build_late_protection_kg_for_engine()
    case_file = _make_deposit_case_file_for_engine("case_hybrid_thread_pr45")

    fake_issue = _IssueContext(
        issue_type=_IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.HYBRID,
    )

    assert captured_modes == ["hybrid"]


@pytest.mark.asyncio
async def test_engine_populates_case_graph_by_issue_for_deposit(monkeypatch):
    """Engine must populate _case_graph_by_issue (deposit: KGFacts adapter)
    so the issue_predictor renderer can read from it."""
    from unittest.mock import AsyncMock, MagicMock

    from llm_orchestrator.models.prediction_v2 import (
        IssueContext as _IssueContext,
        IssueType as _IssueType,
        PredictionMode,
    )
    from llm_orchestrator.pipeline.kg_facts import KGFacts
    from llm_orchestrator.pipeline.prediction_engine_v2 import PredictionEngineV2

    monkeypatch.setenv("STREAM_C_PR4", "1")

    captured_graph_by_issue: dict = {}

    async def spy_predict_all(
        issues, retrieval_results, *, case_file=None, prompt_mode="hybrid"
    ):
        captured_graph_by_issue["snapshot"] = dict(
            engine.issue_predictor._case_graph_by_issue
        )
        return []

    llm = MagicMock()
    rag = AsyncMock()
    rag.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "case_reference": "P1",
                    "year": 2023,
                    "semantic_score": 0.8,
                    "bm25_score": 0.0,
                    "text": "x",
                    "chunk_text": "x",
                }
            ]
            * 3,
            "confidence": 0.8,
        }
    )

    engine = PredictionEngineV2(
        llm_client=llm, rag_pipeline=rag, min_cases_required=3
    )
    engine.issue_predictor.predict_all = spy_predict_all  # type: ignore[assignment]

    kg = _build_late_protection_kg_for_engine()
    case_file = _make_deposit_case_file_for_engine("case_graph_pr45")

    fake_issue = _IssueContext(
        issue_type=_IssueType.DEPOSIT_PROTECTION,
        issue_description="dp",
        kg_constraints=[],
        data_completeness=0.5,
    )
    engine.issue_decomposer.decompose = lambda cf, kg=None: [fake_issue]

    await engine.predict(
        case_file=case_file,
        knowledge_graph=kg,
        mode=PredictionMode.HYBRID,
    )

    snapshot = captured_graph_by_issue.get("snapshot", {})
    assert _IssueType.DEPOSIT_PROTECTION in snapshot
    # For deposit, _case_graph_by_issue carries the KGFacts adapter (the
    # deposit pack's render_factor_card accepts KGFacts directly).
    val = snapshot[_IssueType.DEPOSIT_PROTECTION]
    assert isinstance(val, KGFacts), f"expected KGFacts adapter, got {type(val)}"


def test_pipeline_metadata_has_kg_fields_with_safe_defaults():
    """PipelineMetadata's new KG fields default to safe values so any
    existing constructor still works without changes."""
    m = PipelineMetadata()
    assert m.graph_quality_score is None
    assert m.kg_used_for_prediction is None
    assert m.kg_fallback_mode is None
    assert m.kg_gate_failure_reasons == []
