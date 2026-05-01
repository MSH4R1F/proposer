"""
Integration tests for the UoW-backed MediationService (Phase 9.1).

Tests exercise the full persistence path against a real (migrated) Postgres
database.  The mediator LLM agent is mocked to avoid network calls.

Coverage:
  1. start_mediation creates a mediation row and updates dispute status.
  2. add_message appends user + AI messages.
  3. settle updates both mediation and dispute status atomically.
  4. escalate updates both mediation and dispute status atomically.
  5. submit_offer + respond_to_offer accept (→ settle) flow.
  6. get_messages returns messages and respects since_timestamp filter.

Atomicity-rollback tests are covered separately in Task 9.2.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from apps.api.src.db.uow import UnitOfWork
from apps.api.src.services.dispute_service import DisputeService
from apps.api.src.services.intake_service import IntakeService
from apps.api.src.services.mediation_service import MediationService
from packages.llm_orchestrator.models.case_file import PartyRole
from packages.llm_orchestrator.models.dispute import DisputeStatus
from packages.llm_orchestrator.models.mediation import MediationStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_agent() -> MagicMock:
    """Build a mock MediatorAgent that returns deterministic strings."""
    agent = MagicMock()
    agent.generate_opening_message = AsyncMock(
        return_value="Welcome — here is a neutral overview of this dispute."
    )
    agent.generate_response = AsyncMock(
        return_value="Thank you. Based on similar cases, consider the predicted range."
    )
    return agent


def _make_mock_intake_agent() -> MagicMock:
    """Minimal intake agent mock sufficient for session seeding."""
    import uuid as _uuid
    from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole as PR
    from packages.llm_orchestrator.models.conversation import ConversationState, IntakeStage

    agent = MagicMock()

    def _make_state(role: PR) -> ConversationState:
        # Each call gets a fresh UUID so tenant and landlord get distinct session IDs.
        sid = str(_uuid.uuid4())[:12]
        return ConversationState(
            session_id=sid,
            case_file=CaseFile(case_id=f"case-{sid}", user_role=role),
            messages=[],
            current_stage=IntakeStage.GREETING,
            started_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            stages_completed=[],
            current_stage_attempts=0,
            last_extraction_successful=True,
            extraction_errors=[],
            role_explicitly_set=True,
        )

    async def _start_conversation(**kwargs):
        user_role = kwargs.get("user_role") or PR.TENANT
        return ("hello", _make_state(user_role))

    agent.start_conversation = AsyncMock(side_effect=_start_conversation)
    return agent


@pytest_asyncio.fixture
async def dispute_service(db_sessionmaker):
    return DisputeService(sessionmaker=db_sessionmaker)


@pytest_asyncio.fixture
async def seeded_dispute(db_sessionmaker, dispute_service: DisputeService):
    """
    Create a dispute that has both parties linked and is READY_FOR_MEDIATION.

    Both intake sessions are seeded via IntakeService.start_session() so that
    the FK constraints on disputes.tenant_session_id / landlord_session_id are
    satisfied.  The dispute is then force-updated to READY_FOR_MEDIATION.
    """
    intake_agent = _make_mock_intake_agent()
    intake_svc = IntakeService(sessionmaker=db_sessionmaker, agent=intake_agent)

    # Create tenant session.
    _, tenant_session_id, _ = await intake_svc.start_session(role="tenant")
    # Create landlord session.
    _, landlord_session_id, _ = await intake_svc.start_session(role="landlord")

    # Create the dispute (linked to tenant session).
    dispute = await dispute_service.create_dispute(
        session_id=tenant_session_id,
        role=PartyRole.TENANT.value,
        deposit_amount=1200.0,
    )

    # Link landlord + set READY_FOR_MEDIATION directly in the DB.
    async with UnitOfWork(db_sessionmaker) as uow:
        d = await uow.disputes.get(dispute.dispute_id)
        d.landlord_session_id = landlord_session_id
        d.deposit_amount = 1200.0
        d.status = DisputeStatus.READY_FOR_MEDIATION
        await uow.disputes.save(d)

    # Reload and return final state.
    return await dispute_service.get_dispute(dispute.dispute_id)


_FAKE_PREDICTION: dict = {
    "prediction_id": "pred-test-001",
    "case_id": "case-test-001",
    "overall_outcome": "tenant_wins",
    "overall_confidence": 0.70,
    "predicted_settlement_range": [600, 900],
    "timestamp": "2026-01-01T00:00:00",
    "key_strengths": [],
    "key_weaknesses": [],
    "retrieved_cases": [],
    "outcome_summary": "Tenant likely to recover partial deposit.",
}


@pytest_asyncio.fixture
async def mediation_service(db_sessionmaker, seeded_dispute):
    """MediationService wired to a real DB with mocked agent and prediction data."""
    agent = _make_mock_agent()
    svc = MediationService(sessionmaker=db_sessionmaker, mediator_agent=agent)
    # Stub out prediction lookup (no prediction rows seeded in DB).
    # _fetch_prediction_data_uow is the actual code path used by the
    # postgres-mode service; the legacy _get_prediction_data hook is kept
    # for in-memory rollback paths only.
    svc._fetch_prediction_data_uow = AsyncMock(return_value=_FAKE_PREDICTION)
    svc._get_prediction_data = AsyncMock(return_value=_FAKE_PREDICTION)
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_mediation_creates_row_and_updates_dispute(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """start_mediation must create a mediation row and set dispute → IN_MEDIATION."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    result = await mediation_service.start_mediation(dispute_id, tenant_session)

    assert result["dispute_id"] == dispute_id
    assert result["status"] == "active_negotiation"
    assert result["initial_message"]["message_type"] == "ai_mediator"

    # Verify DB state.
    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        dispute = await uow.disputes.get(dispute_id)

    assert mediation is not None
    assert mediation.status == MediationStatus.ACTIVE_NEGOTIATION
    assert len(mediation.messages) >= 1
    assert dispute is not None
    assert dispute.status == DisputeStatus.IN_MEDIATION


