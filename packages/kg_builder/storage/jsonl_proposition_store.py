"""JSONL-backed proposition store for the Stream C factor-constrained path.

Implements the duck-typed contract that
``llm_orchestrator.pipeline.factor_retrieval.FactorRetriever`` expects:
``search_by_issue_tags(tags, *, limit=50) -> list[Proposition]``.

The Protocol formally lives at
``llm_orchestrator.pipeline.proposition_retrieval.PropositionGraphRepository``
— we deliberately implement the SAME method signatures so the live
prediction path can use this store as a drop-in for the Postgres-backed
``PropositionGraphRepository`` when running off a JSONL artifact.

Why a new class instead of extending ``JSONGraphStore``?
------------------------------------------------------
``JSONGraphStore`` (in ``json_store.py``) persists ``KnowledgeGraph``
case-graphs — completely different shape. The proposition store reads
the *aggregated* output of the LLM proposition extractor (one proposition
per line, across many cases), which is what ``FactorRetriever``'s seed
pass operates on. Keeping this as a sibling module makes the boundary
clean.

File format: one Pydantic-v2-serialised :class:`Proposition` JSON object
per line, produced by
``scripts/ingestion/dump_propositions_to_jsonl.py`` (or the
``--output-jsonl`` flag on ``ingest_propositions.py``).

Loading is eager + cached at construction time. Corpora seen so far cap
at ~2,400 propositions, so the in-memory dict is small (KBs not MBs).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import structlog

from kg_builder.propositions.models import Proposition

logger = structlog.get_logger()


__all__ = ["JsonlPropositionStore", "load_propositions_from_jsonl"]


def load_propositions_from_jsonl(path: Path) -> List[Proposition]:
    """Read a JSONL file of Pydantic-serialised propositions.

    Skips blank lines. Each non-blank line MUST be a JSON object that
    validates as a :class:`Proposition`; malformed lines raise
    ``pydantic.ValidationError`` so corrupt inputs fail loudly rather
    than silently dropping data.
    """
    if not path.exists():
        raise FileNotFoundError(f"proposition JSONL not found: {path}")

    out: List[Proposition] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid JSON: {exc}"
                ) from exc
            out.append(Proposition.model_validate(payload))
    return out


class JsonlPropositionStore:
    """In-memory, JSONL-backed proposition repository.

    Implements the subset of the
    ``llm_orchestrator.pipeline.proposition_retrieval.PropositionGraphRepository``
    Protocol that
    ``llm_orchestrator.pipeline.factor_retrieval.FactorRetriever``
    actually invokes — namely ``search_by_issue_tags``. The remaining
    Protocol methods (``search_by_entities``, ``search_text``,
    ``load_edges_for_documents``, ``load_propositions_by_ids``,
    ``load_propositions_for_documents``, ``load_document_metadata``)
    are also provided as no-op or trivial implementations so the store
    is a safe drop-in for any caller that accidentally invokes them.
    """

    def __init__(
        self,
        propositions: Optional[Iterable[Proposition]] = None,
        *,
        source_path: Optional[Path] = None,
    ) -> None:
        """Construct from an iterable of validated propositions.

        Args:
            propositions: Pre-loaded :class:`Proposition` instances. If
                ``None``, the store is empty (useful for tests).
            source_path: Optional path that was loaded — recorded for
                debugging only, never read after construction.
        """
        self._source_path = source_path
        self._propositions: List[Proposition] = list(propositions or [])
        self._by_issue_tag: dict[str, List[Proposition]] = {}
        self._index_by_issue_tag()

        logger.info(
            "jsonl_proposition_store_loaded",
            source_path=str(source_path) if source_path else None,
            count=len(self._propositions),
            distinct_issue_tags=len(self._by_issue_tag),
        )

    @classmethod
    def from_path(cls, path: Path) -> "JsonlPropositionStore":
        """Load a store from a JSONL file on disk."""
        propositions = load_propositions_from_jsonl(path)
        return cls(propositions, source_path=path)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _index_by_issue_tag(self) -> None:
        """Build the issue_tag → list[Proposition] inverted index.

        A proposition with multiple issue_tags is indexed under each one
        so a single tag query can pick it up. Order within a bucket
        preserves insertion order (which matches the JSONL file order)
        so callers see deterministic results.
        """
        for prop in self._propositions:
            for tag in prop.issue_tags or []:
                self._by_issue_tag.setdefault(tag, []).append(prop)

    # ------------------------------------------------------------------
    # PropositionGraphRepository duck-type — only ``search_by_issue_tags``
    # is reached by FactorRetriever in the live path. Other methods are
    # implemented as safe no-ops so unrelated callers won't crash.
    # ------------------------------------------------------------------

    async def search_by_issue_tags(
        self,
        tags: Sequence[str],
        *,
        limit: int = 50,
    ) -> List[Proposition]:
        """Return up to *limit* propositions whose issue_tags overlap *tags*.

        Match semantics: a proposition is returned iff at least one of
        its ``issue_tags`` exactly equals one of the requested *tags*.
        De-duplication preserves first-seen order so a proposition with
        two matching tags appears only once.
        """
        if not tags:
            return []
        seen_ids: set = set()
        out: List[Proposition] = []
        for tag in tags:
            for prop in self._by_issue_tag.get(tag, ()):
                if prop.proposition_id in seen_ids:
                    continue
                seen_ids.add(prop.proposition_id)
                out.append(prop)
                if len(out) >= limit:
                    return out
        return out

    async def search_by_entities(
        self,
        entities: Sequence[str],
        *,
        limit: int = 50,
    ) -> List[Proposition]:
        """Trivial entity-overlap search.

        Provided for Protocol completeness; FactorRetriever does not call
        it. Implementation walks the loaded list once per call — fine at
        ~2k propositions.
        """
        if not entities:
            return []
        wanted = set(entities)
        out: List[Proposition] = []
        for prop in self._propositions:
            if wanted.intersection(prop.entities or ()):
                out.append(prop)
                if len(out) >= limit:
                    break
        return out

    async def search_text(
        self,
        query: str,
        *,
        limit: int = 50,
    ) -> List[Proposition]:
        """Case-insensitive substring search on Proposition.text.

        Provided for Protocol completeness. Real text search needs
        embeddings (or a Postgres-side vector index); this is a
        deliberately dumb fallback so the duck-type is satisfied.
        """
        if not query:
            return []
        q = query.lower()
        out: List[Proposition] = []
        for prop in self._propositions:
            if q in (prop.text or "").lower():
                out.append(prop)
                if len(out) >= limit:
                    break
        return out

    async def load_edges_for_documents(self, document_ids):  # noqa: ARG002, ANN001
        """JSONL store does not persist edges. Returns empty list."""
        return []

    async def load_propositions_by_ids(
        self, proposition_ids
    ):  # noqa: ANN001
        """Lookup propositions by their UUIDs.

        Linear scan since the JSONL store is small. Returns the matched
        propositions in the order requested (skipping unknown ids).
        """
        wanted = set(proposition_ids)
        if not wanted:
            return []
        return [p for p in self._propositions if p.proposition_id in wanted]

    async def load_propositions_for_documents(
        self,
        document_ids,
        *,
        limit_per_document: int = 25,
    ):  # noqa: ANN001
        """Group propositions by document_id, capping per document.

        Provided for Protocol completeness; FactorRetriever doesn't call
        this either, but downstream callers might.
        """
        wanted = set(document_ids)
        if not wanted:
            return []
        per_doc_count: dict = {}
        out: List[Proposition] = []
        for prop in self._propositions:
            if prop.document_id not in wanted:
                continue
            seen = per_doc_count.get(prop.document_id, 0)
            if seen >= limit_per_document:
                continue
            per_doc_count[prop.document_id] = seen + 1
            out.append(prop)
        return out

    async def load_document_metadata(self, document_ids):  # noqa: ARG002, ANN001
        """JSONL store does not persist DecisionDocument metadata."""
        return {}

    # ------------------------------------------------------------------
    # Convenience accessors (not part of the Protocol)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._propositions)

    @property
    def propositions(self) -> List[Proposition]:
        """All loaded propositions, in file order."""
        return list(self._propositions)
