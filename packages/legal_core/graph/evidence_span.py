"""EvidenceSpan: typed reference to a source-text span supporting a factor.

Per spec §5 + §17.6, every persisted FactorAssertion that isn't deterministic
must reference at least one EvidenceSpan via its supported_by list. The span
itself records the verbatim quote, source, and (optional) paragraph range so
the citation verifier (PR 6) can re-locate the evidence in the original text.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceSourceKind(str, Enum):
    """Closed enum of where evidence can come from."""

    USER_NARRATIVE = "user_narrative"
    USER_UPLOADED_DOCUMENT = "user_uploaded_document"
    OMBUDSMAN_DETERMINATION = "ombudsman_determination"
    TRIBUNAL_DECISION = "tribunal_decision"
    STATUTE = "statute"
    GUIDANCE = "guidance"
    CALCULATOR_TRACE = "calculator_trace"


class EvidenceSpan(BaseModel):
    """Typed reference to a span of source text. See spec §5."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_span_id: str
    source_kind: EvidenceSourceKind
    source_reference: str  # e.g. "tenant_narrative.txt" or case ID
    quote_text: str = Field(min_length=1)
    paragraph_range: Optional[str] = None  # e.g. "¶12-¶14"
