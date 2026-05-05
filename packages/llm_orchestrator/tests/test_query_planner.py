"""Tests for the QueryPlanner module.

The QueryPlanner makes one LLM call. We exercise it with a scripted
fake client that mimics the ClaudeClient.run_agent_turn signature and
returns content_blocks shaped as the real Anthropic response would
deliver them (a single tool_use block with structured input).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import pytest

from llm_orchestrator.agent_loop.loop import AgentTurnResponse
from llm_orchestrator.models.agent_state import QueryPlan
from llm_orchestrator.pipeline.query_planner import (
    _EMIT_TOOL_NAME,
    QueryPlanner,
    _emit_query_plan_tool_schema,
)


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


@dataclass
class _FakeClaude:
    """Drop-in for ClaudeClient.run_agent_turn used in tests.

    Records the call kwargs and returns whatever AgentTurnResponse the
    test prepared. ``raise_on_call`` simulates a transient API failure
    so the empty-plan fallback path can be exercised.
    """

    next_response: Optional[AgentTurnResponse] = None
    raise_on_call: Optional[Exception] = None
    last_kwargs: Optional[dict] = None

    async def run_agent_turn(self, **kwargs: Any) -> AgentTurnResponse:
        self.last_kwargs = kwargs
        if self.raise_on_call is not None:
            raise self.raise_on_call
        assert self.next_response is not None
        return self.next_response


def _emit_block(queries: List[dict]) -> dict:
    """Shape a tool_use block the way the SDK would."""
    return {
        "type": "tool_use",
        "id": "tool_call_1",
        "name": _EMIT_TOOL_NAME,
        "input": {"queries": queries},
    }


def _response(content_blocks: List[dict]) -> AgentTurnResponse:
    return AgentTurnResponse(
        content_blocks=content_blocks,
        stop_reason="tool_use",
        tokens_in=420,
        tokens_out=88,
        model_used="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------


class TestToolSchema:
    def test_schema_well_formed(self):
        schema = _emit_query_plan_tool_schema()
        assert schema["name"] == _EMIT_TOOL_NAME
        assert schema["input_schema"]["type"] == "object"
        props = schema["input_schema"]["properties"]
        assert "queries" in props
        # The queries field should be array-typed; nested $ref must
        # have been inlined so Anthropic accepts the schema directly.
        queries_schema = props["queries"]
        assert queries_schema["type"] == "array"
        # Inlined item schema has type=object with purpose/text fields.
        item = queries_schema.get("items", {})
        assert item.get("type") == "object"
        assert "purpose" in item.get("properties", {})

    def test_schema_no_dollar_refs_remaining(self):
        # Anthropic rejects $ref. Sanity-check that our inliner caught
        # every path. Walk the tree.
        schema = _emit_query_plan_tool_schema()

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                assert "$ref" not in node, f"unresolved $ref in {node}"
                assert "$defs" not in node
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)

        _walk(schema)


# ---------------------------------------------------------------------------
# Happy-path planning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPlanHappyPath:
    async def test_returns_kept_queries(self):
        client = _FakeClaude(
            next_response=_response(
                [
                    _emit_block(
                        [
                            {
                                "purpose": "liability",
                                "text": "damp mould response timelines",
                                "rationale": "core liability evidence",
                            },
                            {
                                "purpose": "remedy",
                                "text": "compensation orders for damp delay",
                                "rationale": "comparator amounts",
                            },
                            {
                                "purpose": "vulnerability",
                                "text": "vulnerable resident impact factors",
                                "rationale": "severity modifier",
                            },
                        ]
                    )
                ]
            )
        )
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(
            case_summary="The property has had damp and mould for 14 months.",
            issue_type="repairs_damp_mould",
            gold_case_id="ho-2024-99999",
        )
        assert isinstance(plan, QueryPlan)
        assert [q.purpose for q in plan.queries] == [
            "liability",
            "remedy",
            "vulnerability",
        ]
        assert plan.decomposer_tokens_in == 420
        assert plan.decomposer_tokens_out == 88
        assert plan.decomposer_model == "claude-sonnet-4-6"

    async def test_forced_tool_choice_in_request(self):
        client = _FakeClaude(
            next_response=_response(
                [
                    _emit_block(
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
        )
        planner = QueryPlanner(llm_client=client)
        await planner.plan(
            case_summary="x",
            issue_type="repairs_disrepair",
        )
        # Verify the planner forces the single tool — guarantees the
        # model returns a structured QueryPlan, not free text.
        tc = client.last_kwargs["tool_choice"]
        assert tc == {"type": "tool", "name": _EMIT_TOOL_NAME}

    async def test_system_prompt_uses_cache_breakpoint(self):
        client = _FakeClaude(
            next_response=_response(
                [
                    _emit_block(
                        [
                            {
                                "purpose": "remedy",
                                "text": "compensation",
                                "rationale": "x",
                            }
                        ]
                    )
                ]
            )
        )
        planner = QueryPlanner(llm_client=client)
        await planner.plan(case_summary="x", issue_type="repairs_disrepair")
        system = client.last_kwargs["system_prompt"]
        # System should be a list of text blocks with cache_control on
        # the static rules block — enables the 60% cache hit rate.
        assert isinstance(system, list)
        assert system[0]["type"] == "text"
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        # And the static text should include the version marker so a
        # prompt change invalidates the cache.
        assert "query_planner_version:" in system[0]["text"]


# ---------------------------------------------------------------------------
# Leakage filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLeakageFiltering:
    async def test_outcome_phrase_query_dropped(self):
        client = _FakeClaude(
            next_response=_response(
                [
                    _emit_block(
                        [
                            {
                                "purpose": "liability",
                                "text": "damp mould response",
                                "rationale": "ok",
                            },
                            {
                                "purpose": "remedy",
                                "text": "compensation £700 awarded cases",
                                "rationale": "leaks outcome",
                            },
                            {
                                "purpose": "remedy",
                                "text": "comparator damp orders amounts",
                                "rationale": "fine",
                            },
                        ]
                    )
                ]
            )
        )
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(
            case_summary="x",
            issue_type="repairs_damp_mould",
            gold_case_id="ho-1",
        )
        # The outcome-revealing query is dropped; the other two remain.
        assert len(plan.queries) == 2
        texts = [q.text for q in plan.queries]
        assert "damp mould response" in texts
        assert "comparator damp orders amounts" in texts
        assert all("£700" not in t for t in texts)

    async def test_self_reference_query_dropped(self):
        client = _FakeClaude(
            next_response=_response(
                [
                    _emit_block(
                        [
                            {
                                "purpose": "liability",
                                "text": "ho-2024-99999 prior decisions",
                                "rationale": "self-ref",
                            },
                            {
                                "purpose": "remedy",
                                "text": "remedy band examples for damp",
                                "rationale": "ok",
                            },
                        ]
                    )
                ]
            )
        )
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(
            case_summary="x",
            issue_type="repairs_damp_mould",
            gold_case_id="ho-2024-99999",
        )
        assert len(plan.queries) == 1
        assert plan.queries[0].purpose == "remedy"

    async def test_internal_dedup_dropped(self):
        # Same (purpose, text) twice — one is a duplicate, drop it.
        client = _FakeClaude(
            next_response=_response(
                [
                    _emit_block(
                        [
                            {
                                "purpose": "remedy",
                                "text": "compensation patterns",
                                "rationale": "first",
                            },
                            {
                                "purpose": "remedy",
                                "text": "compensation patterns",
                                "rationale": "second copy",
                            },
                        ]
                    )
                ]
            )
        )
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(case_summary="x", issue_type="repairs_disrepair")
        assert len(plan.queries) == 1


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFailureModes:
    async def test_llm_error_returns_empty_plan(self):
        client = _FakeClaude(raise_on_call=RuntimeError("boom"))
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(case_summary="x", issue_type="x")
        assert isinstance(plan, QueryPlan)
        assert plan.queries == []
        assert plan.decomposer_tokens_in == 0
        assert plan.decomposer_tokens_out == 0

    async def test_no_tool_use_block_returns_empty_plan(self):
        # Model returned text instead of a tool_use block (shouldn't
        # happen with tool_choice=tool, but defensively handled).
        client = _FakeClaude(
            next_response=_response(
                [{"type": "text", "text": "I refuse."}]
            )
        )
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(case_summary="x", issue_type="x")
        assert plan.queries == []

    async def test_invalid_args_returns_empty_plan(self):
        # Tool call returned, but args don't validate (e.g. purpose
        # not in enum). Pydantic rejects, planner returns empty.
        client = _FakeClaude(
            next_response=_response(
                [
                    {
                        "type": "tool_use",
                        "id": "x",
                        "name": _EMIT_TOOL_NAME,
                        "input": {
                            "queries": [
                                {
                                    "purpose": "not_a_purpose",
                                    "text": "x is fine",
                                    "rationale": "x",
                                }
                            ]
                        },
                    }
                ]
            )
        )
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(case_summary="x", issue_type="x")
        assert plan.queries == []

    async def test_caps_kept_at_5(self):
        # Model emits 7 valid queries; planner caps to 5 even if the
        # schema allows up to 8.
        queries = [
            {
                "purpose": "remedy" if i == 0 else "liability",
                "text": f"unique evidence query number {i}",
                "rationale": "ok",
            }
            for i in range(7)
        ]
        client = _FakeClaude(next_response=_response([_emit_block(queries)]))
        planner = QueryPlanner(llm_client=client)
        plan = await planner.plan(case_summary="x", issue_type="x")
        assert len(plan.queries) == 5
