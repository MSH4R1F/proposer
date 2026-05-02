"""Domain models for proposition extraction (SHA-36 Phase 1).

These Pydantic v2 models describe atomic legal propositions extracted from
tribunal decision documents, the runs that produced them, and the typed
edges linking propositions within a single document.

Pure domain layer — no DB, no LLM, no I/O. Storage adapters and the
extractor pipeline live elsewhere (Tasks 2+).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from uuid import NAMESPACE_OID, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PropositionType(str, Enum):
    """Coarse type of an atomic legal proposition."""

    fact = "fact"
    rule = "rule"
    outcome = "outcome"
    authority = "authority"


class PropositionEdgeType(str, Enum):
    """Typed link between two propositions within a single document."""

    supports = "supports"
    contradicts = "contradicts"
    cites = "cites"
    temporal_before = "temporal_before"
    applies_rule_to_fact = "applies_rule_to_fact"


class ExtractionRunStatus(str, Enum):
    """Lifecycle status of one extractor run against one document."""

    started = "started"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_WHITESPACE_RE = re.compile(r"\s+")


def sha256_hex(text: str) -> str:
    """Hex-digest sha256 of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_for_matching(text: str) -> str:
    """Normalize text for quote-verification matching.

    NFKC unicode normalize + collapse all runs of whitespace to a single space
    + strip. Preserves case and punctuation so legal citations and paragraph
    numbers (e.g. "Section 213(3).") survive intact.
    """
    normalized = unicodedata.normalize("NFKC", text)
    collapsed = _WHITESPACE_RE.sub(" ", normalized)
    return collapsed.strip()


def deterministic_document_id(source_key: str, content_sha256: str) -> UUID:
    """Stable UUID5 for a decision document.

    `source_key` is a canonical identifier — typically the source URL or local
    path. Combined with the content hash so re-fetches of the same URI with
    different content get a new id.
    """
    return uuid5(NAMESPACE_OID, f"{source_key}|{content_sha256}")


def deterministic_proposition_id(
    document_id: UUID,
    paragraph_ref: Optional[str],
    source_passage: str,
    proposition_type: PropositionType,
    text: str,
) -> UUID:
    """Stable UUID5 for a proposition.

    Hashes long strings before composing the namespace key so passages don't
    bloat the input. Includes proposition_type so the same passage/text under
    a different type gets a distinct id.
    """
    key = (
        f"{document_id}|"
        f"{paragraph_ref or ''}|"
        f"{proposition_type.value}|"
        f"{sha256_hex(source_passage)}|"
        f"{sha256_hex(text)}"
    )
    return uuid5(NAMESPACE_OID, key)


def deterministic_edge_id(
    from_id: UUID, to_id: UUID, edge_type: PropositionEdgeType
) -> UUID:
    """Stable UUID5 for a (from, to, type) edge triple."""
    return uuid5(NAMESPACE_OID, f"{from_id}|{to_id}|{edge_type.value}")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DecisionDocument(BaseModel):
    """One source decision (BAILII PDF/HTML or local fixture).

    Independent of Proposer user cases — this is the immutable substrate the
    proposition KG is built on top of.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    case_reference: str = Field(min_length=1, max_length=128)
    source_url: Optional[str] = None
    local_path: Optional[str] = None
    year: Optional[int] = None
    category: Optional[str] = None
    case_type_code: Optional[str] = None
    region_code: Optional[str] = None
    decision_date: Optional[date] = None
    content_sha256: str
    text_sha256: str
    char_count: int = Field(ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)
    extraction_method: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

    @field_validator("content_sha256", "text_sha256")
    @classmethod
    def _check_hex64(cls, value: str) -> str:
        if not _HEX64_RE.match(value):
            raise ValueError("must be a 64-character lowercase hex sha256 digest")
        return value


class PropositionExtractionRun(BaseModel):
    """One run of the extractor against one decision document."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    extractor_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    prompt_sha256: str
    model: str
    status: ExtractionRunStatus
    input_chars: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    proposition_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    tokens_in: Optional[int] = Field(default=None, ge=0)
    tokens_out: Optional[int] = Field(default=None, ge=0)
    error_message: Optional[str] = Field(default=None, max_length=2000)
    created_at: Optional[datetime] = None

    @field_validator("prompt_sha256")
    @classmethod
    def _check_prompt_sha(cls, value: str) -> str:
        if not _HEX64_RE.match(value):
            raise ValueError("prompt_sha256 must be a 64-character lowercase hex digest")
        return value


class Proposition(BaseModel):
    """An atomic legal proposition with provenance back to its source passage."""

    model_config = ConfigDict(extra="forbid")

    proposition_id: UUID
    document_id: UUID
    run_id: Optional[UUID] = None
    case_reference: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=500)
    source_passage: str = Field(min_length=1, max_length=1500)
    paragraph_ref: Optional[str] = Field(default=None, max_length=64)
    source_start_char: Optional[int] = Field(default=None, ge=0)
    source_end_char: Optional[int] = Field(default=None, ge=0)
    page_start: Optional[int] = Field(default=None, ge=1)
    page_end: Optional[int] = Field(default=None, ge=1)
    proposition_type: PropositionType
    issue_tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _check_spans(self) -> "Proposition":
        if (
            self.source_start_char is not None
            and self.source_end_char is not None
            and self.source_end_char < self.source_start_char
        ):
            raise ValueError(
                "source_end_char must be >= source_start_char"
            )
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be >= page_start")
        return self


class PropositionEdge(BaseModel):
    """Typed link between two propositions in the same document."""

    model_config = ConfigDict(extra="forbid")

    edge_id: UUID = Field(default_factory=uuid4)
    from_proposition_id: UUID
    to_proposition_id: UUID
    document_id: UUID
    edge_type: PropositionEdgeType
    rationale: Optional[str] = Field(default=None, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _no_self_loop(self) -> "PropositionEdge":
        if self.from_proposition_id == self.to_proposition_id:
            raise ValueError(
                "from_proposition_id and to_proposition_id must differ"
            )
        return self


__all__ = [
    "PropositionType",
    "PropositionEdgeType",
    "ExtractionRunStatus",
    "DecisionDocument",
    "PropositionExtractionRun",
    "Proposition",
    "PropositionEdge",
    "deterministic_document_id",
    "deterministic_proposition_id",
    "deterministic_edge_id",
    "normalize_for_matching",
    "sha256_hex",
]
