from __future__ import annotations

from types import TracebackType
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.db.repositories import (
    DisputesRepo,
    EvidenceRepo,
    KnowledgeGraphRepo,
    MediationsRepo,
    PredictionsRepo,
    PropositionsRepo,
    SessionsRepo,
)


class UnitOfWork:
    """Request/service-operation transaction boundary for Postgres repos."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self.session: AsyncSession
        self.sessions: SessionsRepo
        self.disputes: DisputesRepo
        self.predictions: PredictionsRepo
        self.knowledge_graphs: KnowledgeGraphRepo
        self.mediations: MediationsRepo
        self.evidence: EvidenceRepo
        self.propositions: PropositionsRepo

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._sessionmaker()
        self.sessions = SessionsRepo(self.session)
        self.disputes = DisputesRepo(self.session)
        self.predictions = PredictionsRepo(self.session)
        self.knowledge_graphs = KnowledgeGraphRepo(self.session)
        self.mediations = MediationsRepo(self.session)
        self.evidence = EvidenceRepo(self.session)
        self.propositions = PropositionsRepo(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
