"""SHA-125/126 Phase 0: shared ``SourceDocument`` -> chunk bridge.

Scrapers from each domain produce :class:`SourceDocument` instances per
the ingestion contract. The legacy chunking + indexing code, however,
operates on :class:`CaseDocument` / :class:`DocumentChunk`. This adapter
is the single bridge between the two so that:

* Every emitted chunk preserves the originating ``SourceMetadata``.
* Chunk ids are deterministic in
  ``(namespace_id, corpus_version, source_id, chunk_index, content_hash)``
  so re-ingesting the same corpus is a no-op (idempotency).
* All Phase-4 metadata (``domain_id``, ``forum``, ``source_id``,
  ``source_publisher``, ``source_kind``, ``matter_types``,
  ``corpus_version``, ``parser_version``) lands on every chunk.

Callers should prefer this adapter over building ``CaseDocument``
manually; it is the seam SHA-125 (Housing Ombudsman) and SHA-126
(GOV.UK Property Tribunal RRO) ingestion scripts go through.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from domain_core.spec import ChunkKind

from ..config import CaseDocument, DocumentChunk, SectionType
from ..source_metadata import SourceMetadata
from .contracts import SourceDocument

__all__ = [
    "deterministic_chunk_id",
    "source_document_to_case_document",
    "chunk_source_document",
]


def deterministic_chunk_id(
    *,
    namespace_id: str,
    corpus_version: str,
    source_id: str,
    chunk_index: int,
    chunk_text: str,
) -> str:
    """Build a stable chunk id for a (namespace, corpus, source, span).

    The id is intentionally human-readable up to the trailing 8-char
    content hash, which protects against silent text drift: if the
    chunker's output changes, the id changes too. Re-ingesting the
    same corpus in the same order produces identical ids, which is
    what idempotency tests assert against.
    """
    if not namespace_id or not corpus_version or not source_id:
        raise ValueError(
            "namespace_id, corpus_version, and source_id are all required"
        )
    if chunk_index < 0:
        raise ValueError("chunk_index must be >= 0")

    digest = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()[:8]
    return f"{namespace_id}::{corpus_version}::{source_id}::{chunk_index:04d}::{digest}"


def _safe_year(metadata: SourceMetadata) -> int:
    """Pull a chunk-shaped year out of SourceMetadata.

    DocumentChunk.year requires an int 2000-2030 (legacy schema). We
    fall back to a sentinel year inside that window when no decision
    date is available so legacy validation does not fail closed for
    statute / guidance documents.
    """
    if metadata.decision_date is not None:
        y = metadata.decision_date.year
        if 2000 <= y <= 2030:
            return y
    if metadata.law_effective_date is not None:
        y = metadata.law_effective_date.year
        if 2000 <= y <= 2030:
            return y
    return 2000


def source_document_to_case_document(sd: SourceDocument) -> CaseDocument:
    """Project a :class:`SourceDocument` onto the legacy CaseDocument shape.

    Only the fields the chunker reads (``case_reference``, ``year``,
    ``full_text``, ``source_path``, ``metadata`` dict, ``source_metadata``)
    are populated. Section parsing is left to the chunker so this stays
    purely structural.
    """
    metadata = sd.metadata
    case_ref = metadata.case_reference or metadata.source_id
    year = _safe_year(metadata)

    region = None
    case_type = None
    extra = sd.extra or {}
    region = extra.get("region") or region
    case_type = extra.get("case_type") or case_type

    return CaseDocument(
        case_reference=case_ref,
        year=year,
        region=region,
        region_name=extra.get("region_name"),
        case_type=case_type,
        case_type_name=extra.get("case_type_name"),
        title=sd.title,
        decision_date=(
            metadata.decision_date.isoformat() if metadata.decision_date else None
        ),
        full_text=sd.raw_text,
        sections={},
        source_path=sd.storage_path or f"<source:{metadata.source_id}>",
        metadata=dict(extra),
        source_metadata=metadata,
    )


def _build_chunk_metadata(
    *,
    base: SourceMetadata,
    chunk_text: str,
    char_start: int,
    char_end: int,
    section_type: SectionType,
) -> SourceMetadata:
    """Clone the document SourceMetadata onto a chunk with span info."""
    data = base.model_dump()
    # Phase-4: chunk_kind is required on every emitted chunk.
    data["chunk_kind"] = ChunkKind.DOCUMENT_CHUNK
    data["char_start"] = char_start
    data["char_end"] = char_end
    # We let content_sha256 reflect the chunk text, not the parent doc,
    # so chunk-level dedup tools behave correctly downstream.
    data["content_sha256"] = hashlib.sha256(
        chunk_text.encode("utf-8")
    ).hexdigest()
    return SourceMetadata(**data)


def chunk_source_document(
    sd: SourceDocument,
    *,
    namespace_id: str,
    chunker,  # LegalChunker, but typed loose to avoid an import cycle.
) -> List[DocumentChunk]:
    """Chunk a :class:`SourceDocument` into legacy :class:`DocumentChunk`s.

    The output chunks carry:

    * The Phase-4 :class:`SourceMetadata` (with ``chunk_kind``, span
      offsets, and a chunk-level ``content_sha256``).
    * Deterministic chunk ids as built by :func:`deterministic_chunk_id`.

    ``namespace_id`` is the retrieval namespace id (e.g.
    ``housing_repairs_social_v1``); together with
    ``metadata.corpus_version`` it scopes the chunk id space.
    """
    if chunker is None:
        raise ValueError("chunker is required (use LegalChunker)")

    metadata = sd.metadata
    case_doc = source_document_to_case_document(sd)
    legacy_chunks: List[DocumentChunk] = chunker.chunk_document(case_doc)

    out: List[DocumentChunk] = []
    cursor = 0
    raw_text = sd.raw_text
    for idx, chunk in enumerate(legacy_chunks):
        # Try to recover a char span by searching for the chunk text in
        # the raw document. Spans must be monotonic and non-overlapping
        # so downstream citation highlighting/source-snippet code can
        # rely on (char_start, char_end) being unique per chunk.
        #
        # Fallback: if the chunker rewrote characters (whitespace
        # normalisation, etc.), fall back to a synthetic span starting
        # at the current cursor and length-of-chunk wide. Crucially the
        # cursor is advanced unconditionally — otherwise consecutive
        # fallback misses would all stamp the same char_start/char_end
        # onto distinct chunks.
        found = raw_text.find(chunk.text, cursor)
        if found < 0:
            span_start = cursor
        else:
            span_start = found
        span_end = span_start + len(chunk.text)
        cursor = span_end

        chunk_meta = _build_chunk_metadata(
            base=metadata,
            chunk_text=chunk.text,
            char_start=span_start,
            char_end=span_end,
            section_type=chunk.section_type,
        )

        new_chunk_id = deterministic_chunk_id(
            namespace_id=namespace_id,
            corpus_version=metadata.corpus_version,
            source_id=metadata.source_id,
            chunk_index=idx,
            chunk_text=chunk.text,
        )

        out.append(
            DocumentChunk(
                chunk_id=new_chunk_id,
                case_reference=case_doc.case_reference,
                chunk_index=idx,
                text=chunk.text,
                section_type=chunk.section_type,
                year=case_doc.year,
                region=case_doc.region,
                case_type=case_doc.case_type,
                token_count=chunk.token_count,
                source_metadata=chunk_meta,
            )
        )
    return out
