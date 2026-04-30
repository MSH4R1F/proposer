import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.disputes_repo import DisputesRepo
from apps.api.src.db.repositories.sessions_repo import SessionsRepo
from packages.llm_orchestrator.models.conversation import ConversationState, IntakeStage
from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus
from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole


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
    from apps.api.src.db.repositories.predictions_repo import PredictionsRepo
    from packages.llm_orchestrator.models.prediction_v2 import OutcomeType, PredictionResult

    repo = DisputesRepo(db_session)
    pred_repo = PredictionsRepo(db_session)
    d = _make_dispute()
    p = PredictionResult(
        case_id="case-1",
        prediction_id="p-1",
        timestamp="2026-01-01T00:00:00",
        overall_outcome=OutcomeType.SPLIT,
        overall_confidence=0.5,
    )
    await pred_repo.save(p)
    await repo.save(d)
    await db_session.commit()

    await repo.set_cached_prediction_id(d.dispute_id, "p-1", cache_key="abc")
    await db_session.commit()
    locked = await repo.lock_for_prediction_cache(d.dispute_id)
    assert locked is not None
    assert locked.cached_prediction_id == "p-1"
    assert locked.prediction_cache_key == "abc"


@pytest.mark.asyncio
async def test_versioned_save_preserves_prediction_cache_key(db_session: AsyncSession) -> None:
    from apps.api.src.db.repositories.predictions_repo import PredictionsRepo
    from packages.llm_orchestrator.models.prediction_v2 import OutcomeType, PredictionResult

    repo = DisputesRepo(db_session)
    pred_repo = PredictionsRepo(db_session)
    d = _make_dispute()
    p = PredictionResult(
        case_id="case-1",
        prediction_id="p-1",
        timestamp="2026-01-01T00:00:00",
        overall_outcome=OutcomeType.SPLIT,
        overall_confidence=0.5,
    )
    await pred_repo.save(p)
    await repo.save(d)
    await db_session.commit()

    versioned = await repo.get_with_version(d.dispute_id)
    assert versioned is not None
    await repo.set_cached_prediction_id(d.dispute_id, "p-1", cache_key="abc")
    await repo.save(versioned.dispute, expected_version=versioned.version)
    await db_session.commit()

    locked = await repo.lock_for_prediction_cache(d.dispute_id)
    assert locked is not None
    assert locked.cached_prediction_id == "p-1"
    assert locked.prediction_cache_key == "abc"


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


@pytest.mark.asyncio
async def test_get_overlays_fk_set_null_columns(db_session: AsyncSession) -> None:
    sessions = SessionsRepo(db_session)
    disputes = DisputesRepo(db_session)
    state = ConversationState(
        session_id="sess-delete-me",
        case_file=CaseFile(case_id="case-delete-me", user_role=PartyRole.TENANT),
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
    dispute = _make_dispute(dispute_id="DISP-SETNULL")
    dispute.tenant_session_id = state.session_id

    await sessions.save(state)
    await disputes.save(dispute)
    await db_session.commit()

    await sessions.delete(state.session_id)
    await db_session.commit()

    loaded = await disputes.get(dispute.dispute_id)

    assert loaded is not None
    assert loaded.tenant_session_id is None
