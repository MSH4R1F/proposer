"""SHA-20 Phase 4: SourceMetadata schema for retrieval/ingestion.

This module defines :class:`SourceMetadata`, the canonical per-document /
per-chunk metadata bag that crosses every layer of the RAG engine:

* parsed during ingestion from the source publisher,
* embedded into each :class:`~rag_engine.config.DocumentChunk`,
* projected to the Chroma metadata dict and BM25 metadata dict,
* read back in the citation verifier and citation mapper.

It is a *strict* Pydantic v2 model (``extra="forbid"``) so additions are
intentional. The fields mirror the Phase 4 spec in
``docs/superpowers/plans/2026-05-01-sha-20-multi-domain-architecture-implementation.md``.

Naming notes
------------
* ``te3s`` in namespace and corpus paths refers to the OpenAI embedding
  model ``text-embedding-3-small``. Embedding-model changes trigger a full
  rebuild and a new ``corpus_version`` because vectors are not portable
  across models.
* ``chunk_kind`` is intentionally typed via the canonical
  :class:`domain_core.spec.ChunkKind` so the SHA-36 Proposition KG seam
  (proposition chunks alongside document chunks) needs no API change.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain_core.spec import (
    ChunkKind,
    Forum,
    SourceKind,
    SourcePublisher,
)


class SourceMetadata(BaseModel):
    """Canonical per-source metadata bag (document- or chunk-level).

    This is the union of fields the Phase 4 plan requires. Any field that
    is genuinely document-level (e.g. ``decision_date``) is also valid at
    the chunk level — chunks inherit their document's metadata.

    All path-like / URL fields are stored as strings (POSIX-style for paths)
    so that the value survives serialization to ChromaDB metadata, which
    only accepts scalar strings/ints/floats/bools.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    # Domain routing -----------------------------------------------------
    domain_id: str = Field(..., description="DomainId, e.g. 'housing.deposit.v1'.")
    domain_family: str = Field(..., description="DomainFamily value, e.g. 'housing'.")
    forum: Forum = Field(..., description="Adjudicating forum.")

    # Source identity ----------------------------------------------------
    source_id: str = Field(
        ...,
        description=(
            "Stable, unique identifier for the source document within "
            "its publisher (e.g. case_reference, statute section id, "
            "ombudsman case number)."
        ),
    )
    source_publisher: SourcePublisher = Field(...)
    source_kind: SourceKind = Field(...)

    # Subject / temporal -------------------------------------------------
    matter_types: List[str] = Field(
        default_factory=list,
        description=(
            "Domain-defined matter type tags this source is relevant to "
            "(e.g. 'deposit_deduction')."
        ),
    )
    decision_date: Optional[date] = Field(
        None, description="Date the decision was issued (for case_decision/ombudsman)."
    )
    law_effective_date: Optional[date] = Field(
        None,
        description=(
            "Effective date of the statute / guidance text this chunk "
            "represents (for point-in-time retrieval)."
        ),
    )

    # URLs / licensing ---------------------------------------------------
    source_url: Optional[str] = Field(
        None, description="Canonical (publisher-supplied) URL for the source."
    )
    source_license: Optional[str] = Field(
        None,
        description=(
            "Licensing string (SPDX-ish or human-readable). "
            "Used by the citation mapper / disclaimers."
        ),
    )
    canonical_url: Optional[str] = Field(
        None,
        description=(
            "URL the citation mapper resolved for this source, possibly "
            "with point-in-time params."
        ),
    )

    # Corpus versioning --------------------------------------------------
    corpus_version: str = Field(
        ...,
        description=(
            "Version label of the corpus snapshot this source belongs to "
            "(e.g. 'legacy_2025_pre_sha20', '2026Q2_te3s')."
        ),
    )
    parser_version: str = Field(
        ...,
        description=(
            "Version of the parser/extractor that produced this chunk. "
            "Used by gates: parser bump => corpus rebuild required."
        ),
    )
    content_sha256: Optional[str] = Field(
        None,
        description=(
            "Hex sha256 of the canonical text content (post-cleaning) "
            "for dedup and integrity checks."
        ),
    )

    # Citation / chunk shape --------------------------------------------
    case_reference: Optional[str] = Field(
        None,
        description=(
            "Free-form case reference string (legacy field used by the "
            "deposit pipeline). Stored alongside source_id for compat."
        ),
    )
    chunk_kind: ChunkKind = Field(
        default=ChunkKind.DOCUMENT_CHUNK,
        description=(
            "Whether this row is a document chunk or a decomposed "
            "proposition (SHA-36 seam)."
        ),
    )
    page: Optional[int] = Field(None, ge=0, description="1-based page number, if known.")
    paragraph: Optional[int] = Field(
        None, ge=0, description="1-based paragraph number within the source, if known."
    )
    char_start: Optional[int] = Field(
        None, ge=0, description="Character offset of the chunk's start in the source."
    )
    char_end: Optional[int] = Field(
        None,
        ge=0,
        description="Character offset of the chunk's end (exclusive) in the source.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("source_id", "domain_id", "domain_family", "corpus_version", "parser_version")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("required string field must be non-empty")
        return v

    @field_validator("char_end")
    @classmethod
    def _char_end_after_start(cls, v: Optional[int], info) -> Optional[int]:
        start = info.data.get("char_start") if hasattr(info, "data") else None
        if v is not None and start is not None and v < start:
            raise ValueError("char_end must be >= char_start")
        return v

    # ------------------------------------------------------------------
    # Projections
    # ------------------------------------------------------------------

    def to_chroma_metadata(self) -> Dict[str, Any]:
        """Project to ChromaDB-safe scalars.

        ChromaDB only accepts ``str | int | float | bool`` values, so all
        enums are projected to ``.value`` and dates to ISO strings.
        ``matter_types`` is joined with ``|`` (and re-split on read) — Chroma
        does not accept lists.
        """
        out: Dict[str, Any] = {
            "domain_id": self.domain_id,
            "domain_family": self.domain_family,
            "forum": self.forum.value,
            "source_id": self.source_id,
            "source_publisher": self.source_publisher.value,
            "source_kind": self.source_kind.value,
            "matter_types": "|".join(self.matter_types) if self.matter_types else "",
            "corpus_version": self.corpus_version,
            "parser_version": self.parser_version,
            "chunk_kind": self.chunk_kind.value,
        }
        if self.decision_date is not None:
            out["decision_date"] = self.decision_date.isoformat()
        if self.law_effective_date is not None:
            out["law_effective_date"] = self.law_effective_date.isoformat()
        if self.source_url:
            out["source_url"] = self.source_url
        if self.canonical_url:
            out["canonical_url"] = self.canonical_url
        if self.source_license:
            out["source_license"] = self.source_license
        if self.content_sha256:
            out["content_sha256"] = self.content_sha256
        if self.case_reference:
            out["case_reference"] = self.case_reference
        if self.page is not None:
            out["page"] = self.page
        if self.paragraph is not None:
            out["paragraph"] = self.paragraph
        if self.char_start is not None:
            out["char_start"] = self.char_start
        if self.char_end is not None:
            out["char_end"] = self.char_end
        return out

    @classmethod
    def from_chroma_metadata(cls, meta: Dict[str, Any]) -> "SourceMetadata":
        """Reverse of :meth:`to_chroma_metadata` — best-effort.

        Used by hybrid retrieval / citation verification to reconstruct a
        SourceMetadata from a row's persisted Chroma scalars.
        Missing required fields will raise ``ValidationError``.
        """
        raw_matter = meta.get("matter_types", "")
        matter_types: List[str]
        if isinstance(raw_matter, list):
            matter_types = [str(m) for m in raw_matter]
        elif raw_matter:
            matter_types = [m for m in str(raw_matter).split("|") if m]
        else:
            matter_types = []

        def _date(key: str) -> Optional[date]:
            v = meta.get(key)
            if not v:
                return None
            try:
                return date.fromisoformat(str(v))
            except ValueError:
                return None

        return cls(
            domain_id=str(meta["domain_id"]),
            domain_family=str(meta["domain_family"]),
            forum=Forum(meta["forum"]),
            source_id=str(meta["source_id"]),
            source_publisher=SourcePublisher(meta["source_publisher"]),
            source_kind=SourceKind(meta["source_kind"]),
            matter_types=matter_types,
            decision_date=_date("decision_date"),
            law_effective_date=_date("law_effective_date"),
            source_url=meta.get("source_url"),
            source_license=meta.get("source_license"),
            canonical_url=meta.get("canonical_url"),
            corpus_version=str(meta["corpus_version"]),
            parser_version=str(meta["parser_version"]),
            content_sha256=meta.get("content_sha256"),
            case_reference=meta.get("case_reference"),
            chunk_kind=ChunkKind(meta.get("chunk_kind", ChunkKind.DOCUMENT_CHUNK.value)),
            page=meta.get("page"),
            paragraph=meta.get("paragraph"),
            char_start=meta.get("char_start"),
            char_end=meta.get("char_end"),
        )


__all__ = ["SourceMetadata"]
