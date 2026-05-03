"""SHA-20 Phase 4 ingestion contract.

Multi-domain corpus ingestion uses a small set of strict Pydantic models
defined in ``contracts.py``:

* :class:`SourceDocument` — one publisher document.
* :class:`SourceChunk` — one chunk derived from a SourceDocument.
* :class:`CorpusManifest` — describes a corpus *version*.
* :class:`IngestionRunManifest` — append-only record of a single
  ingestion run.

The contract is deliberately disjoint from the legacy
``CaseDocument``/``DocumentChunk`` shape — legacy callers that don't pass
a ``SourceMetadata`` keep working, while new callers go through these
models to guarantee the Phase-4 metadata bag is present and validated.
"""

from .adapters import (
    chunk_source_document,
    deterministic_chunk_id,
    source_document_to_case_document,
)
from .contracts import (
    CorpusManifest,
    IngestionRunManifest,
    SourceChunk,
    SourceDocument,
)

__all__ = [
    "CorpusManifest",
    "IngestionRunManifest",
    "SourceChunk",
    "SourceDocument",
    "chunk_source_document",
    "deterministic_chunk_id",
    "source_document_to_case_document",
]
