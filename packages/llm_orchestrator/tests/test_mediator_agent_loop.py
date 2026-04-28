"""Scripted-client tests for the migrated MediatorAgent flows.

Covers both generate_opening_message (Step 5) and generate_response (Step 6).
Drives the AgentLoop via a fake AgentTurnClient scripted with pre-built
AgentTurnResponse objects. Assertions check that the intended tools appear
in the returned TraceSummary and that the final text is populated.
- scripted client was called exactly twice
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from ..agent_loop.loop import AgentTurnClient, AgentTurnResponse
from ..agent_loop.trace import TraceSummary
from ..agents.mediator_agent import MediatorAgent
from ..models.prediction_v2 import OutcomeType, PredictionResult


# ---------------------------------------------------------------------------
# Scripted fake AgentTurnClient
# ---------------------------------------------------------------------------


class _ScriptedClient:
    """Consumes a queue of AgentTurnResponse objects in FIFO order."""

    def __init__(self, responses: List[AgentTurnResponse]) -> None:
        self._responses: List[AgentTurnResponse] = list(responses)
        self.calls: List[Dict[str, Any]] = []

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> AgentTurnResponse:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "messages": [dict(m) for m in messages],
                "tool_schemas": list(tool_schemas),
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        if not self._responses:
            raise AssertionError("Scripted client called more times than scripted.")
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

_OPENER_TEXT = (
    "This is not legal advice. All information is based on analysis of similar "
    "tribunal cases. Based on similar cases, settlements typically land between "
    "£300 and £500. Both parties have reasonable positions and I encourage "
    "an open dialogue to find common ground."
)


def _make_scripted_client() -> _ScriptedClient:
    """Two-turn script: model asks for ZOPA, then replies with final text."""
    call_1 = AgentTurnResponse(
        content_blocks=[
            {
                "type": "tool_use",
                "id": "t1",
                "name": "calculate_zopa",
                "input": {},
            }
        ],
        stop_reason="tool_use",
        tokens_in=100,
        tokens_out=20,
        model_used="fake-model",
    )
    call_2 = AgentTurnResponse(
        content_blocks=[{"type": "text", "text": _OPENER_TEXT}],
        stop_reason="end_turn",
        tokens_in=120,
        tokens_out=60,
        model_used="fake-model",
    )
    return _ScriptedClient(responses=[call_1, call_2])


def _make_prediction() -> PredictionResult:
    return PredictionResult(
        case_id="CASE-001",
        overall_outcome=OutcomeType.SPLIT,
        overall_confidence=0.72,
        predicted_settlement_range=(300.0, 500.0),
        key_strengths=["Checkout inventory signed by tenant", "Photos timestamped"],
        key_weaknesses=["Wear-and-tear deductions unclear"],
        retrieved_cases=["Jones v Smith [2021]", "Patel v Henderson [2022]"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_opening_message_calls_zopa_tool() -> None:
    """generate_opening_message invokes calculate_zopa then returns text + trace."""
    scripted = _make_scripted_client()
    agent = MediatorAgent(llm_client=scripted)

    prediction = _make_prediction()
    dispute: Dict[str, Any] = {
        "dispute_id": "DISP-TEST01",
        "deposit_amount": 800.0,
        "property_address": "10 Example Street, London",
    }
    expectation_tenant: Dict[str, Any] = {
        "expected_return": 700.0,
        "key_issues": ["cleaning", "damage"],
    }
    expectation_landlord: Dict[str, Any] = {
        "expected_deduction": 400.0,
        "key_issues": ["redecoration", "cleaning"],
    }

    final_text, trace = await agent.generate_opening_message(
        prediction=prediction,
        dispute=dispute,
        expectation_data_tenant=expectation_tenant,
        expectation_data_landlord=expectation_landlord,
    )

    # --- return types ---
    assert isinstance(final_text, str), "final_text must be a str"
    assert len(final_text) > 0, "final_text must be non-empty"
    assert isinstance(trace, TraceSummary), "trace must be a TraceSummary"

    # --- trace contains a calculate_zopa tool_call step ---
    tool_call_steps = [s for s in trace.steps if s.kind == "tool_call"]
    assert len(tool_call_steps) >= 1, "trace must contain at least one tool_call step"
    zopa_steps = [s for s in tool_call_steps if s.name == "calculate_zopa"]
    assert len(zopa_steps) >= 1, "trace must contain a calculate_zopa step"

    # --- scripted client was called exactly twice ---
    assert len(scripted.calls) == 2, (
        f"Expected 2 LLM calls (tool_use turn + reply turn), got {len(scripted.calls)}"
    )


@pytest.mark.asyncio
async def test_generate_opening_message_returns_empty_str_on_max_turns() -> None:
    """If the loop hits max_turns without end_turn, return ('', trace)."""
    # Single response that always asks for a tool — loop will exhaust max_turns=6.
    loop_response = AgentTurnResponse(
        content_blocks=[
            {
                "type": "tool_use",
                "id": "tx",
                "name": "calculate_zopa",
                "input": {},
            }
        ],
        stop_reason="tool_use",
        tokens_in=10,
        tokens_out=5,
        model_used="fake-model",
    )

    class _LoopingClient:
        def __init__(self) -> None:
            self.call_count = 0

        async def run_agent_turn(self, **kwargs: Any) -> AgentTurnResponse:
            self.call_count += 1
            return loop_response

    looping = _LoopingClient()
    agent = MediatorAgent(llm_client=looping)  # type: ignore[arg-type]
    prediction = _make_prediction()

    final_text, trace = await agent.generate_opening_message(
        prediction=prediction,
        dispute={"dispute_id": "DISP-LOOP"},
        expectation_data_tenant={},
        expectation_data_landlord={},
    )

    assert final_text == "", "MAX_TURNS path should return empty string"
    assert isinstance(trace, TraceSummary)
    assert looping.call_count == 6  # max_turns=6
    assert trace.steps, "MAX_TURNS trace should still record the steps it took"
    assert any(
        step.name == "calculate_zopa" for step in trace.steps
    ), "MAX_TURNS trace should record the looping tool dispatch"


# ---------------------------------------------------------------------------
# generate_response tests (Step 6)
# ---------------------------------------------------------------------------

_RESPONSE_TEXT = "Based on similar cases, a settlement in the £300-£500 range seems reasonable."


def _make_response_scripted_client() -> _ScriptedClient:
    """Three-turn script: calculate_counter_range → get_cost_benefit → final text."""
    call_1 = AgentTurnResponse(
        content_blocks=[
            {
                "type": "tool_use",
                "id": "r1",
                "name": "calculate_counter_range",
                "input": {"current_offer": 400, "role": "tenant"},
            }
        ],
        stop_reason="tool_use",
        tokens_in=100,
        tokens_out=20,
        model_used="fake-model",
    )
    call_2 = AgentTurnResponse(
        content_blocks=[
            {
                "type": "tool_use",
                "id": "r2",
                "name": "get_cost_benefit",
                "input": {"role": "tenant"},
            }
        ],
        stop_reason="tool_use",
        tokens_in=120,
        tokens_out=20,
        model_used="fake-model",
    )
    call_3 = AgentTurnResponse(
        content_blocks=[{"type": "text", "text": _RESPONSE_TEXT}],
        stop_reason="end_turn",
        tokens_in=140,
        tokens_out=60,
        model_used="fake-model",
    )
    return _ScriptedClient(responses=[call_1, call_2, call_3])


@pytest.mark.asyncio
async def test_generate_response_calls_counter_range_and_cost_benefit() -> None:
    """generate_response invokes calculate_counter_range and get_cost_benefit then returns text + trace."""
    scripted = _make_response_scripted_client()
    agent = MediatorAgent(llm_client=scripted)

    prediction = _make_prediction()
    dispute: Dict[str, Any] = {
        "dispute_id": "DISP-TEST02",
        "deposit_amount": 800.0,
        "property_address": "20 Example Road, London",
    }
    messages: List[Dict[str, Any]] = [
        {"sender_role": "tenant", "content": "I want my full deposit back."},
        {"sender_role": "landlord", "content": "There was damage - I'll return £400."},
    ]

    from ..models.mediation import StructuredOffer

    latest_offer = StructuredOffer(
        proposed_by_role="landlord",
        amount=400.0,
    )

    final_text, trace = await agent.generate_response(
        messages=messages,
        prediction=prediction,
        dispute=dispute,
        latest_offer=latest_offer,
    )

    # --- return types ---
    assert isinstance(final_text, str), "final_text must be a str"
    assert len(final_text) > 0, "final_text must be non-empty"
    assert isinstance(trace, TraceSummary), "trace must be a TraceSummary"

    # --- trace contains expected tool_call steps ---
    tool_call_steps = [s for s in trace.steps if s.kind == "tool_call"]
    tool_names = [s.name for s in tool_call_steps]
    assert "calculate_counter_range" in tool_names, (
        f"trace must contain calculate_counter_range step; got {tool_names}"
    )
    assert "get_cost_benefit" in tool_names, (
        f"trace must contain get_cost_benefit step; got {tool_names}"
    )

    # --- scripted client was called exactly 3 times ---
    assert len(scripted.calls) == 3, (
        f"Expected 3 LLM calls, got {len(scripted.calls)}"
    )

    # --- stats are incremented ---
    assert agent.get_stats()["messages_processed"] == 1
