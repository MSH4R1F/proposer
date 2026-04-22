"""
Tests for the optional reasoning_trace field on MediationMessage.
"""

from datetime import datetime

from packages.llm_orchestrator.agent_loop.trace import (
    TraceStep,
    TraceSummary,
    TraceTerminationReason,
)
from packages.llm_orchestrator.models.mediation import MediationMessage


def _make_trace_summary() -> TraceSummary:
    step = TraceStep(
        index=0,
        kind="model_turn",
        name="mediator_reply",
        started_at=datetime(2024, 1, 1, 12, 0, 0),
        duration_ms=350,
        tokens_in=120,
        tokens_out=80,
        input_preview="What is a fair settlement?",
        output_preview="Based on similar cases…",
        is_error=False,
    )
    return TraceSummary(
        trace_id="test-trace-001",
        termination=TraceTerminationReason.END_TURN,
        total_duration_ms=350,
        total_tokens_in=120,
        total_tokens_out=80,
        steps=[step],
    )


def test_default_reasoning_trace_is_none() -> None:
    msg = MediationMessage(sender_role="tenant", content="Hello")
    assert msg.reasoning_trace is None


def test_message_without_trace_round_trips() -> None:
    msg = MediationMessage(sender_role="tenant", content="hi")
    data = msg.model_dump(mode="json")
    restored = MediationMessage.model_validate(data)
    assert restored.reasoning_trace is None


def test_message_with_trace_round_trips() -> None:
    trace = _make_trace_summary()
    msg = MediationMessage(
        sender_role="ai_mediator",
        content="Here is my analysis.",
        reasoning_trace=trace,
    )
    data = msg.model_dump(mode="json")
    restored = MediationMessage.model_validate(data)
    assert restored.reasoning_trace is not None
    assert restored.reasoning_trace.model_dump() == trace.model_dump()
