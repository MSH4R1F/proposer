from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field

TraceStepKind = Literal["model_turn", "tool_call", "tool_error", "termination"]


class TraceTerminationReason(str, Enum):
    END_TURN = "end_turn"
    MAX_TURNS = "max_turns"
    MODEL_ERROR = "model_error"
    # Retrieval-agent-specific terminators (see
    # ``docs/research/hybrid-rag-agentic-retrieval-plan-2026-05-05.md`` §3.4
    # and ``agentic-retrieval-architecture-research-2026-05-05.md`` §3.3).
    JUDGE_OK = "judge_ok"  # judge called finalize() with confidence >= tau
    JUDGE_ABSTAIN = "judge_abstain"  # judge declared no liability span exists
    JUDGE_INVALID = "judge_invalid"  # 2 consecutive invalid tool calls
    DUP_QUERY = "dup_query"  # cycle guard: same (purpose, query) twice
    TOKEN_CAP = "token_cap"  # cumulative tool-trace tokens exceeded
    CHUNKS_CAP = "chunks_cap"  # cumulative deduped chunks exceeded
    MAX_ITER = "max_iter"  # hard iteration cap reached


class TraceStep(BaseModel):
    index: int
    kind: TraceStepKind
    name: Optional[str] = None
    started_at: datetime
    duration_ms: int
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None
    is_error: bool = False


class TraceSummary(BaseModel):
    trace_id: str
    termination: TraceTerminationReason
    total_duration_ms: int
    total_tokens_in: int
    total_tokens_out: int
    steps: List[TraceStep]
    # SHA-20 Phase 3: free-form trace-level metadata (e.g. domain tags) so
    # callers can preserve routing context past Phase 8's full launch-gate
    # work. Defaults to empty so existing serialised traces still validate.
    metadata: Dict[str, Any] = Field(default_factory=dict)


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+44\s?|0)7\d{3}\s?\d{6}")
_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b", re.IGNORECASE)
# UK National Insurance number, e.g. ``QQ123456C``. Letters D, F, I, Q, U, V
# are excluded from prefix positions (HMRC rules); we follow the closed
# allowlist so we don't mistakenly mask non-NI substrings.
_NI_NUMBER_RE = re.compile(
    r"\b[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]\b"
)


def redact_text(value: str, *, max_chars: int = 500) -> str:
    """Mask UK PII patterns then truncate to max_chars."""
    value = _EMAIL_RE.sub("[email]", value)
    value = _PHONE_RE.sub("[phone]", value)
    value = _POSTCODE_RE.sub("[postcode]", value)
    if len(value) > max_chars:
        value = value[:max_chars] + "\u2026"
    return value


def _scrub_employment_trace_text(
    text: str,
    *,
    party_names: Optional[Iterable[str]] = None,
    max_chars: int = 500,
) -> str:
    """Conservative regex scrubber for employment-domain trace text.

    Phase 8 wires this in front of LangFuse / no-op trace previews when
    the resolved domain family is ``employment``. The redaction is
    intentionally narrow:

    * email addresses \u2192 ``[email]``
    * UK mobile / landline-shaped numbers \u2192 ``[phone]``
    * UK postcodes \u2192 ``[postcode]``
    * UK National Insurance numbers \u2192 ``[ni_number]``
    * Known party names (allowlist) \u2192 ``[person]``

    Production-grade redaction (medical history, payroll identifiers,
    free-text claimant narrative, addresses, \u2026) lands in Phase 11. Until
    then, callers must NOT pass employment trace text directly to
    LangFuse without invoking this helper. If a future code path needs
    something stronger and Phase 11 is not yet ready, add a
    ``# TODO Phase 11: real redaction`` placeholder that *errors* rather
    than defaulting to pass-through.
    """
    value = _EMAIL_RE.sub("[email]", text)
    value = _PHONE_RE.sub("[phone]", value)
    value = _POSTCODE_RE.sub("[postcode]", value)
    value = _NI_NUMBER_RE.sub("[ni_number]", value)
    for name in party_names or ():
        if not name:
            continue
        # Word-boundary match, case-insensitive.
        try:
            pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        except re.error:  # pragma: no cover - defensive
            continue
        value = pattern.sub("[person]", value)
    if len(value) > max_chars:
        value = value[:max_chars] + "\u2026"
    return value


