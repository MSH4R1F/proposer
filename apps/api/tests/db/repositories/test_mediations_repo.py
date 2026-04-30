from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.disputes_repo import DisputesRepo
from apps.api.src.db.repositories.mediations_repo import MediationsRepo
from apps.api.src.db.repositories.sessions_repo import ConcurrentUpdateError
from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus
from packages.llm_orchestrator.models.case_file import PartyRole
from packages.llm_orchestrator.models.mediation import (
    MediationSession,
    MediationStatus,
    MediationMessage,
    MessageType,
    StructuredOffer,
    OfferStatus,
)


def _make_dispute(dispute_id: str = "DISP-1", invite: str = "INV-1") -> DisputeCase:
    return DisputeCase(
        dispute_id=dispute_id,
        invite_code=invite,
        status=DisputeStatus.WAITING_FOR_LANDLORD,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        created_by_role=PartyRole.TENANT,
        tenant_session_id=None,
        landlord_session_id=None,
        property_address=None,
        property_postcode=None,
        deposit_amount=None,
        notes=None,
    )


def _make_mediation(
    mediation_id: str = "MED-1",
    dispute_id: str = "DISP-1",
) -> MediationSession:
    offer = StructuredOffer(
        id="OFF-1",
        amount=500.0,
        proposed_by_role="tenant",
        status=OfferStatus.PENDING,
        proposed_at="2026-01-01T10:00:00",
    )
    offer2 = StructuredOffer(
        id="OFF-2",
        amount=700.0,
        proposed_by_role="landlord",
        status=OfferStatus.COUNTERED,
        proposed_at="2026-01-01T11:00:00",
        responded_at="2026-01-01T12:00:00",
        counter_amount=600.0,
    )
    msg1 = MediationMessage(
        id="MSG-1",
        sender_role="tenant",
        content="I'd like to propose a settlement.",
        message_type=MessageType.TEXT,
        timestamp="2026-01-01T10:00:00",
        metadata={"source": "web"},
        offer_id=None,
    )
    msg2 = MediationMessage(
        id="MSG-2",
        sender_role="tenant",
        content="Offer submitted: £500.00",
        message_type=MessageType.OFFER,
        timestamp="2026-01-01T10:01:00",
        metadata={},
        offer_id="OFF-1",
    )
    return MediationSession(
        mediation_id=mediation_id,
        dispute_id=dispute_id,
        status=MediationStatus.ACTIVE_NEGOTIATION,
        started_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T10:00:00",
        settled_at=None,
        settlement_amount=None,
        escalated_at=None,
        messages=[msg1, msg2],
        offers=[offer, offer2],
    )


async def _seed_dispute(
    db_session: AsyncSession,
    dispute_id: str,
    invite: str,
) -> None:
    disputes_repo = DisputesRepo(db_session)
    d = _make_dispute(dispute_id=dispute_id, invite=invite)
    await disputes_repo.save(d)
    await db_session.commit()


@pytest.mark.asyncio
async def test_mediation_roundtrip_with_messages_and_offers(
    db_session: AsyncSession,
) -> None:
    await _seed_dispute(db_session, "DISP-1", "INV-1")

    repo = MediationsRepo(db_session)
    med = _make_mediation(mediation_id="MED-1", dispute_id="DISP-1")
    await repo.save(med)
    await db_session.commit()

    loaded = await repo.get("MED-1")
    assert loaded is not None
    assert loaded.model_dump(mode="json") == med.model_dump(mode="json")


@pytest.mark.asyncio
async def test_save_replaces_children_on_upsert(db_session: AsyncSession) -> None:
    await _seed_dispute(db_session, "DISP-2", "INV-2")

    repo = MediationsRepo(db_session)
    med = _make_mediation(mediation_id="MED-2", dispute_id="DISP-2")
    await repo.save(med)
    await db_session.commit()

    # Save again with empty messages and offers
    med.messages = []
    med.offers = []
    await repo.save(med)
    await db_session.commit()

    loaded = await repo.get("MED-2")
    assert loaded is not None
    assert loaded.messages == []
    assert loaded.offers == []


@pytest.mark.asyncio
async def test_get_by_dispute_id(db_session: AsyncSession) -> None:
    await _seed_dispute(db_session, "DISP-3", "INV-3")
    await _seed_dispute(db_session, "DISP-4", "INV-4")

    repo = MediationsRepo(db_session)
    med3 = _make_mediation(mediation_id="MED-3", dispute_id="DISP-3")
    med4 = _make_mediation(mediation_id="MED-4", dispute_id="DISP-4")
    await repo.save(med3)
    await repo.save(med4)
    await db_session.commit()

    result = await repo.get_by_dispute_id("DISP-3")
    assert result is not None
    assert result.mediation_id == "MED-3"
    assert result.dispute_id == "DISP-3"

    result2 = await repo.get_by_dispute_id("DISP-4")
    assert result2 is not None
    assert result2.mediation_id == "MED-4"


@pytest.mark.asyncio
async def test_lock_by_dispute_id_returns_versioned_session(
    db_session: AsyncSession,
) -> None:
    await _seed_dispute(db_session, "DISP-6", "INV-6")

    repo = MediationsRepo(db_session)
    med = _make_mediation(mediation_id="MED-6", dispute_id="DISP-6")
    await repo.save(med)
    await db_session.commit()

    locked = await repo.lock_by_dispute_id("DISP-6")

    assert locked is not None
    assert locked.session.mediation_id == "MED-6"
    assert locked.version == 1


@pytest.mark.asyncio
async def test_save_with_expected_version_raises_on_mismatch(
    db_session: AsyncSession,
) -> None:
    await _seed_dispute(db_session, "DISP-5", "INV-5")

    repo = MediationsRepo(db_session)
    med = _make_mediation(mediation_id="MED-5", dispute_id="DISP-5")
    await repo.save(med)
    await db_session.commit()

    with pytest.raises(ConcurrentUpdateError):
        await repo.save(med, expected_version=999)
