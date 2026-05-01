"""Session-safe read adapter for proposition KG retrieval."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.db.uow import UnitOfWork
from packages.kg_builder.propositions import (
    DecisionDocument,
    Proposition,
    PropositionEdge,
)


class PostgresPropositionGraphStore:
    """Expose PropositionsRepo read methods without holding a live session.

    PredictionEngineV2 is process-cached, so it cannot safely own a repository
    tied to one request's AsyncSession. This adapter keeps only the sessionmaker
    and opens short UnitOfWork scopes for each retrieval read.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def search_by_issue_tags(
        self,
        tags: Sequence[str],
        *,
        limit: int = 50,
    ) -> list[Proposition]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.search_by_issue_tags(tags, limit=limit)

    async def search_by_entities(
        self,
        entities: Sequence[str],
        *,
        limit: int = 50,
    ) -> list[Proposition]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.search_by_entities(entities, limit=limit)

    async def search_text(self, query: str, *, limit: int = 50) -> list[Proposition]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.search_text(query, limit=limit)

    async def load_edges_for_documents(
        self,
        document_ids: Sequence[UUID],
    ) -> list[PropositionEdge]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.load_edges_for_documents(document_ids)

    async def load_propositions_by_ids(
        self,
        proposition_ids: Sequence[UUID],
    ) -> list[Proposition]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.load_propositions_by_ids(proposition_ids)

    async def load_propositions_for_documents(
        self,
        document_ids: Sequence[UUID],
        *,
        limit_per_document: int = 25,
    ) -> list[Proposition]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.load_propositions_for_documents(
                document_ids,
                limit_per_document=limit_per_document,
            )

    async def load_document_metadata(
        self,
        document_ids: Sequence[UUID],
    ) -> dict[UUID, DecisionDocument]:
        async with UnitOfWork(self._sm) as uow:
            return await uow.propositions.load_document_metadata(document_ids)
