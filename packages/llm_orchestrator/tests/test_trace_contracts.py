from datetime import datetime, timezone

import pytest

from ..agent_loop.trace import (
    TraceLogger,
    TraceStep,
    TraceSummary,
    TraceTerminationReason,
    redact_text,
)


def _make_step(index: int, duration_ms: int = 10, tokens_in: int = 5, tokens_out: int = 3) -> TraceStep:
    return TraceStep(
        index=index,
        kind="model_turn",
        started_at=datetime.now(timezone.utc),
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


def test_redact_text_masks_pii_in_one_string() -> None:
    raw = "Contact alice@example.com or call 07700 900123 from SW1A 1AA."
    result = redact_text(raw)
    assert "[email]" in result
    assert "alice@example.com" not in result
    assert "[phone]" in result
    assert "07700 900123" not in result
    assert "[postcode]" in result
    assert "SW1A 1AA" not in result


def test_redact_text_truncates_when_exceeds_max_chars() -> None:
    long_input = "a" * 600
    result = redact_text(long_input, max_chars=100)
    assert len(result) <= 101  # 100 chars + ellipsis character
    assert result.endswith("…")


def test_trace_summary_round_trips_via_model_validate() -> None:
    steps = [_make_step(0), _make_step(1)]
    summary = TraceSummary(
        trace_id="test-id",
        termination=TraceTerminationReason.END_TURN,
        total_duration_ms=20,
        total_tokens_in=10,
        total_tokens_out=6,
        steps=steps,
    )
    dumped = summary.model_dump()
    restored = TraceSummary.model_validate(dumped)
    assert len(restored.steps) == 2
    assert restored.trace_id == "test-id"
    assert restored.termination == TraceTerminationReason.END_TURN


def test_trace_logger_no_op_aggregates_correctly() -> None:
    logger = TraceLogger.no_op()
    logger.start_trace(trace_id="abc-123")
    logger.record_step(_make_step(0, duration_ms=100, tokens_in=10, tokens_out=5))
    logger.record_step(_make_step(1, duration_ms=200, tokens_in=20, tokens_out=8))
    summary = logger.end_trace(termination=TraceTerminationReason.END_TURN)

    assert summary.trace_id == "abc-123"
    assert summary.termination == TraceTerminationReason.END_TURN
    assert summary.total_duration_ms == 300
    assert summary.total_tokens_in == 30
    assert summary.total_tokens_out == 13
    assert len(summary.steps) == 2


def test_trace_logger_auto_generates_trace_id_when_omitted() -> None:
    logger = TraceLogger.no_op()
    logger.start_trace()
    summary = logger.end_trace(termination=TraceTerminationReason.MAX_TURNS)
    assert summary.trace_id != ""
    assert len(summary.trace_id) > 0
