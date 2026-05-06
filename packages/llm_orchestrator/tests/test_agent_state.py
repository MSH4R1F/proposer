"""Tests for the retrieval-agent state model.

Module under test:
``packages/llm_orchestrator/models/agent_state.py``.
"""

from __future__ import annotations

import pytest

from llm_orchestrator.models.agent_state import (
    AgentAction,
    AgentAmount,
    AgentChunk,
    AgentKGFact,
    AgentState,
    PlannedQuery,
    QueryPlan,
)


def _chunk(source_id="ho_1", paragraph_id="p1", text="x", **kw) -> AgentChunk:
    defaults = {
        "chunk_id": f"{source_id}#{paragraph_id}",
        "source_id": source_id,
        "paragraph_id": paragraph_id,
        "text": text,
    }
    defaults.update(kw)
    return AgentChunk(**defaults)


def _state() -> AgentState:
    return AgentState(case_id="ho-202428538", issue_type="repairs_disrepair")


class TestAddChunks:
    def test_first_insert_added(self):
        s = _state()
        added = s.add_chunks([_chunk()])
        assert added == 1
        assert len(s.chunks_so_far) == 1

    def test_dedupe_by_source_paragraph(self):
        s = _state()
        s.add_chunks([_chunk(source_id="A", paragraph_id="1")])
        added = s.add_chunks([_chunk(source_id="A", paragraph_id="1")])
        assert added == 0
        assert len(s.chunks_so_far) == 1

    def test_same_source_different_paragraph_kept(self):
        s = _state()
        s.add_chunks([_chunk(source_id="A", paragraph_id="1")])
        added = s.add_chunks([_chunk(source_id="A", paragraph_id="2")])
        assert added == 1
        assert len(s.chunks_so_far) == 2

    def test_none_paragraph_treated_as_distinct(self):
        s = _state()
        s.add_chunks([_chunk(source_id="A", paragraph_id=None)])
        s.add_chunks([_chunk(source_id="A", paragraph_id="1")])
        # (A, None) and (A, "1") are distinct keys.
        assert len(s.chunks_so_far) == 2

    def test_partial_dedupe_in_one_call(self):
        s = _state()
        s.add_chunks([_chunk(source_id="A", paragraph_id="1")])
        added = s.add_chunks(
            [
                _chunk(source_id="A", paragraph_id="1"),  # dup
                _chunk(source_id="B", paragraph_id="1"),  # new
                _chunk(source_id="B", paragraph_id="1"),  # dup-within-batch
            ]
        )
        assert added == 1
        assert len(s.chunks_so_far) == 2


class TestHasQuery:
    def test_unseen_query(self):
        s = _state()
        assert not s.has_query("liability", "damp mould response timelines")

    def test_seen_query(self):
        s = _state()
        s.queries_so_far.append(("liability", "damp mould response timelines"))
        assert s.has_query("liability", "damp mould response timelines")

    def test_same_text_different_purpose_is_distinct(self):
        s = _state()
        s.queries_so_far.append(("liability", "compensation"))
        # Different purpose = different query key.
        assert not s.has_query("remedy", "compensation")


class TestAgentActionValidation:
    def test_finalize_action_carries_confidence(self):
        a = AgentAction(
            tool="finalize",
            rationale="enough liability + remedy",
            confidence_score=0.82,
        )
        assert a.confidence_score == 0.82

    def test_retrieve_action_input(self):
        a = AgentAction(
            tool="retrieve",
            input={"query": "vulnerability evidence", "purpose": "vulnerability"},
            rationale="need vulnerability marker",
        )
        assert a.input["query"] == "vulnerability evidence"

    def test_unknown_tool_rejected(self):
        with pytest.raises(Exception):
            AgentAction(tool="ransack", rationale="nope")  # type: ignore[arg-type]


class TestQueryPlan:
    def test_empty_plan_serialises(self):
        p = QueryPlan()
        assert p.queries == []
        assert p.decomposer_tokens_in == 0

    def test_planned_query_purpose_validated(self):
        with pytest.raises(Exception):
            PlannedQuery(purpose="not_a_purpose", text="x")  # type: ignore[arg-type]

    def test_planned_query_round_trip(self):
        p = PlannedQuery(
            purpose="remedy",
            text="compensation orders for damp delay",
            rationale="we need the order paragraph specifically",
        )
        assert p.purpose == "remedy"


class TestAgentAmountAndKGFact:
    def test_agent_amount(self):
        a = AgentAmount(
            chunk_id="ho_1#p1",
            paragraph_id="p1",
            amount_gbp=350.0,
            surrounding_sentence="...£350...",
            raw_match="£350",
        )
        assert a.amount_gbp == 350.0

    def test_kg_fact_unknown_default(self):
        f = AgentKGFact(field="vulnerability_flag")
        assert f.is_known is False
        assert f.value is None
