from ..agent_loop.context import ToolContext
from ..agent_loop.trace import TraceLogger


def test_default_construction_has_none_fields() -> None:
    ctx = ToolContext()
    assert ctx.rag is None
    assert ctx.kg is None
    assert ctx.storage is None
    assert ctx.dispute_id is None
    assert ctx.user_id is None
    assert ctx.session_id is None
    assert ctx.request_id is None


def test_trace_logger_is_trace_logger_instance() -> None:
    ctx = ToolContext()
    assert isinstance(ctx.trace_logger, TraceLogger)


def test_two_instances_have_different_trace_loggers() -> None:
    ctx1 = ToolContext()
    ctx2 = ToolContext()
    assert ctx1.trace_logger is not ctx2.trace_logger


def test_redact_pii_defaults_to_true() -> None:
    ctx = ToolContext()
    assert ctx.redact_pii is True


def test_override_fields_hold_values_and_rest_stay_defaulted() -> None:
    ctx = ToolContext(dispute_id="abc", user_id="u1")
    assert ctx.dispute_id == "abc"
    assert ctx.user_id == "u1"
    assert ctx.rag is None
    assert ctx.kg is None
    assert ctx.storage is None
    assert ctx.session_id is None
    assert ctx.request_id is None
    assert ctx.redact_pii is True
    assert isinstance(ctx.trace_logger, TraceLogger)
