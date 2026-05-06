"""Tests for the retrieval-agent tool definitions and leakage guards.

Module under test:
``packages/llm_orchestrator/pipeline/retrieval_agent_tools.py``.
"""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from llm_orchestrator.models.agent_state import AgentChunk, AgentState
from llm_orchestrator.pipeline.retrieval_agent_tools import (
    FORBIDDEN_PATTERNS,
    RetrievalToolContext,
    ToolDispatchError,
    abstain,
    assert_query_safe,
    build_retrieval_toolset,
    check_kg_fact,
    extract_amounts,
    finalize,
    retrieve,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _FakeRAG:
    """In-memory RAG stand-in. Records every retrieve call so tests
    can assert on the keyword args (envelope-inheritance proxy)."""

    def __init__(self, results: List[Any]) -> None:
        self.results = results
        self.calls: List[dict[str, Any]] = []

    async def retrieve(self, *, query: str, k: int = 5, section_type=None) -> List[Any]:
        self.calls.append(
            {"query": query, "k": k, "section_type": section_type}
        )
        return list(self.results)


def _state(case_id="ho-1", issue_type="repairs_disrepair") -> AgentState:
    return AgentState(case_id=case_id, issue_type=issue_type)


def _ctx(
    *,
    state: Optional[AgentState] = None,
    rag: Any = None,
    kg: Any = None,
    gold_case_id: str = "ho-1",
) -> RetrievalToolContext:
    return RetrievalToolContext(
        rag=rag,
        kg=kg,
        agent_state=state or _state(),
        gold_case_id=gold_case_id,
    )


def _result_chunk(
    chunk_id="ho_1#p1",
    source_id="ho_1",
    paragraph_id="p1",
    text="Compensation of £700 ordered.",
    section_type="orders",
    score=0.8,
) -> dict[str, Any]:
    """Shape a fake RAG result the way real DocumentChunk-like objects
    are accessed by the adapter (``_to_agent_chunk``)."""
    return {
        "chunk_id": chunk_id,
        "source_id": source_id,
        "paragraph_id": paragraph_id,
        "text": text,
        "section_type": section_type,
        "combined_score": score,
    }


# ---------------------------------------------------------------------------
# assert_query_safe
# ---------------------------------------------------------------------------


class TestAssertQuerySafe:
    def test_neutral_query_allowed(self):
        assert_query_safe("damp mould response timelines", "ho-1")

    def test_self_reference_blocked(self):
        with pytest.raises(ToolDispatchError, match="under analysis"):
            assert_query_safe("how was ho-1 decided", "ho-1")

    def test_self_reference_case_insensitive(self):
        with pytest.raises(ToolDispatchError):
            assert_query_safe("the case HO-1 outcomes", "ho-1")

    def test_empty_gold_case_id_skips_self_ref(self):
        # Test fixtures sometimes don't have a real case_id.
        assert_query_safe("ho-1 patterns", "")

    @pytest.mark.parametrize(
        "bad_query",
        [
            "tenant wins compensation",
            "tenant\twin",
            "landlord win cases",
            "compensation £500",
            "awarded £700",
            "maladministration found",
            "severe maladministration found",
            "service failure upheld",
            "Service Failure Upheld",
        ],
    )
    def test_outcome_phrase_blocked(self, bad_query: str):
        with pytest.raises(ToolDispatchError, match="outcome-revealing"):
            assert_query_safe(bad_query, "")

    def test_phrase_substring_doesnt_falsely_block(self):
        # "compensation amount" without £ should be allowed — agents
        # genuinely need to ask about compensation patterns.
        assert_query_safe("compensation amount patterns for damp", "")

    def test_all_forbidden_patterns_have_unique_messages(self):
        # Sanity: every forbidden pattern is unique. Catches accidental
        # duplicates if someone copy-pastes.
        seen = set()
        for p in FORBIDDEN_PATTERNS:
            assert p.pattern not in seen
            seen.add(p.pattern)


# ---------------------------------------------------------------------------
# retrieve tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetrieveTool:
    async def test_returns_chunks_and_updates_state(self):
        rag = _FakeRAG([_result_chunk()])
        state = _state()
        ctx = _ctx(state=state, rag=rag)
        result = await retrieve.dispatch(
            ctx,
            {"query": "damp mould response", "purpose": "liability"},
        )
        assert not result.is_error
        assert result.model_payload["added_chunks"] == 1
        assert len(state.chunks_so_far) == 1
        assert state.queries_so_far == [("liability", "damp mould response")]
        assert rag.calls == [
            {
                "query": "damp mould response",
                "k": 5,
                "section_type": None,
            }
        ]

    async def test_rejects_outcome_phrase_query(self):
        rag = _FakeRAG([_result_chunk()])
        state = _state()
        ctx = _ctx(state=state, rag=rag)
        result = await retrieve.dispatch(
            ctx,
            {
                "query": "compensation £500 cases",
                "purpose": "remedy",
            },
        )
        assert result.is_error
        # Blocked queries must be logged for the trace audit gate.
        assert state.blocked_queries == [
            {
                "purpose": "remedy",
                "query": "compensation £500 cases",
                "iter": state.iter,
            }
        ]
        # No RAG call must have happened — the guard is BEFORE retrieve.
        assert rag.calls == []
        # State is unchanged on rejection.
        assert state.chunks_so_far == []
        assert state.queries_so_far == []

    async def test_rejects_self_reference(self):
        rag = _FakeRAG([_result_chunk()])
        state = _state()
        ctx = _ctx(state=state, rag=rag, gold_case_id="ho-2024-99999")
        result = await retrieve.dispatch(
            ctx,
            {
                "query": "how was ho-2024-99999 reasoned",
                "purpose": "liability",
            },
        )
        assert result.is_error
        assert rag.calls == []

    async def test_rejects_duplicate_query(self):
        rag = _FakeRAG([_result_chunk()])
        state = _state()
        state.queries_so_far.append(("liability", "duplicate query"))
        ctx = _ctx(state=state, rag=rag)
        result = await retrieve.dispatch(
            ctx,
            {"query": "duplicate query", "purpose": "liability"},
        )
        assert result.is_error
        assert "Duplicate" in str(result.model_payload["error"])
        assert rag.calls == []

    async def test_dedupe_by_source_paragraph(self):
        rag = _FakeRAG([_result_chunk()])
        state = _state()
        # Pre-seed with the same chunk; second retrieve should
        # surface 0 added.
        state.add_chunks(
            [
                AgentChunk(
                    chunk_id="ho_1#p1",
                    source_id="ho_1",
                    paragraph_id="p1",
                    text="x",
                )
            ]
        )
        ctx = _ctx(state=state, rag=rag)
        result = await retrieve.dispatch(
            ctx,
            {"query": "different query", "purpose": "remedy"},
        )
        assert not result.is_error
        assert result.model_payload["added_chunks"] == 0
        assert len(state.chunks_so_far) == 1

    async def test_section_type_filter_passed_through(self):
        rag = _FakeRAG([])
        state = _state()
        ctx = _ctx(state=state, rag=rag)
        await retrieve.dispatch(
            ctx,
            {
                "query": "compensation orders for damp",
                "purpose": "remedy",
                "section_type": "orders",
            },
        )
        assert rag.calls[0]["section_type"] == "orders"

    async def test_no_rag_returns_error(self):
        state = _state()
        ctx = _ctx(state=state, rag=None)
        result = await retrieve.dispatch(
            ctx,
            {"query": "any query here", "purpose": "liability"},
        )
        assert result.is_error
        assert "Retrieval is not available" in str(
            result.model_payload["error"]
        )

    async def test_invalid_purpose_caught_by_pydantic(self):
        rag = _FakeRAG([])
        state = _state()
        ctx = _ctx(state=state, rag=rag)
        result = await retrieve.dispatch(
            ctx,
            {"query": "x", "purpose": "nonsense"},  # not in enum
        )
        # Pydantic rejects at args validation; tool returns is_error.
        assert result.is_error


# ---------------------------------------------------------------------------
# extract_amounts tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExtractAmountsTool:
    async def test_extracts_from_known_chunk(self):
        state = _state()
        state.chunks_so_far.append(
            AgentChunk(
                chunk_id="ho_1#p47",
                source_id="ho_1",
                paragraph_id="p47",
                text="The landlord shall pay £700 in compensation.",
                section_type="orders",
            )
        )
        ctx = _ctx(state=state)
        result = await extract_amounts.dispatch(
            ctx, {"chunk_id": "ho_1#p47"}
        )
        assert not result.is_error
        assert result.model_payload["extracted_count"] == 1
        assert result.model_payload["amounts"][0]["amount_gbp"] == 700.0
        # Side-effect: amounts persisted on state for later use.
        assert len(state.amounts_extracted) == 1

    async def test_unknown_chunk_id_rejected(self):
        state = _state()
        ctx = _ctx(state=state)
        result = await extract_amounts.dispatch(
            ctx, {"chunk_id": "never_seen#p1"}
        )
        assert result.is_error
        assert "not seen in any prior retrieve" in str(
            result.model_payload["error"]
        )

    async def test_zero_amounts_is_not_an_error(self):
        # Real Ombudsman text often has determinations with no £
        # amount; the tool must return successfully with extracted_count=0
        # so the agent can decide what to do next.
        state = _state()
        state.chunks_so_far.append(
            AgentChunk(
                chunk_id="ho_2#p1",
                source_id="ho_2",
                paragraph_id="p1",
                text="The landlord acknowledged the failure but no order was made.",
                section_type="determination",
            )
        )
        ctx = _ctx(state=state)
        result = await extract_amounts.dispatch(
            ctx, {"chunk_id": "ho_2#p1"}
        )
        assert not result.is_error
        assert result.model_payload["extracted_count"] == 0


# ---------------------------------------------------------------------------
# check_kg_fact tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCheckKGFactTool:
    async def test_returns_unknown_when_no_kg(self):
        state = _state()
        ctx = _ctx(state=state, kg=None)
        result = await check_kg_fact.dispatch(
            ctx, {"field": "vulnerability_flag"}
        )
        assert not result.is_error
        assert result.model_payload["is_known"] is False
        assert result.model_payload["value"] is None
        # Side-effect: fact recorded on state.
        assert len(state.kg_facts_seen) == 1

    async def test_uses_kg_typed_reader_when_available(self):
        class _FakeKG:
            def read_typed_fact(self, field: str):
                if field == "vulnerability_flag":
                    return (True, True)
                return (None, False)

        state = _state()
        ctx = _ctx(state=state, kg=_FakeKG())
        result = await check_kg_fact.dispatch(
            ctx, {"field": "vulnerability_flag"}
        )
        assert not result.is_error
        assert result.model_payload["value"] is True
        assert result.model_payload["is_known"] is True

    async def test_invalid_field_caught_by_pydantic(self):
        state = _state()
        ctx = _ctx(state=state)
        result = await check_kg_fact.dispatch(
            ctx, {"field": "ground_truth_outcome"}  # NOT in enum
        )
        assert result.is_error


# ---------------------------------------------------------------------------
# finalize / abstain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFinalizeAndAbstain:
    async def test_finalize_returns_reason_and_confidence(self):
        ctx = _ctx()
        result = await finalize.dispatch(
            ctx,
            {
                "reason": "have liability + 2 comparator amounts",
                "confidence_score": 0.82,
            },
        )
        assert not result.is_error
        assert result.model_payload["confidence_score"] == 0.82
        assert "comparator amounts" in result.model_payload["reason"]

    async def test_finalize_confidence_score_optional(self):
        ctx = _ctx()
        result = await finalize.dispatch(
            ctx,
            {"reason": "ok"},
        )
        # No confidence_score given — tool accepts it; the loop will
        # treat None as "low confidence" downstream.
        assert not result.is_error
        assert result.model_payload["confidence_score"] is None

    async def test_finalize_confidence_out_of_range_rejected(self):
        ctx = _ctx()
        result = await finalize.dispatch(
            ctx,
            {"reason": "ok", "confidence_score": 1.5},
        )
        assert result.is_error  # ge=0.0,le=1.0 caught by Pydantic

    async def test_abstain_requires_reason(self):
        ctx = _ctx()
        result = await abstain.dispatch(ctx, {"reason": ""})
        # min_length=4 rejected.
        assert result.is_error

    async def test_abstain_records_reason(self):
        ctx = _ctx()
        result = await abstain.dispatch(
            ctx, {"reason": "no liability span exists in any retrieved chunk"}
        )
        assert not result.is_error
        assert "no liability span" in result.model_payload["reason"]


# ---------------------------------------------------------------------------
# ToolSet
# ---------------------------------------------------------------------------


class TestToolSet:
    def test_build_retrieval_toolset_has_five_tools(self):
        ts = build_retrieval_toolset()
        names = {t.name for t in ts.tools}
        assert names == {
            "retrieve",
            "extract_amounts",
            "check_kg_fact",
            "finalize",
            "abstain",
        }

    def test_anthropic_schemas_well_formed(self):
        ts = build_retrieval_toolset()
        schemas = ts.anthropic_schemas()
        assert len(schemas) == 5
        for s in schemas:
            assert "name" in s
            assert "description" in s
            assert s["input_schema"]["type"] == "object"
            assert "properties" in s["input_schema"]

    def test_retrieve_schema_enforces_purpose_enum(self):
        ts = build_retrieval_toolset()
        retrieve_schema = next(s for s in ts.anthropic_schemas() if s["name"] == "retrieve")
        purpose_prop = retrieve_schema["input_schema"]["properties"]["purpose"]
        assert set(purpose_prop["enum"]) == {
            "liability",
            "remedy",
            "vulnerability",
            "timeline",
            "adhoc",
        }


# ---------------------------------------------------------------------------
# Context guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContextGuard:
    async def test_plain_tool_context_rejected(self):
        # Use the parent ToolContext directly (no agent_state). This
        # is a programming error — tools must not be invoked outside
        # the retrieval-agent loop.
        from llm_orchestrator.agent_loop.context import ToolContext

        ctx = ToolContext()
        result = await retrieve.dispatch(
            ctx,
            {"query": "x is a fine query", "purpose": "liability"},
        )
        assert result.is_error
        assert "RetrievalToolContext" in str(result.model_payload["error"])
