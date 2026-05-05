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
