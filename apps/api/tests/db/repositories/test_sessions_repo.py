import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.sessions_repo import SessionsRepo
from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
from packages.llm_orchestrator.models.conversation import (
    ConversationState, IntakeStage,
)


def _make_state(session_id: str = "sess-1", case_id: str = "case-1") -> ConversationState:
    return ConversationState(
        session_id=session_id,
        case_file=CaseFile(case_id=case_id, user_role=PartyRole.TENANT),
        messages=[],
        current_stage=IntakeStage.GREETING,
        started_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        stages_completed=[],
        current_stage_attempts=0,
        last_extraction_successful=True,
        extraction_errors=[],
        role_explicitly_set=False,
    )


@pytest.mark.asyncio
async def test_save_then_get_returns_identical_state(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    original = _make_state()
    await repo.save(original)
    await db_session.commit()

    loaded = await repo.get(original.session_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == original.model_dump(mode="json")


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    assert await repo.get("nope") is None


@pytest.mark.asyncio
async def test_save_is_upsert(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    state = _make_state()
    await repo.save(state)
    await db_session.commit()

    state.current_stage = IntakeStage.BASIC_DETAILS
    await repo.save(state)
    await db_session.commit()

    loaded = await repo.get(state.session_id)
    assert loaded is not None
    assert loaded.current_stage == IntakeStage.BASIC_DETAILS


@pytest.mark.asyncio
async def test_get_by_case_id(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    state = _make_state(session_id="sess-2", case_id="case-2")
    await repo.save(state)
    await db_session.commit()

    loaded = await repo.get_by_case_id("case-2")
    assert loaded is not None
    assert loaded.session_id == "sess-2"


@pytest.mark.asyncio
async def test_delete_removes_row(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    state = _make_state()
    await repo.save(state)
    await db_session.commit()

    await repo.delete(state.session_id)
    await db_session.commit()

    assert await repo.get(state.session_id) is None


@pytest.mark.asyncio
async def test_list_all_returns_all_sessions(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    a = _make_state(session_id="sa", case_id="ca")
    b = _make_state(session_id="sb", case_id="cb")
    await repo.save(a)
    await repo.save(b)
    await db_session.commit()

    listed = {s.session_id for s in await repo.list_all()}
    assert listed == {"sa", "sb"}