@pytest.mark.asyncio
async def test_start_mediation_is_idempotent(
    mediation_service: MediationService,
    seeded_dispute,
) -> None:
    """Calling start_mediation twice must return the existing session, not raise."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    first = await mediation_service.start_mediation(dispute_id, tenant_session)
    second = await mediation_service.start_mediation(dispute_id, tenant_session)

    assert first["mediation_id"] == second["mediation_id"]


@pytest.mark.asyncio
async def test_concurrent_start_mediation_is_idempotent(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """Concurrent starters must converge on one mediation row for the dispute."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    first, second = await asyncio.gather(
        mediation_service.start_mediation(dispute_id, tenant_session),
        mediation_service.start_mediation(dispute_id, tenant_session),
    )

    assert first["mediation_id"] == second["mediation_id"]

    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        dispute = await uow.disputes.get(dispute_id)

    assert mediation is not None
    assert dispute is not None
    assert mediation.status == MediationStatus.ACTIVE_NEGOTIATION
    assert dispute.status == DisputeStatus.IN_MEDIATION


@pytest.mark.asyncio
async def test_add_message_appends_user_and_ai_messages(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """add_message must persist a user message and an AI mediator response."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)
    result = await mediation_service.add_message(
        dispute_id, tenant_session, "I think my landlord is wrong."
    )

    assert "user_message" in result
    assert result["user_message"]["sender_role"] == "tenant"
    assert "ai_response" in result
    assert result["ai_response"]["sender_role"] == "ai_mediator"

    # Verify DB persistence.
    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)

    # Opening message + user message + AI response = at least 3.
    assert len(mediation.messages) >= 3


@pytest.mark.asyncio
async def test_concurrent_add_message_preserves_both_updates(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """Two simultaneous messages must both survive the read-modify-write cycle."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id
    landlord_session = seeded_dispute.landlord_session_id

    async def _delayed_response(**kwargs):
        await asyncio.sleep(0.05)
        return "Neutral follow-up with legal-information framing."

    mediation_service._mediator.generate_response = AsyncMock(
        side_effect=_delayed_response
    )

    await mediation_service.start_mediation(dispute_id, tenant_session)
    await asyncio.gather(
        mediation_service.add_message(dispute_id, tenant_session, "Tenant update"),
        mediation_service.add_message(dispute_id, landlord_session, "Landlord update"),
    )

    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)

    assert mediation is not None
    contents = [message.content for message in mediation.messages]
    assert "Tenant update" in contents
    assert "Landlord update" in contents
    assert len(mediation.messages) >= 5


@pytest.mark.asyncio
async def test_get_expectation_data_matches_web_contract(
    mediation_service: MediationService,
    seeded_dispute,
) -> None:
    """Expectation payload should expose the frontend ExpectationData shape."""
    result = await mediation_service.get_expectation_data(
        seeded_dispute.dispute_id,
        seeded_dispute.tenant_session_id,
    )

    assert result["party_role"] == "tenant"
    assert result["prediction_summary"]["suggested_amount"] == 750.0
    assert result["prediction_summary"]["settlement_range"] == [600.0, 900.0]
    assert "party_framing" in result
    assert result["cost_benefit"]["settlement_option"]["amount"] == 750.0
    assert result["cost_benefit"]["tribunal_option"]["cost_to_party"] == 0
    assert result["tribunal_costs"]["timeline_months_min"] == 6