class TraceLogger:
    """No-op trace logger; subclass to add LangFuse or other backends."""

    def __init__(self) -> None:
        self._trace_id: str = ""
        self._steps: List[TraceStep] = []
        self._metadata: Dict[str, Any] = {}

    @classmethod
    def no_op(cls) -> TraceLogger:
        """Return a no-op instance."""
        return cls()

    def start_trace(self, *, trace_id: Optional[str] = None, tags: Optional[dict] = None) -> None:
        self._trace_id = trace_id or str(uuid.uuid4())
        self._steps = []
        # SHA-20 Phase 3+8: preserve trace-level tags as metadata so they
        # make it into the returned TraceSummary even on the no-op path.
        # ``None`` values are dropped so the trace store doesn't carry
        # empty placeholder fields.
        self._metadata = {
            k: v for k, v in (tags or {}).items() if v is not None
        }

    def record_step(self, step: TraceStep) -> None:
        self._steps.append(step)

    def end_trace(self, *, termination: TraceTerminationReason) -> TraceSummary:
        if not self._trace_id:
            self._trace_id = str(uuid.uuid4())
        return TraceSummary(
            trace_id=self._trace_id,
            termination=termination,
            total_duration_ms=sum(s.duration_ms for s in self._steps),
            total_tokens_in=sum(s.tokens_in or 0 for s in self._steps),
            total_tokens_out=sum(s.tokens_out or 0 for s in self._steps),
            steps=list(self._steps),
            metadata=dict(self._metadata),
        )


class LangFuseTraceLogger(TraceLogger):
    """LangFuse-backed TraceLogger that also keeps the no-op in-memory trace.

    Falls back to pure in-memory behavior if langfuse isn't installed or
    initialization fails.
    """

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        dispute_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._session_id = session_id
        self._user_id = user_id
        self._dispute_id = dispute_id
        self._client = None
        self._root_trace = None
        try:
            from langfuse import Langfuse  # type: ignore

            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
        except Exception as exc:  # pragma: no cover - init failure is logged
            import structlog

            structlog.get_logger().warning(
                "langfuse_init_failed",
                error=str(exc),
            )
            self._client = None

    def start_trace(
        self,
        *,
        trace_id: Optional[str] = None,
        tags: Optional[dict] = None,
    ) -> None:
        super().start_trace(trace_id=trace_id, tags=tags)
        if self._client is None:
            return
        try:
            # SHA-20 Phase 8: drop ``None`` tag values before forwarding to
            # LangFuse — the LangFuse UI shows empty cells for ``None``,
            # which dilutes signal for downstream eval reviewers.
            cleaned_tags = {
                k: v for k, v in (tags or {}).items() if v is not None
            }
            self._root_trace = self._client.trace(
                id=self._trace_id,
                session_id=self._session_id,
                user_id=self._user_id,
                metadata={
                    "dispute_id": self._dispute_id,
                    **cleaned_tags,
                },
            )
        except Exception:  # pragma: no cover
            self._root_trace = None

    def record_step(self, step: TraceStep) -> None:
        super().record_step(step)
        if self._root_trace is None:
            return
        try:
            self._root_trace.span(
                name=step.name or step.kind,
                input=step.input_preview,
                output=step.output_preview,
                metadata={
                    "kind": step.kind,
                    "duration_ms": step.duration_ms,
                    "tokens_in": step.tokens_in,
                    "tokens_out": step.tokens_out,
                    "is_error": step.is_error,
                },
                level="ERROR" if step.is_error else "DEFAULT",
            )
        except Exception:  # pragma: no cover
            pass

    def end_trace(self, *, termination: TraceTerminationReason) -> TraceSummary:
        summary = super().end_trace(termination=termination)
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:  # pragma: no cover
                pass
        return summary
