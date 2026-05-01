"""Repository for the Proposition Knowledge Graph (SHA-36).

Maps between Pydantic domain models in `kg_builder.propositions` and the
ORM rows in `apps.api.src.db.models.propositions`. Repos do NOT commit —
the surrounding `UnitOfWork` does.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import (
    DecisionDocumentRow,
    PropositionEdgeRow,
    PropositionExtractionRunRow,
    PropositionRow,
)
from packages.kg_builder.propositions import (
    DecisionDocument,
    ExtractionRunStatus,
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    PropositionExtractionRun,
    PropositionType,
)


# Keys allowed in finish_run(counts=...). Anything else is ignored.
_RUN_COUNT_COLUMNS = {
    "input_chars",
    "chunk_count",
    "proposition_count",
    "edge_count",
    "rejected_count",
    "tokens_in",
    "tokens_out",
}


class PropositionsRepo:
    """Async repository for decision documents, runs, propositions, and edges."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------------
    # Document CRUD
    # ------------------------------------------------------------------

    async def upsert_document(self, doc: DecisionDocument) -> None:
        """Idempotent insert keyed on `document_id`. ON CONFLICT DO NOTHING."""
        values = self._doc_to_values(doc)
        stmt = pg_insert(DecisionDocumentRow).values(**values)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[DecisionDocumentRow.document_id]
        )
        await self._s.execute(stmt)

    async def get_document(self, document_id: UUID) -> Optional[DecisionDocument]:
        row = await self._s.get(DecisionDocumentRow, document_id)
        return self._row_to_doc(row) if row else None

    async def get_document_by_hash(
        self, content_sha256: str
    ) -> Optional[DecisionDocument]:
        result = await self._s.execute(
            select(DecisionDocumentRow).where(
                DecisionDocumentRow.content_sha256 == content_sha256
            )
        )
        row = result.scalar_one_or_none()
        return self._row_to_doc(row) if row else None

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    async def create_run(self, run: PropositionExtractionRun) -> None:
        """Pass-through insert. Caller has handled --resume dedup."""
        values = self._run_to_values(run)
        self._s.add(PropositionExtractionRunRow(**values))
        await self._s.flush()

    async def finish_run(
        self,
        run_id: UUID,
        *,
        status: ExtractionRunStatus,
        counts: dict[str, Any],
        error_message: Optional[str] = None,
    ) -> None:
        """UPDATE the run row. Only count keys present in `counts` are written.

        `status` is always updated. `error_message` is always written (pass
        None to clear).
        """
        update_values: dict[str, Any] = {
            "status": status.value,
            "error_message": error_message,
        }
        for key in _RUN_COUNT_COLUMNS:
            if key in counts:
                update_values[key] = counts[key]
        await self._s.execute(
            update(PropositionExtractionRunRow)
            .where(PropositionExtractionRunRow.run_id == run_id)
            .values(**update_values)
        )

    # ------------------------------------------------------------------
    # Bulk upserts
    # ------------------------------------------------------------------

    async def bulk_upsert_propositions(
        self, props: Sequence[Proposition]
    ) -> int:
        """Insert all propositions; ON CONFLICT (proposition_id) DO NOTHING.

        Returns the count of rows actually inserted (suppressed conflicts are
        not counted).
        """
        if not props:
            return 0
        rows = [self._prop_to_values(p) for p in props]
        stmt = (
            pg_insert(PropositionRow)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=[PropositionRow.proposition_id]
            )
            .returning(PropositionRow.proposition_id)
        )
        result = await self._s.execute(stmt)
        return len(result.fetchall())

    async def bulk_upsert_edges(
        self, edges: Sequence[PropositionEdge]
    ) -> int:
        """Insert all edges; ON CONFLICT on (from, to, edge_type) DO NOTHING."""
        if not edges:
            return 0
        rows = [self._edge_to_values(e) for e in edges]
        stmt = (
            pg_insert(PropositionEdgeRow)
            .values(rows)
            .on_conflict_do_nothing(
                constraint="uq_proposition_edges_triple",
            )
            .returning(PropositionEdgeRow.edge_id)
        )
        result = await self._s.execute(stmt)
        return len(result.fetchall())

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    async def list_by_case(self, case_reference: str) -> list[Proposition]:
        result = await self._s.execute(
            select(PropositionRow)
            .where(PropositionRow.case_reference == case_reference)
            .order_by(
                PropositionRow.paragraph_ref.asc().nulls_last(),
                PropositionRow.proposition_id.asc(),
            )
        )
        return [self._row_to_prop(r) for r in result.scalars()]

    async def list_by_document(self, document_id: UUID) -> list[Proposition]:
        result = await self._s.execute(
            select(PropositionRow)
            .where(PropositionRow.document_id == document_id)
            .order_by(
                PropositionRow.paragraph_ref.asc().nulls_last(),
                PropositionRow.proposition_id.asc(),
            )
        )
        return [self._row_to_prop(r) for r in result.scalars()]

    async def list_edges_for_document(
        self, document_id: UUID
    ) -> list[PropositionEdge]:
        result = await self._s.execute(
            select(PropositionEdgeRow)
            .where(PropositionEdgeRow.document_id == document_id)
            .order_by(PropositionEdgeRow.edge_id.asc())
        )
        return [self._row_to_edge(r) for r in result.scalars()]

    async def list_neighbors(
        self,
        proposition_id: UUID,
        *,
        edge_types: Optional[Sequence[PropositionEdgeType]] = None,
    ) -> list[Proposition]:
        """Outgoing-only neighbors of `proposition_id`.

        If `edge_types` is provided, only edges of those types are followed.
        Phase 1 is non-transitive — Phase 2 PageRank does its own traversal.
        """
        join_condition = PropositionRow.proposition_id == PropositionEdgeRow.to_proposition_id
        stmt = (
            select(PropositionRow)
            .join(PropositionEdgeRow, join_condition)
            .where(PropositionEdgeRow.from_proposition_id == proposition_id)
        )
        if edge_types:
            stmt = stmt.where(
                PropositionEdgeRow.edge_type.in_([t.value for t in edge_types])
            )
        stmt = stmt.order_by(
            PropositionRow.paragraph_ref.asc().nulls_last(),
            PropositionRow.proposition_id.asc(),
        )
        result = await self._s.execute(stmt)
        return [self._row_to_prop(r) for r in result.scalars()]

    # ------------------------------------------------------------------
    # Domain ↔ Row mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _doc_to_values(doc: DecisionDocument) -> dict[str, Any]:
        values: dict[str, Any] = dict(
            document_id=doc.document_id,
            case_reference=doc.case_reference,
            source_url=doc.source_url,
            local_path=doc.local_path,
            year=doc.year,
            category=doc.category,
            case_type_code=doc.case_type_code,
            region_code=doc.region_code,
            decision_date=doc.decision_date,
            content_sha256=doc.content_sha256,
            text_sha256=doc.text_sha256,
            char_count=doc.char_count,
            page_count=doc.page_count,
            extraction_method=doc.extraction_method,
            metadata_=dict(doc.metadata),
        )
        if doc.created_at is not None:
            values["created_at"] = doc.created_at
        return values

    @staticmethod
    def _row_to_doc(row: DecisionDocumentRow) -> DecisionDocument:
        return DecisionDocument(
            document_id=row.document_id,
            case_reference=row.case_reference,
            source_url=row.source_url,
            local_path=row.local_path,
            year=row.year,
            category=row.category,
            case_type_code=row.case_type_code,
            region_code=row.region_code,
            decision_date=row.decision_date,
            content_sha256=row.content_sha256,
            text_sha256=row.text_sha256,
            char_count=row.char_count,
            page_count=row.page_count,
            extraction_method=row.extraction_method,
            metadata=dict(row.metadata_ or {}),
            created_at=row.created_at,
        )

    @staticmethod
    def _run_to_values(run: PropositionExtractionRun) -> dict[str, Any]:
        values: dict[str, Any] = dict(
            run_id=run.run_id,
            document_id=run.document_id,
            extractor_version=run.extractor_version,
            prompt_version=run.prompt_version,
            prompt_sha256=run.prompt_sha256,
            model=run.model,
            status=run.status.value,
            input_chars=run.input_chars,
            chunk_count=run.chunk_count,
            proposition_count=run.proposition_count,
            edge_count=run.edge_count,
            rejected_count=run.rejected_count,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            error_message=run.error_message,
        )
        if run.created_at is not None:
            values["created_at"] = run.created_at
        return values

    @staticmethod
    def _prop_to_values(p: Proposition) -> dict[str, Any]:
        values: dict[str, Any] = dict(
            proposition_id=p.proposition_id,
            document_id=p.document_id,
            run_id=p.run_id,
            case_reference=p.case_reference,
            text=p.text,
            source_passage=p.source_passage,
            paragraph_ref=p.paragraph_ref,
            source_start_char=p.source_start_char,
            source_end_char=p.source_end_char,
            page_start=p.page_start,
            page_end=p.page_end,
            proposition_type=p.proposition_type.value,
            issue_tags=list(p.issue_tags),
            entities=list(p.entities),
            confidence=float(p.confidence),
        )
        if p.created_at is not None:
            values["created_at"] = p.created_at
        return values

    @staticmethod
    def _row_to_prop(row: PropositionRow) -> Proposition:
        return Proposition(
            proposition_id=row.proposition_id,
            document_id=row.document_id,
            run_id=row.run_id,
            case_reference=row.case_reference,
            text=row.text,
            source_passage=row.source_passage,
            paragraph_ref=row.paragraph_ref,
            source_start_char=row.source_start_char,
            source_end_char=row.source_end_char,
            page_start=row.page_start,
            page_end=row.page_end,
            proposition_type=PropositionType(row.proposition_type),
            issue_tags=list(row.issue_tags or []),
            entities=list(row.entities or []),
            confidence=float(row.confidence),
            created_at=row.created_at,
        )

    @staticmethod
    def _edge_to_values(edge: PropositionEdge) -> dict[str, Any]:
        values: dict[str, Any] = dict(
            edge_id=edge.edge_id,
            from_proposition_id=edge.from_proposition_id,
            to_proposition_id=edge.to_proposition_id,
            document_id=edge.document_id,
            edge_type=edge.edge_type.value,
            rationale=edge.rationale,
            confidence=float(edge.confidence),
        )
        if edge.created_at is not None:
            values["created_at"] = edge.created_at
        return values

    @staticmethod
    def _row_to_edge(row: PropositionEdgeRow) -> PropositionEdge:
        return PropositionEdge(
            edge_id=row.edge_id,
            from_proposition_id=row.from_proposition_id,
            to_proposition_id=row.to_proposition_id,
            document_id=row.document_id,
            edge_type=PropositionEdgeType(row.edge_type),
            rationale=row.rationale,
            confidence=float(row.confidence),
            created_at=row.created_at,
        )
