"""SHA-20 Phase 4 ingestion data models.

See ``rag_engine.ingestion`` for the high-level contract. The four models
here are intentionally minimal and append-only — anything not listed
must not be added without bumping ``parser_version``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain_core.spec import ChunkKind, Forum

from ..source_metadata import SourceMetadata


class SourceDocument(BaseModel):
    """One publisher document — a single decision PDF, ombudsman decision
    page, or statute section.

    Carries every :class:`SourceMetadata` field at the document level via
    composition (``metadata: SourceMetadata``). ``raw_text`` is the
    canonical post-cleaning text; chunkers consume this.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    metadata: SourceMetadata
    raw_text: str = Field(..., description="Canonical cleaned text of the document.")
    title: Optional[str] = Field(None, description="Human-readable document title.")
    storage_path: Optional[str] = Field(
        None, description="On-disk POSIX path to the raw publisher artefact."
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Publisher-specific fields not in SourceMetadata (parsed JSON, OCR notes).",
    )

    @field_validator("raw_text")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("raw_text must be non-empty")
        return v


class SourceChunk(BaseModel):
    """One chunk derived from a :class:`SourceDocument`.

    Carries the same :class:`SourceMetadata` (with chunk-level overrides
    of ``chunk_kind``, ``page``, ``paragraph``, ``char_start``,
    ``char_end``) plus the chunk text and a stable ``chunk_id``.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    chunk_id: str = Field(..., description="Stable, globally-unique chunk id.")
    metadata: SourceMetadata
    text: str = Field(..., description="Chunk text content.")
    token_count: int = Field(default=0, ge=0)

    @field_validator("text")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("chunk text must be non-empty")
        return v

    @model_validator(mode="after")
    def _check_chunk_kind_present(self) -> "SourceChunk":
        # SHA-36 seam: chunk_kind must be present on the chunk's metadata.
        if not isinstance(self.metadata.chunk_kind, ChunkKind):
            raise ValueError("metadata.chunk_kind must be a ChunkKind enum")
        return self


class CorpusManifest(BaseModel):
    """Describes a built corpus version (the *result* of one or more
    ingestion runs).

    Distinct from :class:`IngestionRunManifest`, which logs the *act*
    of ingestion. A single corpus version may be produced by multiple
    ingestion runs (e.g. incremental backfill).
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    domain_id: str
    domain_family: str
    forum: Forum
    corpus_version: str
    embed_model: str = Field(
        ..., description="OpenAI embedding model id, e.g. 'text-embedding-3-small'."
    )
    parser_version: str
    ingestion_started_at: datetime
    ingestion_finished_at: datetime
    total_documents: int = Field(..., ge=0)
    total_chunks: int = Field(..., ge=0)
    chunk_kind_counts: Dict[str, int] = Field(default_factory=dict)
    content_sha256_summary: Optional[str] = Field(
        None,
        description="Aggregate sha256 over per-document content_sha256 (audit trail).",
    )

    @model_validator(mode="after")
    def _check_dates(self) -> "CorpusManifest":
        if self.ingestion_finished_at < self.ingestion_started_at:
            raise ValueError("ingestion_finished_at must be >= ingestion_started_at")
        return self

    @field_validator("chunk_kind_counts")
    @classmethod
    def _check_chunk_kind_counts_keys(cls, v: Dict[str, int]) -> Dict[str, int]:
        valid = {ck.value for ck in ChunkKind}
        for k in v:
            if k not in valid:
                raise ValueError(
                    f"chunk_kind_counts has unknown ChunkKind {k!r}; "
                    f"allowed: {sorted(valid)}"
                )
        return v


class IngestionRunManifest(BaseModel):
    """Append-only record of one ingestion run.

    Distinct from :class:`CorpusManifest`. We keep *every* run manifest;
    we keep at most a few corpus manifests (the active and rollback
    versions per audit policy).
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    run_id: str = Field(..., description="UUID/ULID for this run.")
    domain_id: str
    corpus_version: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    documents_attempted: int = Field(default=0, ge=0)
    documents_ingested: int = Field(default=0, ge=0)
    documents_skipped: int = Field(default=0, ge=0)
    documents_failed: int = Field(default=0, ge=0)
    chunks_emitted: int = Field(default=0, ge=0)
    parser_version: str
    embed_model: str
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_run_dates(self) -> "IngestionRunManifest":
        if self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        return self


__all__ = [
    "SourceDocument",
    "SourceChunk",
    "CorpusManifest",
    "IngestionRunManifest",
]