@pytest.mark.asyncio
async def test_settle_updates_mediation_and_dispute_atomically(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """settle() must update both the mediation row and the dispute row in one transaction."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)
    result = await mediation_service.settle(dispute_id, 750.0)

    assert result["status"] == "settled"
    assert result["settlement_amount"] == 750.0

    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        dispute = await uow.disputes.get(dispute_id)

    assert mediation.status == MediationStatus.SETTLED
    assert mediation.settlement_amount == 750.0
    assert dispute.status == DisputeStatus.SETTLED


@pytest.mark.asyncio
async def test_escalate_updates_mediation_and_dispute_atomically(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """escalate() must update both the mediation row and the dispute row in one transaction."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)
    result = await mediation_service.escalate(dispute_id)

    assert result["mediation_status"] == "escalated"

    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        dispute = await uow.disputes.get(dispute_id)

    assert mediation.status == MediationStatus.ESCALATED
    assert dispute.status == DisputeStatus.CLOSED  # escalate() sets CLOSED on DisputeCase


@pytest.mark.asyncio
async def test_submit_offer_and_accept_settles(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
) -> None:
    """submit_offer + respond_to_offer(accept) must settle the mediation atomically."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id
    landlord_session = seeded_dispute.landlord_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)

    offer = await mediation_service.submit_offer(dispute_id, tenant_session, 600.0)
    assert offer.amount == 600.0
    assert offer.status.value == "pending"

    result = await mediation_service.respond_to_offer(
        dispute_id, landlord_session, offer.id, "accept"
    )

    assert result["action"] == "accept"
    assert result["settlement_amount"] == 600.0
    assert result["mediation_status"] == "settled"
    assert len(result["messages"]) == 1

    async with UnitOfWork(db_sessionmaker) as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        dispute = await uow.disputes.get(dispute_id)

    assert mediation.status == MediationStatus.SETTLED
    assert mediation.settlement_amount == 600.0
    assert dispute.status == DisputeStatus.SETTLED


@pytest.mark.asyncio
async def test_submit_offer_allows_prediction_range_above_deposit(
    mediation_service: MediationService,
    seeded_dispute,
) -> None:
    """Deposit-penalty settlements may exceed the original deposit."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id
    prediction_with_penalty_range = {
        **_FAKE_PREDICTION,
        "predicted_settlement_range": [1500, 3000],
    }
    mediation_service._fetch_prediction_data_uow.return_value = (
        prediction_with_penalty_range
    )
    mediation_service._get_prediction_data.return_value = prediction_with_penalty_range

    await mediation_service.start_mediation(dispute_id, tenant_session)
    offer = await mediation_service.submit_offer(dispute_id, tenant_session, 2500.0)

    assert offer.amount == 2500.0
    assert offer.status.value == "pending"


@pytest.mark.asyncio
async def test_get_session_returns_messages_and_offers(
    mediation_service: MediationService,
    seeded_dispute,
) -> None:
    """The web client's /session call needs the full mediation state."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)
    offer = await mediation_service.submit_offer(dispute_id, tenant_session, 600.0)

    result = await mediation_service.get_session(dispute_id)

    assert result["dispute_id"] == dispute_id
    assert result["offers"][0]["id"] == offer.id
    assert any(message["offer_id"] == offer.id for message in result["messages"])


@pytest.mark.asyncio
async def test_counter_offer_returns_updated_and_new_offer_with_messages(
    mediation_service: MediationService,
    seeded_dispute,
) -> None:
    """Counter responses should let the web update the old card and add the new one."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id
    landlord_session = seeded_dispute.landlord_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)
    offer = await mediation_service.submit_offer(dispute_id, tenant_session, 600.0)

    result = await mediation_service.respond_to_offer(
        dispute_id,
        landlord_session,
        offer.id,
        "counter",
        counter_amount=700.0,
    )

    assert result["action"] == "counter"
    assert result["offer"]["id"] == offer.id
    assert result["offer"]["status"] == "countered"
    assert result["new_offer"]["amount"] == 700.0
    assert result["messages"][0]["offer_id"] == result["new_offer"]["id"]


@pytest.mark.asyncio
async def test_get_messages_respects_since_timestamp(
    mediation_service: MediationService,
    seeded_dispute,
) -> None:
    """get_messages must filter messages after since_timestamp."""
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)

    all_messages = await mediation_service.get_messages(dispute_id)
    assert len(all_messages) >= 1

    # Use the first message's timestamp as the filter boundary.
    first_ts = all_messages[0]["timestamp"]
    await mediation_service.add_message(dispute_id, tenant_session, "Follow-up message.")

    filtered = await mediation_service.get_messages(dispute_id, first_ts)
    assert all(m["timestamp"] > first_ts for m in filtered)
    assert len(filtered) >= 1  # at least the new user message + AI response
