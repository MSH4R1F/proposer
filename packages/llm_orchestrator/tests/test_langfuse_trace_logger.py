"""Unit tests for LangFuseTraceLogger.

All tests run offline. The langfuse SDK is NOT installed in the test
environment, so the fallback path is exercised by default. For the
"SDK-available" case we inject a fake `langfuse` module into sys.modules.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ..agent_loop.trace import (
    LangFuseTraceLogger,
    TraceLogger,
    TraceStep,
    TraceTerminationReason,
)


def _make_step(index: int = 0, is_error: bool = False) -> TraceStep:
    return TraceStep(
        index=index,
        kind="model_turn",
        name="turn",
        started_at=datetime.now(timezone.utc),
        duration_ms=10,
        tokens_in=5,
        tokens_out=3,
        input_preview="hello",
        output_preview="world",
        is_error=is_error,
    )


def test_langfuse_logger_falls_back_to_noop_without_sdk() -> None:
    """If importing langfuse raises, the logger degrades to in-memory behavior."""

    # Build a fake `langfuse` module whose attribute access raises ImportError.
    # We patch sys.modules so the `from langfuse import Langfuse` line fails.
    # The cleanest way is to make the import itself raise by putting a
    # non-module value into sys.modules. We use a MagicMock that raises on
    # attribute access.
    broken_module = MagicMock()
    broken_module.Langfuse = MagicMock(side_effect=ImportError("forced"))

    with patch.dict(sys.modules, {"langfuse": broken_module}):
        logger = LangFuseTraceLogger(public_key="x", secret_key="y", host="z")

    assert logger._client is None
    assert logger._root_trace is None

    # Full lifecycle must still work with no exceptions.
    logger.start_trace(trace_id="trace-abc", tags={"foo": "bar"})
    logger.record_step(_make_step(0))
    logger.record_step(_make_step(1))
    summary = logger.end_trace(termination=TraceTerminationReason.END_TURN)

    assert summary.trace_id == "trace-abc"
    assert summary.termination == TraceTerminationReason.END_TURN
    assert len(summary.steps) == 2
    assert summary.total_duration_ms == 20
    assert summary.total_tokens_in == 10
    assert summary.total_tokens_out == 6


def test_langfuse_logger_records_steps_through_base() -> None:
    """With _client=None, record_step still appends to the in-memory trace."""
    # Simulate absent SDK: sys.modules has no "langfuse" key, so the lazy
    # `from langfuse import Langfuse` inside __init__ should ImportError.
    saved = sys.modules.pop("langfuse", None)
    try:
        logger = LangFuseTraceLogger(public_key="x", secret_key="y", host="z")
    finally:
        if saved is not None:
            sys.modules["langfuse"] = saved

    assert logger._client is None

    logger.start_trace(trace_id="base-trace")
    logger.record_step(_make_step(0))
    logger.record_step(_make_step(1))
    logger.record_step(_make_step(2))
    summary = logger.end_trace(termination=TraceTerminationReason.MAX_TURNS)

    assert len(summary.steps) == 3
    assert summary.trace_id == "base-trace"
    assert summary.termination == TraceTerminationReason.MAX_TURNS


def test_langfuse_logger_delegates_to_client_when_available() -> None:
    """When the Langfuse SDK is importable, trace/span/flush are called."""
    fake_client = MagicMock()
    fake_root_trace = MagicMock()
    fake_client.trace.return_value = fake_root_trace

    fake_langfuse_class = MagicMock(return_value=fake_client)

    # Inject a fake `langfuse` module with the `Langfuse` symbol.
    fake_module = types.ModuleType("langfuse")
    fake_module.Langfuse = fake_langfuse_class

    with patch.dict(sys.modules, {"langfuse": fake_module}):
        logger = LangFuseTraceLogger(
            public_key="pk",
            secret_key="sk",
            host="http://langfuse.local",
            session_id="sess-1",
            user_id="user-1",
            dispute_id="disp-1",
        )

        # Client constructed with the creds.
        fake_langfuse_class.assert_called_once_with(
            public_key="pk",
            secret_key="sk",
            host="http://langfuse.local",
        )
        assert logger._client is fake_client

        logger.start_trace(trace_id="tid", tags={"tag": "v"})
        fake_client.trace.assert_called_once()
        trace_kwargs = fake_client.trace.call_args.kwargs
        assert trace_kwargs["id"] == "tid"
        assert trace_kwargs["session_id"] == "sess-1"
        assert trace_kwargs["user_id"] == "user-1"
        assert trace_kwargs["metadata"]["dispute_id"] == "disp-1"
        assert trace_kwargs["metadata"]["tag"] == "v"

        logger.record_step(_make_step(0))
        logger.record_step(_make_step(1, is_error=True))
        assert fake_root_trace.span.call_count == 2

        # Error step should map to level="ERROR"
        second_call_kwargs = fake_root_trace.span.call_args_list[1].kwargs
        assert second_call_kwargs["level"] == "ERROR"

        # First step: level="DEFAULT"
        first_call_kwargs = fake_root_trace.span.call_args_list[0].kwargs
        assert first_call_kwargs["level"] == "DEFAULT"
        assert first_call_kwargs["input"] == "hello"
        assert first_call_kwargs["output"] == "world"

        summary = logger.end_trace(termination=TraceTerminationReason.END_TURN)
        fake_client.flush.assert_called_once()

    # Base-class aggregation still works.
    assert len(summary.steps) == 2
    assert summary.termination == TraceTerminationReason.END_TURN


# ---------------------------------------------------------------------------
# SHA-20 Phase 8: tag emission + None-stripping
# ---------------------------------------------------------------------------


def test_no_op_logger_drops_none_tags() -> None:
    logger = TraceLogger.no_op()
    logger.start_trace(
        trace_id="t-phase8",
        tags={
            "domain.id": "housing.deposit.v1",
            "source.publisher": None,  # should be dropped
            "llm.role": None,
        },
    )
    summary = logger.end_trace(termination=TraceTerminationReason.END_TURN)
    assert summary.metadata["domain.id"] == "housing.deposit.v1"
    assert "source.publisher" not in summary.metadata
    assert "llm.role" not in summary.metadata


def test_langfuse_logger_drops_none_tags_in_metadata() -> None:
    fake_client = MagicMock()
    fake_root_trace = MagicMock()
    fake_client.trace.return_value = fake_root_trace
    fake_langfuse_class = MagicMock(return_value=fake_client)

    fake_module = types.ModuleType("langfuse")
    fake_module.Langfuse = fake_langfuse_class

    with patch.dict(sys.modules, {"langfuse": fake_module}):
        logger = LangFuseTraceLogger(
            public_key="pk", secret_key="sk", host="h"
        )
        logger.start_trace(
            trace_id="t-1",
            tags={
                "domain.id": "employment.unfair_dismissal.v1",
                "source.publisher": None,
                "llm.role": None,
            },
        )
        kwargs = fake_client.trace.call_args.kwargs
        meta = kwargs["metadata"]
        assert meta["domain.id"] == "employment.unfair_dismissal.v1"
        assert "source.publisher" not in meta
        assert "llm.role" not in meta


def test_no_op_logger_emits_phase8_tag_set() -> None:
    """The trace metadata round-trips the Phase 8 tag superset."""
    logger = TraceLogger.no_op()
    full_tags = {
        "domain.id": "housing.deposit.v1",
        "domain.family": "housing",
        "domain.domain_version": "v1",
        "domain.stage": "research",
        "forum": "deposit_scheme_adjudication",
        "retrieval.namespace": "housing_deposit_v1_legacy",
        "prompt_pack.id": "housing.deposit.v1",
        "ontology.id": "housing.deposit.v1",
        "eval_suite.id": "housing.deposit.v1",
        "prediction_mode": "production",
        "cross_domain_retrieval": "false",
        "domain_gate.artifact_id": "housing.deposit.v1",
        "domain_gate.artifact_hash": "deadbeef",
    }
    logger.start_trace(trace_id="phase8-tags", tags=full_tags)
    summary = logger.end_trace(termination=TraceTerminationReason.END_TURN)
    for k, v in full_tags.items():
        assert summary.metadata[k] == v
