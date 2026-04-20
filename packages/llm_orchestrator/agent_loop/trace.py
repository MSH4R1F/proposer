from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel

TraceStepKind = Literal["model_turn", "tool_call", "tool_error", "termination"]


class TraceTerminationReason(str, Enum):
    END_TURN = "end_turn"
    MAX_TURNS = "max_turns"
    MODEL_ERROR = "model_error"


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


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+44\s?|0)7\d{3}\s?\d{6}")
_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b", re.IGNORECASE)


def redact_text(value: str, *, max_chars: int = 500) -> str:
    """Mask UK PII patterns then truncate to max_chars."""
    value = _EMAIL_RE.sub("[email]", value)
    value = _PHONE_RE.sub("[phone]", value)
    value = _POSTCODE_RE.sub("[postcode]", value)
    if len(value) > max_chars:
        value = value[:max_chars] + "\u2026"
    return value


class TraceLogger:
    """No-op trace logger; subclass to add LangFuse or other backends."""

    def __init__(self) -> None:
        self._trace_id: str = ""
        self._steps: List[TraceStep] = []

    @classmethod
    def no_op(cls) -> TraceLogger:
        """Return a no-op instance."""
        return cls()

    def start_trace(self, *, trace_id: Optional[str] = None, tags: Optional[dict] = None) -> None:
        self._trace_id = trace_id or str(uuid.uuid4())
        self._steps = []

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
        )
