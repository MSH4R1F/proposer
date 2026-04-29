import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.disputes_repo import DisputesRepo
from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus
from packages.llm_orchestrator.models.case_file import PartyRole


def _make_dispute(dispute_id: str = "DISP-1", invite: str = "INV-1") -> DisputeCase:
    return DisputeCase(
        dispute_id=dispute_id,
        invite_code=invite,
        status=DisputeStatus.WAITING_FOR_LANDLORD,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        created_by_role=PartyRole.TENANT,
        tenant_session_id=None, landlord_session_id=None,
        property_address=None, property_postcode=None, deposit_amount=None,
        notes=None,
    )


@pytest.mark.asyncio
async def test_dispute_roundtrip(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute()
    await repo.save(d)
    await db_session.commit()
    loaded = await repo.get(d.dispute_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == d.model_dump(mode="json")


@pytest.mark.asyncio
async def test_get_by_invite_code(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute(dispute_id="DISP-A", invite="ABC123")
    await repo.save(d)
    await db_session.commit()
    loaded = await repo.get_by_invite_code("ABC123")
    assert loaded is not None and loaded.dispute_id == "DISP-A"


@pytest.mark.asyncio
async def test_set_cached_prediction_id(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute()
    await repo.save(d)
    await db_session.commit()

    await repo.set_cached_prediction_id(d.dispute_id, None)
    await db_session.commit()


@pytest.mark.asyncio
async def test_lock_for_prediction_cache_exposes_projection(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute()
    await repo.save(d)
    await db_session.commit()

    locked = await repo.lock_for_prediction_cache(d.dispute_id)

    assert locked is not None
    assert locked.dispute.dispute_id == d.dispute_id
    assert locked.cached_prediction_id is None
