from __future__ import annotations

import pytest

from apps.api.src.db.uow import UnitOfWork


class _FailingCommitSession:
    def __init__(self) -> None:
        self.closed = False

    async def commit(self) -> None:
        raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_uow_closes_session_when_commit_fails() -> None:
    session = _FailingCommitSession()

    with pytest.raises(RuntimeError, match="commit failed"):
        async with UnitOfWork(lambda: session):
            pass

    assert session.closed is True


@pytest.mark.asyncio
async def test_uow_exposes_propositions_repo(db_sessionmaker) -> None:
    from apps.api.src.db.repositories.propositions_repo import PropositionsRepo

    async with UnitOfWork(db_sessionmaker) as uow:
        assert isinstance(uow.propositions, PropositionsRepo)
