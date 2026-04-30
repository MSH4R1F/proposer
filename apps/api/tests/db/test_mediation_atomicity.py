"""
Phase 9.2: prove the four MediationService atomicity hazards roll back fully
when the SECOND write in the transaction raises.

For each hazard we:
  1. Seed prerequisite rows using the same fixture pattern as test_mediation_service.py.
  2. Monkey-patch DisputesRepo.save (always the second write in every hazard) to raise.
  3. Call the service method and assert it propagates the exception.
  4. Open a fresh session and assert neither mutation persisted.

Hazards:
  1. start_mediation  — mediations.save + disputes.save (dispute → IN_MEDIATION)
  2. settle           — mediations.save + disputes.save (dispute → SETTLED)
  3. escalate         — mediations.save + disputes.save (dispute → CLOSED)
  4. respond_to_offer accept → settle — mediations.save + disputes.save (dispute → SETTLED)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from apps.api.src.db.models.disputes import DisputeRow
from apps.api.src.db.models.mediations import MediationSessionRow
from apps.api.src.db.repositories.disputes_repo import DisputesRepo
from apps.api.src.db.uow import UnitOfWork
from apps.api.src.services.dispute_service import DisputeService
from apps.api.src.services.intake_service import IntakeService
from apps.api.src.services.mediation_service import MediationService
from packages.llm_orchestrator.models.case_file import PartyRole
from packages.llm_orchestrator.models.dispute import DisputeStatus
from packages.llm_orchestrator.models.mediation import (
    MediationSession,
    MediationStatus,
    StructuredOffer,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FAKE_PREDICTION: dict = {
    "prediction_id": "pred-atomicity-001",
    "case_id": "case-atomicity-001",
    "overall_outcome": "tenant_wins",
    "overall_confidence": 0.70,
    "predicted_settlement_range": [600, 900],
    "timestamp": "2026-01-01T00:00:00",
    "key_strengths": [],
    "key_weaknesses": [],
    "retrieved_cases": [],
    "outcome_summary": "Tenant likely to recover partial deposit.",
}


def _make_mock_agent() -> MagicMock:
    agent = MagicMock()
    agent.generate_opening_message = AsyncMock(
        return_value="Welcome — neutral overview of this dispute."
    )
    agent.generate_response = AsyncMock(
        return_value="Thank you. Consider the predicted range."
    )
    return agent


def _make_mock_intake_agent() -> MagicMock:
    import uuid as _uuid

    from packages.llm_orchestrator.models.case_file import CaseFile
    from packages.llm_orchestrator.models.case_file import PartyRole as PR
    from packages.llm_orchestrator.models.conversation import ConversationState, IntakeStage

    agent = MagicMock()

    def _make_state(role: PR) -> ConversationState:
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


# ---------------------------------------------------------------------------
# Shared session-seeding fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seeded_dispute(db_sessionmaker):
    """
    Create a dispute with both parties linked and status READY_FOR_MEDIATION.
    Mirrors the seeded_dispute fixture in test_mediation_service.py.
    """
    intake_agent = _make_mock_intake_agent()
    intake_svc = IntakeService(sessionmaker=db_sessionmaker, agent=intake_agent)
    dispute_svc = DisputeService(sessionmaker=db_sessionmaker)

    _, tenant_session_id, _ = await intake_svc.start_session(role="tenant")
    _, landlord_session_id, _ = await intake_svc.start_session(role="landlord")

    dispute = await dispute_svc.create_dispute(
        session_id=tenant_session_id,
        role=PartyRole.TENANT.value,
        deposit_amount=1200.0,
    )

    async with UnitOfWork(db_sessionmaker) as uow:
        d = await uow.disputes.get(dispute.dispute_id)
        d.landlord_session_id = landlord_session_id
        d.deposit_amount = 1200.0
        d.status = DisputeStatus.READY_FOR_MEDIATION
        await uow.disputes.save(d)

    return await dispute_svc.get_dispute(dispute.dispute_id)


@pytest_asyncio.fixture
async def mediation_service(db_sessionmaker, seeded_dispute):
    """MediationService wired to the test DB with a mocked agent and prediction."""
    svc = MediationService(
        sessionmaker=db_sessionmaker,
        mediator_agent=_make_mock_agent(),
    )
    svc._get_prediction_data = AsyncMock(return_value=_FAKE_PREDICTION)
    return svc


# ---------------------------------------------------------------------------
# Hazard 1 — start_mediation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_mediation_rolls_back_when_dispute_save_fails(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
    monkeypatch,
):
    """
    Hazard 1: start_mediation creates the mediation row THEN updates dispute.status.
    If disputes.save raises, the mediation row must not persist.
    """
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    _original_save = DisputesRepo.save

    async def _boom(self, dispute, **kw):
        raise RuntimeError("simulated dispute.save failure — hazard 1")

    monkeypatch.setattr(DisputesRepo, "save", _boom)

    with pytest.raises(RuntimeError, match="simulated dispute.save failure — hazard 1"):
        await mediation_service.start_mediation(dispute_id, tenant_session)

    # Assert: mediation row absent, dispute status unchanged.
    async with db_sessionmaker() as session:
        d_row = await session.get(DisputeRow, dispute_id)
        result = await session.execute(
            select(MediationSessionRow).where(
                MediationSessionRow.dispute_id == dispute_id
            )
        )
        m_rows = list(result.scalars())

    assert d_row is not None, "dispute row vanished unexpectedly"
    assert d_row.status == "ready_for_mediation", (
        f"dispute status leaked to {d_row.status!r}; expected ready_for_mediation"
    )
    assert m_rows == [], (
        f"mediation row persisted despite rollback: {[r.mediation_id for r in m_rows]}"
    )


# ---------------------------------------------------------------------------
# Hazard 2 — settle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settle_rolls_back_when_dispute_save_fails(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
    monkeypatch,
):
    """
    Hazard 2: settle() updates mediation THEN dispute.
    If disputes.save raises, mediation must stay ACTIVE_NEGOTIATION.
    """
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    # Start mediation first (without the patch so this succeeds).
    await mediation_service.start_mediation(dispute_id, tenant_session)

    # Verify mediation exists and is active before the hazard test.
    async with db_sessionmaker() as session:
        result = await session.execute(
            select(MediationSessionRow).where(MediationSessionRow.dispute_id == dispute_id)
        )
        m_before = result.scalars().first()
    assert m_before is not None
    assert m_before.status == "active_negotiation"

    async def _boom(self, dispute, **kw):
        raise RuntimeError("simulated dispute.save failure — hazard 2")

    monkeypatch.setattr(DisputesRepo, "save", _boom)

    with pytest.raises(RuntimeError, match="simulated dispute.save failure — hazard 2"):
        await mediation_service.settle(dispute_id, 750.0)

    # Assert: dispute stays IN_MEDIATION, mediation stays ACTIVE_NEGOTIATION.
    async with db_sessionmaker() as session:
        d_row = await session.get(DisputeRow, dispute_id)
        result = await session.execute(
            select(MediationSessionRow).where(MediationSessionRow.dispute_id == dispute_id)
        )
        m_row = result.scalars().first()

    assert d_row is not None
    assert d_row.status == "in_mediation", (
        f"dispute status leaked to {d_row.status!r}; expected in_mediation"
    )
    assert m_row is not None
    assert m_row.status == "active_negotiation", (
        f"mediation status leaked to {m_row.status!r}; expected active_negotiation"
    )
    assert m_row.settlement_amount is None, (
        f"settlement_amount leaked: {m_row.settlement_amount}"
    )


# ---------------------------------------------------------------------------
# Hazard 3 — escalate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_rolls_back_when_dispute_save_fails(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
    monkeypatch,
):
    """
    Hazard 3: escalate() updates mediation THEN dispute.
    If disputes.save raises, mediation must stay ACTIVE_NEGOTIATION.
    """
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)

    async def _boom(self, dispute, **kw):
        raise RuntimeError("simulated dispute.save failure — hazard 3")

    monkeypatch.setattr(DisputesRepo, "save", _boom)

    with pytest.raises(RuntimeError, match="simulated dispute.save failure — hazard 3"):
        await mediation_service.escalate(dispute_id)

    async with db_sessionmaker() as session:
        d_row = await session.get(DisputeRow, dispute_id)
        result = await session.execute(
            select(MediationSessionRow).where(MediationSessionRow.dispute_id == dispute_id)
        )
        m_row = result.scalars().first()

    assert d_row is not None
    assert d_row.status == "in_mediation", (
        f"dispute status leaked to {d_row.status!r}; expected in_mediation"
    )
    assert m_row is not None
    assert m_row.status == "active_negotiation", (
        f"mediation status leaked to {m_row.status!r}; expected active_negotiation"
    )
    assert m_row.escalated_at is None, (
        f"escalated_at leaked: {m_row.escalated_at}"
    )


# ---------------------------------------------------------------------------
# Hazard 4 — respond_to_offer accept → settle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_offer_rolls_back_when_dispute_save_fails(
    mediation_service: MediationService,
    seeded_dispute,
    db_sessionmaker,
    monkeypatch,
):
    """
    Hazard 4: respond_to_offer(accept) updates mediation (offer accepted + settle)
    THEN dispute.  If disputes.save raises, mediation offer must still be PENDING
    and mediation status must remain ACTIVE_NEGOTIATION.
    """
    dispute_id = seeded_dispute.dispute_id
    tenant_session = seeded_dispute.tenant_session_id
    landlord_session = seeded_dispute.landlord_session_id

    await mediation_service.start_mediation(dispute_id, tenant_session)

    # Tenant submits an offer without the patch.
    offer: StructuredOffer = await mediation_service.submit_offer(
        dispute_id, tenant_session, 600.0
    )
    offer_id = offer.id
    assert offer.status.value == "pending"

    # Verify initial state before hazard.
    async with db_sessionmaker() as session:
        result = await session.execute(
            select(MediationSessionRow).where(MediationSessionRow.dispute_id == dispute_id)
        )
        m_before = result.scalars().first()
    assert m_before.status == "active_negotiation"

    async def _boom(self, dispute, **kw):
        raise RuntimeError("simulated dispute.save failure — hazard 4")

    monkeypatch.setattr(DisputesRepo, "save", _boom)

    with pytest.raises(RuntimeError, match="simulated dispute.save failure — hazard 4"):
        await mediation_service.respond_to_offer(
            dispute_id, landlord_session, offer_id, "accept"
        )

    # Assert: dispute stays IN_MEDIATION, mediation stays ACTIVE_NEGOTIATION,
    # offer stays PENDING.
    async with db_sessionmaker() as session:
        d_row = await session.get(DisputeRow, dispute_id)
        result = await session.execute(
            select(MediationSessionRow).where(MediationSessionRow.dispute_id == dispute_id)
        )
        m_row = result.scalars().first()

    assert d_row is not None
    assert d_row.status == "in_mediation", (
        f"dispute status leaked to {d_row.status!r}; expected in_mediation"
    )
    assert m_row is not None
    assert m_row.status == "active_negotiation", (
        f"mediation status leaked to {m_row.status!r}; expected active_negotiation"
    )
    assert m_row.settlement_amount is None, (
        f"settlement_amount leaked: {m_row.settlement_amount}"
    )

    # Check offer status in the payload — it must still be pending.
    payload_offers = m_row.payload.get("offers", [])
    matched = [o for o in payload_offers if o.get("id") == offer_id]
    assert matched, f"offer {offer_id!r} not found in mediation payload"
    assert matched[0].get("status") == "pending", (
        f"offer status leaked to {matched[0].get('status')!r}; expected pending"
    )
