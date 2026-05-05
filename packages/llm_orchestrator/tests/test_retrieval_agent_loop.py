"""Tests for the iterative retrieval agent loop.

Module under test:
``packages/llm_orchestrator/pipeline/retrieval_agent_loop.py``.

Strategy: script the LLM client (planner + judge calls) so each turn
returns a deterministic tool_use block. Use a fake RAG that returns
canned chunks. Verify state transitions, terminators, leakage audit
fields, and tool_choice plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import pytest

from llm_orchestrator.agent_loop.loop import AgentTurnResponse
from llm_orchestrator.agent_loop.trace import TraceTerminationReason
from llm_orchestrator.models.agent_state import (
    AgentState,
    PlannedQuery,
    QueryPlan,
)
from llm_orchestrator.pipeline.query_planner import _EMIT_TOOL_NAME
from llm_orchestrator.pipeline.retrieval_agent_loop import (
    JUDGE_CONFIDENCE_THRESHOLD,
    MAX_ITER,
    run_agent_loop,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _ScriptedClient:
    """Returns ``responses`` in order on each run_agent_turn call.

    First entry is the planner response; subsequent entries are judge
    responses for iters 2, 3, 4. ``call_log`` records the kwargs of
    every call so tests can assert on tool_choice values.
    """

    responses: List[AgentTurnResponse] = field(default_factory=list)
    call_log: List[dict] = field(default_factory=list)
    error_on_call: Optional[Exception] = None
    _idx: int = 0

    async def run_agent_turn(self, **kwargs: Any) -> AgentTurnResponse:
        self.call_log.append(kwargs)
        if self.error_on_call is not None:
            err = self.error_on_call
            self.error_on_call = None  # raise once, then continue
            raise err
        if self._idx >= len(self.responses):
            raise AssertionError(
                f"Scripted client ran out of responses at call "
                f"{self._idx + 1}; tool_choice={kwargs.get('tool_choice')}"
            )
        resp = self.responses[self._idx]
        self._idx += 1
        return resp


@dataclass
class _FakeRAG:
    """Returns scripted chunks per query. ``per_query_results`` maps
    query string -> list of result dicts."""

    per_query_results: dict[str, List[dict]] = field(default_factory=dict)
    default_results: List[dict] = field(default_factory=list)
    calls: List[dict] = field(default_factory=list)

    async def retrieve(
        self, *, query: str, k: int = 5, section_type: Optional[str] = None
    ) -> List[dict]:
        self.calls.append(
            {"query": query, "k": k, "section_type": section_type}
        )
        return list(self.per_query_results.get(query, self.default_results))


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


def _judge_response(
    tool_name: str,
    input_dict: dict,
    *,
    tokens_in: int = 1000,
    tokens_out: int = 60,
) -> AgentTurnResponse:
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
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model_used="claude-sonnet-4-6",
    )


def _chunk(
    chunk_id="ho_1#p1",
    source_id="ho_1",
    paragraph_id="p1",
    text="The landlord shall pay £700 in compensation.",
    section_type="orders",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "paragraph_id": paragraph_id,
        "text": text,
        "section_type": section_type,
        "combined_score": 0.8,
    }


# ---------------------------------------------------------------------------
# Iteration 1: planner runs first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIter1Planner:
    async def test_planner_runs_first_and_seeds_chunks(self):
        client = _ScriptedClient(
            responses=[
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
                            "rationale": "remedy",
                        },
                    ]
                ),
                # Iter 2: finalize with high confidence.
                _judge_response(
                    "finalize",
                    {"reason": "have liability + remedy", "confidence_score": 0.85},
                ),
            ]
        )
        rag = _FakeRAG(
            per_query_results={
                "damp mould response timelines": [_chunk(chunk_id="A#1", source_id="A", paragraph_id="1")],
                "compensation orders for damp": [_chunk(chunk_id="B#2", source_id="B", paragraph_id="2")],
            }
        )
        state = await run_agent_loop(
            llm_client=client,
            rag=rag,
            case_summary="14-month damp",
            issue_type="repairs_damp_mould",
        )
        assert state.iter == 2
        assert state.terminator == TraceTerminationReason.JUDGE_OK.value
        # Both planner queries reached the RAG.
        retrieved_queries = [c["query"] for c in rag.calls]
        assert "damp mould response timelines" in retrieved_queries
        assert "compensation orders for damp" in retrieved_queries
        assert len(state.chunks_so_far) == 2
        assert len(state.queries_so_far) == 2

    async def test_empty_plan_returns_judge_invalid(self):
        client = _ScriptedClient(
            responses=[_planner_response([])]
        )
        rag = _FakeRAG()
        state = await run_agent_loop(
            llm_client=client, rag=rag, case_summary="x", issue_type="x"
        )
        assert state.terminator == TraceTerminationReason.JUDGE_INVALID.value
        # Judge was never called — only the planner.
        assert len(client.call_log) == 1

    async def test_planner_runs_no_chunks_returns_judge_abstain(self):
        # Planner emits queries but the RAG returns nothing for any
        # of them. The agent has no evidence to feed the judge so we
        # short-circuit to judge_abstain.
        client = _ScriptedClient(
            responses=[
                _planner_response(
                    [
                        {
                            "purpose": "remedy",
                            "text": "compensation orders",
                            "rationale": "x",
                        }
                    ]
                )
            ]
        )
        rag = _FakeRAG(default_results=[])
        state = await run_agent_loop(
            llm_client=client, rag=rag, case_summary="x", issue_type="x"
        )
        assert state.terminator == TraceTerminationReason.JUDGE_ABSTAIN.value
        # No judge call ever happened.
        assert len(client.call_log) == 1


# ---------------------------------------------------------------------------
# Termination paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTerminationPaths:
    async def _bootstrap(self, judge_responses: List[AgentTurnResponse]):
        client = _ScriptedClient(
            responses=[
                _planner_response(
                    [{"purpose": "remedy", "text": "compensation orders", "rationale": "x"}]
                ),
                *judge_responses,
            ]
        )
        rag = _FakeRAG(default_results=[_chunk()])
        state = await run_agent_loop(
            llm_client=client,
            rag=rag,
            case_summary="x",
            issue_type="repairs_disrepair",
        )
        return state, client

    async def test_finalize_high_confidence_judge_ok(self):
        state, _ = await self._bootstrap(
            [
                _judge_response(
                    "finalize",
                    {"reason": "ok", "confidence_score": 0.85},
                )
            ]
        )
        assert state.terminator == TraceTerminationReason.JUDGE_OK.value

    async def test_finalize_low_confidence_keeps_iterating(self):
        state, client = await self._bootstrap(
            [
                _judge_response(
                    "finalize",
                    {"reason": "unsure", "confidence_score": 0.40},
                ),
                _judge_response(
                    "finalize",
                    {"reason": "now ok", "confidence_score": 0.90},
                ),
            ]
        )
        # Two judge calls happened (low-conf at iter2, high-conf at iter3).
        assert state.terminator == TraceTerminationReason.JUDGE_OK.value
        # Three total LLM calls (planner + 2 judge).
        assert len(client.call_log) == 3

    async def test_abstain_judge_abstain(self):
        state, _ = await self._bootstrap(
            [
                _judge_response(
                    "abstain",
                    {"reason": "no liability span exists in any retrieved chunk"},
                )
            ]
        )
        assert state.terminator == TraceTerminationReason.JUDGE_ABSTAIN.value

    async def test_max_iter_when_judge_keeps_low_confidence(self):
        # Three low-confidence finalizes — at iter 4 we force finalize
        # via tool_choice; if that's still low-conf, we exit MAX_ITER.
        state, client = await self._bootstrap(
            [
                _judge_response(
                    "finalize",
                    {"reason": "low", "confidence_score": 0.30},
                ),
                _judge_response(
                    "finalize",
                    {"reason": "low", "confidence_score": 0.30},
                ),
                _judge_response(
                    "finalize",
                    {"reason": "still low", "confidence_score": 0.30},
                ),
            ]
        )
        assert state.terminator == TraceTerminationReason.MAX_ITER.value
        # Planner + 3 judge calls (iters 2, 3, 4 = MAX_ITER).
        assert len(client.call_log) == 4

    async def test_dup_query_yields_judge_invalid(self):
        # Issuing the same (purpose, query) twice should be caught by
        # the dedup guard in retrieve(). One dispatch error + one more
        # = JUDGE_INVALID after MAX_INVALID_TOOL_NAMES.
        state, client = await self._bootstrap(
            [
                _judge_response(
                    "retrieve",
                    {"query": "compensation orders", "purpose": "remedy"},
                ),
                _judge_response(
                    "retrieve",
                    {"query": "compensation orders", "purpose": "remedy"},
                ),
            ]
        )
        assert state.terminator == TraceTerminationReason.JUDGE_INVALID.value


# ---------------------------------------------------------------------------
# tool_choice plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolChoicePlumbing:
    async def test_force_finalize_at_max_iter(self):
        # Run to MAX_ITER so we can verify the tool_choice on the
        # final judge call is the forced-finalize shape.
        client = _ScriptedClient(
            responses=[
                _planner_response(
                    [{"purpose": "remedy", "text": "compensation orders", "rationale": "x"}]
                ),
                # iters 2, 3: low-conf finalize, keep going
                _judge_response(
                    "finalize",
                    {"reason": "low", "confidence_score": 0.40},
                ),
                _judge_response(
                    "finalize",
                    {"reason": "low", "confidence_score": 0.40},
                ),
                # iter 4 = MAX_ITER: forced finalize, model emits high conf
                _judge_response(
                    "finalize",
                    {"reason": "ok", "confidence_score": 0.95},
                ),
            ]
        )
        rag = _FakeRAG(default_results=[_chunk()])
        await run_agent_loop(
            llm_client=client, rag=rag, case_summary="x", issue_type="x"
        )
        # Planner is call_log[0]; judge calls are 1, 2, 3.
        assert client.call_log[1]["tool_choice"] == {
            "type": "any",
            "disable_parallel_tool_use": True,
        }
        assert client.call_log[2]["tool_choice"] == {
            "type": "any",
            "disable_parallel_tool_use": True,
        }
        # Final iter: forced finalize.
        assert client.call_log[3]["tool_choice"] == {
            "type": "tool",
            "name": "finalize",
        }

    async def test_planner_uses_forced_emit(self):
        client = _ScriptedClient(
            responses=[
                _planner_response(
                    [{"purpose": "remedy", "text": "x is fine", "rationale": "x"}]
                ),
                _judge_response(
                    "finalize",
                    {"reason": "ok", "confidence_score": 0.85},
                ),
            ]
        )
        rag = _FakeRAG(default_results=[_chunk()])
        await run_agent_loop(
            llm_client=client, rag=rag, case_summary="x", issue_type="x"
        )
        # First call (planner) forces emit_query_plan.
        assert client.call_log[0]["tool_choice"] == {
            "type": "tool",
            "name": _EMIT_TOOL_NAME,
        }


# ---------------------------------------------------------------------------
# Leakage audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLeakageAudit:
    async def test_blocked_query_recorded(self):
        # Judge tries to issue a query containing an outcome phrase.
        # The dispatch fails; we record the blocked entry and the
        # streak increments.
        client = _ScriptedClient(
            responses=[
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
                    "retrieve",
                    {
                        "query": "compensation £500 awarded cases",
                        "purpose": "remedy",
                    },
                ),
                _judge_response(
                    "finalize",
                    {"reason": "ok now", "confidence_score": 0.85},
                ),
            ]
        )
        rag = _FakeRAG(default_results=[_chunk()])
        state = await run_agent_loop(
            llm_client=client,
            rag=rag,
            case_summary="x",
            issue_type="x",
            gold_case_id="ho-1",
        )
        assert state.terminator == TraceTerminationReason.JUDGE_OK.value
        # The blocked query is logged for the audit trail.
        assert len(state.blocked_queries) == 1
        assert state.blocked_queries[0]["query"] == "compensation £500 awarded cases"


# ---------------------------------------------------------------------------
# Token cap short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCaps:
    async def test_token_cap_stops_loop(self):
        # Pre-load the planner response with absurd token usage so the
        # cap fires after iter 1.
        client = _ScriptedClient(
            responses=[
                AgentTurnResponse(
                    content_blocks=[
                        {
                            "type": "tool_use",
                            "id": "p",
                            "name": _EMIT_TOOL_NAME,
                            "input": {
                                "queries": [
                                    {
                                        "purpose": "remedy",
                                        "text": "compensation orders",
                                        "rationale": "x",
                                    }
                                ]
                            },
                        }
                    ],
                    stop_reason="tool_use",
                    tokens_in=10_000,
                    tokens_out=0,
                    model_used="claude-sonnet-4-6",
                )
            ]
        )
        rag = _FakeRAG(default_results=[_chunk()])
        state = await run_agent_loop(
            llm_client=client, rag=rag, case_summary="x", issue_type="x"
        )
        # Planner ran (iter=1), token cap fires before judge runs.
        assert state.terminator == TraceTerminationReason.TOKEN_CAP.value


# ---------------------------------------------------------------------------
# Sanity on AgentState
# ---------------------------------------------------------------------------


class TestStateInvariants:
    def test_constants_match_spec(self):
        # Sanity: if MAX_ITER changes, tests need to revalidate.
        assert MAX_ITER == 4
        assert JUDGE_CONFIDENCE_THRESHOLD == 0.70
