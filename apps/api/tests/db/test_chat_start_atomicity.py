"""Phase 6.3: assert /chat/start writes session+dispute atomically.

If the dispute save fails after the session save, the session save must roll
back too — no orphaned session row in intake_sessions.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from apps.api.src.db.models import DisputeRow, IntakeSessionRow
from apps.api.src.services.intake_service import IntakeService
from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
from packages.llm_orchestrator.models.conversation import (
    ConversationState,
    IntakeStage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(session_id: str, case_id: str) -> ConversationState:
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def intake_service_with_mock_agent(db_sessionmaker):
    agent = AsyncMock()
    state = _make_state("atom-sess-1", "atom-case-1")
    agent.start_conversation.return_value = ("hello", state)
    return IntakeService(sessionmaker=db_sessionmaker, agent=agent)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_start_with_create_dispute_persists_both(
    intake_service_with_mock_agent,
    db_sessionmaker,
):
    """Happy path: session + dispute are both written in one atomic block."""
    greeting, conv, dispute = await intake_service_with_mock_agent.start_session_with_dispute(
        role="tenant",
        create_dispute=True,
    )
    assert greeting == "hello"
    assert dispute is not None
    assert dispute.tenant_session_id == "atom-sess-1"

    async with db_sessionmaker() as session:
        sess_row = await session.get(IntakeSessionRow, "atom-sess-1")
        disp_row = await session.get(DisputeRow, dispute.dispute_id)

    assert sess_row is not None, "session row must be persisted"
    assert disp_row is not None, "dispute row must be persisted"


@pytest.mark.asyncio
async def test_chat_start_rolls_back_when_dispute_save_fails(
    intake_service_with_mock_agent,
    db_sessionmaker,
    monkeypatch,
):
    """If the dispute write blows up, the session write must roll back too."""
    from apps.api.src.db.repositories import disputes_repo as disputes_repo_mod

    async def boom(self, *args, **kwargs):
        raise RuntimeError("simulated dispute save failure")

    monkeypatch.setattr(disputes_repo_mod.DisputesRepo, "save", boom)

    with pytest.raises(RuntimeError, match="simulated dispute save failure"):
        await intake_service_with_mock_agent.start_session_with_dispute(
            role="tenant",
            create_dispute=True,
        )

    # Confirm neither row landed in the database
    async with db_sessionmaker() as session:
        sess_row = await session.get(IntakeSessionRow, "atom-sess-1")
        result = await session.execute(select(DisputeRow))
        disputes = list(result.scalars())

    assert sess_row is None, "session row leaked despite dispute rollback"
    assert disputes == [], "dispute row must not have been committed"


@pytest.mark.asyncio
async def test_chat_start_join_via_invite_code(
    intake_service_with_mock_agent,
    db_sessionmaker,
):
    """Join an existing dispute via invite_code; session + updated dispute persist atomically."""
    from apps.api.src.db.repositories.disputes_repo import DisputesRepo
    from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus

    # Seed an existing dispute with a known invite code.
    # We leave landlord_session_id=None so there is no FK dependency on a
    # non-existent intake_sessions row. The dispute starts with no parties
    # linked; the join will attach the tenant session atomically.
    seed_dispute = DisputeCase(
        dispute_id="DISP-SEED01",
        invite_code="JOIN001",
        status=DisputeStatus.WAITING_FOR_LANDLORD,
        created_at=datetime.now().isoformat(timespec="seconds"),
        updated_at=datetime.now().isoformat(timespec="seconds"),
        created_by_role=PartyRole.LANDLORD.value,
        tenant_session_id=None,
        landlord_session_id=None,
        property_address=None,
        property_postcode=None,
        deposit_amount=None,
    )
    async with db_sessionmaker() as session:
        await DisputesRepo(session).save(seed_dispute)
        await session.commit()

    greeting, conv, dispute = await intake_service_with_mock_agent.start_session_with_dispute(
        role="tenant",
        invite_code="JOIN001",
    )

    assert dispute is not None
    assert dispute.dispute_id == "DISP-SEED01"
    assert dispute.tenant_session_id == "atom-sess-1"

    # Verify both rows are durably written
    async with db_sessionmaker() as session:
        sess_row = await session.get(IntakeSessionRow, "atom-sess-1")
        disp_row = await session.get(DisputeRow, "DISP-SEED01")

    assert sess_row is not None, "session row must be persisted after join"
    assert disp_row is not None, "dispute row must be persisted after join"
