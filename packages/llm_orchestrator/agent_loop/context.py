from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from .trace import TraceLogger

if TYPE_CHECKING:
    from ..models.prediction_v2 import PredictionResult


@dataclass
class ToolContext:
    """Dependency bundle passed as the first argument to every tool function."""

    rag: Optional[Any] = None
    kg: Optional[Any] = None
    storage: Optional[Any] = None
    dispute_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    trace_logger: TraceLogger = field(default_factory=TraceLogger.no_op)
    redact_pii: bool = True
    prediction: Optional[PredictionResult] = None
    # SHA-20 Phase 3: per-request domain trace tags. Populated by the API
    # layer when a domain runtime context has been resolved; consumed by
    # ``trace_logger.start_trace(tags=...)`` callers to preserve domain
    # routing context in LangFuse / no-op trace output.
    domain_tags: Dict[str, str] = field(default_factory=dict)
