"""
Integration tests for the UoW-backed IntakeService (Phase 6.1).

These tests exercise the full persistence path against a real (migrated)
Postgres database spun up by pytest-postgresql.  The IntakeAgent is mocked
so we never hit the LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
import pytest_asyncio

from apps.api.src.services.dispute_service import DisputeService
from apps.api.src.services.intake_service import IntakeService
from llm_orchestrator.models.case_file import CaseFile, DisputeIssue, PartyRole
from llm_orchestrator.models.conversation import ConversationState, IntakeStage
from llm_orchestrator.models.dispute import DisputeStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_state(
    session_id: str = "test-sess",
    case_id: str = "test-case",
    role: PartyRole = PartyRole.TENANT,
    stage: IntakeStage = IntakeStage.GREETING,
) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        case_file=CaseFile(case_id=case_id, user_role=role),
        messages=[],
        current_stage=stage,
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
async def intake_service(db_sessionmaker):
    """IntakeService wired to a real DB; agent is mocked to avoid LLM calls."""
    agent = AsyncMock()

    # start_conversation → (greeting, ConversationState)
    initial_state = _make_state()
    agent.start_conversation.return_value = ("hello", initial_state)

    # set_user_role → (response_text, updated_state)
    updated_after_role = _make_state(stage=IntakeStage.BASIC_DETAILS)
    updated_after_role.case_file.user_role = PartyRole.TENANT
    updated_after_role.role_explicitly_set = True
    agent.set_user_role.return_value = ("role set", updated_after_role)

    # process_message → (response_text, updated_state)
    updated_after_msg = _make_state(stage=IntakeStage.BASIC_DETAILS)
    agent.process_message.return_value = ("agent reply", updated_after_msg)

    return IntakeService(sessionmaker=db_sessionmaker, agent=agent)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_session_persists_row(intake_service: IntakeService) -> None:
    """start_session must write a row to intake_sessions."""
    greeting, session_id, stage = await intake_service.start_session(role="tenant")

    assert greeting == "hello"
    assert session_id == "test-sess"
    assert stage == IntakeStage.GREETING.value

    # Read it back via the service to confirm persistence
    status = await intake_service.get_session_status(session_id)
    assert status is not None
    assert status["session_id"] == session_id


@pytest.mark.asyncio
async def test_get_session_status_after_start(intake_service: IntakeService) -> None:
    """get_session_status returns the started session without error."""
    _, session_id, _ = await intake_service.start_session(role="tenant")

    status = await intake_service.get_session_status(session_id)

    assert status is not None
    assert status["session_id"] == session_id
    assert status["stage"] == IntakeStage.GREETING.value
    assert isinstance(status["case_file"], dict)


@pytest.mark.asyncio
async def test_get_session_status_unknown_returns_none(intake_service: IntakeService) -> None:
    """get_session_status returns None for an unknown session_id."""
    result = await intake_service.get_session_status("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_set_role_updates_persisted_row(intake_service: IntakeService) -> None:
    """set_role must persist the updated stage/role into the DB."""
    _, session_id, _ = await intake_service.start_session(role="tenant")

    result = await intake_service.set_role(session_id, "tenant")

    assert result["role_set"] is True
    assert result["stage"] == IntakeStage.BASIC_DETAILS.value

    # Reload via get_session_status to confirm persistence
    status = await intake_service.get_session_status(session_id)
    assert status is not None
    assert status["stage"] == IntakeStage.BASIC_DETAILS.value


@pytest.mark.asyncio
async def test_delete_session_removes_row(intake_service: IntakeService) -> None:
    """delete_session returns True and the row is gone afterwards."""
    _, session_id, _ = await intake_service.start_session(role="tenant")

    deleted = await intake_service.delete_session(session_id)
    assert deleted is True

    status = await intake_service.get_session_status(session_id)
    assert status is None


@pytest.mark.asyncio
async def test_delete_session_nonexistent_returns_false(intake_service: IntakeService) -> None:
    """delete_session returns False when the session doesn't exist."""
    deleted = await intake_service.delete_session("ghost-session")
    assert deleted is False


@pytest.mark.asyncio
async def test_list_sessions_returns_all(db_sessionmaker) -> None:
    """list_sessions returns one entry per persisted session."""
    # Build two independent agents so each start_conversation returns a unique state
    agent_a = AsyncMock()
    state_a = _make_state(session_id="sess-a", case_id="case-a")
    agent_a.start_conversation.return_value = ("hi", state_a)

    agent_b = AsyncMock()
    state_b = _make_state(session_id="sess-b", case_id="case-b")
    agent_b.start_conversation.return_value = ("hi", state_b)

    svc_a = IntakeService(sessionmaker=db_sessionmaker, agent=agent_a)
    svc_b = IntakeService(sessionmaker=db_sessionmaker, agent=agent_b)

    await svc_a.start_session(role="tenant")
    await svc_b.start_session(role="landlord")

    # list_sessions uses the same DB, so use either service instance
    sessions = await svc_a.list_sessions()
    session_ids = {s["session_id"] for s in sessions}
    assert "sess-a" in session_ids
    assert "sess-b" in session_ids


@pytest.mark.asyncio
async def test_process_message_syncs_linked_dispute_in_postgres(db_sessionmaker) -> None:
    agent = AsyncMock()
    initial = _make_state(session_id="sync-sess", case_id="sync-case")
    agent.start_conversation.return_value = ("hello", initial)

    completed = _make_state(
        session_id="sync-sess",
        case_id="sync-case",
        stage=IntakeStage.CONFIRMATION,
    )
    completed.case_file.issues = [DisputeIssue.CLEANING]
    completed.case_file.intake_complete = True
    completed.case_file.calculate_completeness()
    agent.process_message.return_value = ("done", completed)

    intake = IntakeService(sessionmaker=db_sessionmaker, agent=agent)
    disputes = DisputeService(sessionmaker=db_sessionmaker)

    _, conversation, dispute = await intake.start_session_with_dispute(
        role="tenant",
        create_dispute=True,
    )
    assert dispute is not None

    await intake.process_message(conversation.session_id, "cleaning dispute details")

    loaded = await disputes.get_dispute(dispute.dispute_id)
    assert loaded is not None
    assert loaded.status == DisputeStatus.TENANT_COMPLETE


@pytest.mark.asyncio
async def test_bulk_intake_with_dispute_marks_party_complete(db_sessionmaker) -> None:
    agent = AsyncMock()
    initial = _make_state(session_id="bulk-sess", case_id="bulk-case")
    agent.start_conversation.return_value = ("hello", initial)

    completed_case = CaseFile(case_id="bulk-case", user_role=PartyRole.TENANT)
    completed_case.issues = [DisputeIssue.CLEANING]
    completed_case.calculate_completeness()
    completed_case.intake_complete = True
    agent.extractor.extract_bulk = AsyncMock(
        return_value=SimpleNamespace(
            updated_case_file=completed_case,
            no_new_info=False,
        )
    )

    intake = IntakeService(sessionmaker=db_sessionmaker, agent=agent)

    _, dispute = await intake.bulk_intake_with_dispute(
        role="tenant",
        case_text="The landlord is withholding money for cleaning.",
        create_dispute=True,
    )

    assert dispute is not None
    assert dispute.status == DisputeStatus.TENANT_COMPLETE
