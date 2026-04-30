"""
Integration tests for the UoW-backed PredictionService (Phase 7.1).

These tests exercise the full persistence path against a real (migrated)
Postgres database spun up by pytest-postgresql.  The LLM prediction engine
and graph builder are mocked so we never hit external APIs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import select

from apps.api.src.db.models.disputes import DisputeRow
from apps.api.src.db.uow import UnitOfWork
from apps.api.src.services.prediction_service import (
    PredictionCacheConflictError,
    PredictionService,
)
from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
from packages.llm_orchestrator.models.conversation import ConversationState, IntakeStage
from packages.llm_orchestrator.models.dispute import DisputeCase, generate_invite_code
from packages.llm_orchestrator.models.prediction_v2 import (
    Citation,
    EvidenceStrength,
    IssuePrediction,
    IssueOutcome,
    IssueType,
    OutcomeType,
    PredictionResult,
    ReasoningStep,
)
from packages.kg_builder.models.graph import KnowledgeGraph


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _make_case_file(
    case_id: str = "case-1",
    role: PartyRole = PartyRole.TENANT,
) -> CaseFile:
    return CaseFile(case_id=case_id, user_role=role)


def _make_session(
    session_id: str = "sess-1",
    case_id: str = "case-1",
    role: PartyRole = PartyRole.TENANT,
    stage: IntakeStage = IntakeStage.GREETING,
) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        case_file=_make_case_file(case_id=case_id, role=role),
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


def _make_prediction(
    prediction_id: str = "pred-1",
    case_id: str = "case-1",
) -> PredictionResult:
    citation = Citation(
        case_reference="LON/00AY/2023/0042", year=2023, region="London",
        paragraph="12", quote="Q" * 80, relevance="R" * 80,
        similarity_score=0.91, verified=True,
    )
    issue = IssuePrediction(
        issue_type=IssueType.CLEANING, issue_description="Dirty kitchen",
        outcome=IssueOutcome.LANDLORD_WINS, raw_confidence=0.7,
        predicted_amount=120.0, amount_range=(80.0, 160.0),
        reasoning="Inventory checkin clean, checkout dirty.",
        key_factors=["clear inventory"], supporting_cases=[citation],
        counterfactuals=[], evidence_strength=EvidenceStrength.MODERATE,
    )
    step = ReasoningStep(
        step_number=1, category="legal_framework",
        title="Deposit framework", content="Long content...",
        citations=[citation], confidence=0.8,
    )
    return PredictionResult(
        case_id=case_id, prediction_id=prediction_id,
        timestamp="2026-01-01T00:00:00",
        overall_outcome=OutcomeType.SPLIT, overall_confidence=0.65,
        outcome_summary="Mixed outcome",
        tenant_recovery_amount=400.0, landlord_recovery_amount=120.0,
        predicted_settlement_range=(380.0, 500.0),
        issue_predictions=[issue], reasoning_trace=[step],
        retrieved_cases=[], total_cases_analyzed=42,
        pipeline_metadata=None,
        temporal_distribution={2023: 12, 2022: 10},
        key_strengths=["clear evidence"], key_weaknesses=[],
        uncertainties=[], missing_information=[],
        model_version="2.0.0", pipeline_version="v2",
    )


def _make_kg(case_id: str = "case-1") -> KnowledgeGraph:
    """Return a minimal KnowledgeGraph for the given case_id."""
    return KnowledgeGraph(case_id=case_id, nodes=[], edges=[])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_engine():
    """AsyncMock for the LLM prediction engine."""
    engine = AsyncMock()
    return engine


@pytest_asyncio.fixture
async def mock_graph_builder():
    """MagicMock for the pure-Python graph builder."""
    gb = MagicMock()
    return gb


@pytest_asyncio.fixture
async def prediction_service(db_sessionmaker, mock_engine, mock_graph_builder):
    """PredictionService with injected mocks; never hits LLMs."""
    return PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )


# ---------------------------------------------------------------------------
# Test 1: one-party case (no dispute) — no caching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_prediction_for_one_party_case_does_not_cache(
    db_sessionmaker,
    prediction_service: PredictionService,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
) -> None:
    """A case with no linked dispute: prediction saved but no dispute cache set."""
    case_id = "solo-case"
    pred_id = "solo-pred"
    kg = _make_kg(case_id=case_id)
    pred = _make_prediction(prediction_id=pred_id, case_id=case_id)

    mock_graph_builder.build.return_value = kg
    mock_engine.predict.return_value = pred

    # Seed the session in the DB (no dispute linkage).
    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(_make_session(session_id="sess-solo", case_id=case_id))

    result = await prediction_service.generate_prediction(case_id)
    assert result.prediction_id == pred_id

    # Prediction and KG must be persisted.
    async with UnitOfWork(db_sessionmaker) as uow:
        saved = await uow.predictions.get(pred_id)
        assert saved is not None
        assert saved.prediction_id == pred_id

        kg_saved = await uow.knowledge_graphs.get(case_id)
        assert kg_saved is not None

    # mock_engine.predict must have been called exactly once.
    mock_engine.predict.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: two-party dispute — caching and deduplication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_prediction_for_two_party_dispute_caches(
    db_sessionmaker,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
) -> None:
    """
    Both tenant + landlord linked to the same dispute.

    First call (tenant's case_id) must:
    - run mock_engine.predict once
    - write disputes.cached_prediction_id

    Second call (landlord's case_id) must:
    - return the SAME cached prediction
    - NOT call mock_engine.predict again
    """
    tenant_sid = "sess-tenant"
    landlord_sid = "sess-landlord"
    tenant_case = "case-tenant"
    landlord_case = "case-landlord"
    dispute_id = "dispute-two"
    pred_id = "shared-pred"
    invite = generate_invite_code()

    # Merged case_id is the tenant's case_id (merge_case_files returns a new
    # CaseFile; mock engine gets it as the "merged" case).  The prediction's
    # case_id must be set to the tenant's case_id so the repo links it.
    merged_case_id = tenant_case

    # Configure mocks.
    kg = _make_kg(case_id=merged_case_id)
    pred = _make_prediction(prediction_id=pred_id, case_id=merged_case_id)
    mock_graph_builder.build.return_value = kg
    mock_engine.predict.return_value = pred

    # Seed sessions + dispute.
    async with UnitOfWork(db_sessionmaker) as uow:
        tenant_state = _make_session(
            session_id=tenant_sid, case_id=tenant_case, role=PartyRole.TENANT
        )
        landlord_state = _make_session(
            session_id=landlord_sid, case_id=landlord_case, role=PartyRole.LANDLORD
        )
        await uow.sessions.save(tenant_state)
        await uow.sessions.save(landlord_state)

        dispute = DisputeCase(
            dispute_id=dispute_id,
            invite_code=invite,
            created_by_role="tenant",
        )
        dispute.link_tenant_session(tenant_sid)
        dispute.link_landlord_session(landlord_sid)
        await uow.disputes.save(dispute)

    svc1 = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )
    svc2 = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )

    # First call: tenant's case_id.
    result1 = await svc1.generate_prediction(tenant_case)
    assert result1.prediction_id == pred_id

    # disputes.cached_prediction_id must be populated now.
    async with UnitOfWork(db_sessionmaker) as uow:
        row_result = await uow.session.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id)
        )
        row = row_result.scalar_one_or_none()
        assert row is not None
        assert row.cached_prediction_id == pred_id

    # Second call: landlord's case_id.  Engine must NOT be called again.
    engine_call_count_before = mock_engine.predict.call_count
    result2 = await svc2.generate_prediction(landlord_case)
    assert result2.prediction_id == pred_id
    assert mock_engine.predict.call_count == engine_call_count_before, (
        "predict() must not be called for the second party when cache is warm"
    )


# ---------------------------------------------------------------------------
# Test 3: atomic rollback on write failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_prediction_atomic_rollback_on_failure(
    db_sessionmaker,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
    monkeypatch,
) -> None:
    """
    If set_cached_prediction_id raises, the whole stage-3 transaction rolls back:
    no rows in predictions or knowledge_graphs for that case_id.

    We use a two-party dispute so that the set_cached_prediction_id path is reached
    (it runs last in stage 3, after KG + prediction saves).
    """
    tenant_sid = "sess-t-atomic"
    landlord_sid = "sess-l-atomic"
    tenant_case = "case-atomic-tenant"
    landlord_case = "case-atomic-landlord"
    dispute_id = "dispute-atomic"
    pred_id = "atomic-pred"
    invite = generate_invite_code()

    merged_case_id = tenant_case
    kg = _make_kg(case_id=merged_case_id)
    pred = _make_prediction(prediction_id=pred_id, case_id=merged_case_id)
    mock_graph_builder.build.return_value = kg
    mock_engine.predict.return_value = pred

    # Seed sessions + dispute.
    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(
            _make_session(session_id=tenant_sid, case_id=tenant_case, role=PartyRole.TENANT)
        )
        await uow.sessions.save(
            _make_session(session_id=landlord_sid, case_id=landlord_case, role=PartyRole.LANDLORD)
        )
        dispute = DisputeCase(
            dispute_id=dispute_id,
            invite_code=invite,
            created_by_role="tenant",
        )
        dispute.link_tenant_session(tenant_sid)
        dispute.link_landlord_session(landlord_sid)
        await uow.disputes.save(dispute)

    # Patch set_cached_prediction_id on the repo class to raise.
    from apps.api.src.db.repositories.disputes_repo import DisputesRepo

    original_set = DisputesRepo.set_cached_prediction_id

    async def _failing_set(self, dispute_id, prediction_id, *, cache_key=None):
        raise RuntimeError("injected failure in set_cached_prediction_id")

    monkeypatch.setattr(DisputesRepo, "set_cached_prediction_id", _failing_set)

    svc = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        await svc.generate_prediction(tenant_case)

    # Rollback means no prediction or KG rows exist for this case_id.
    async with UnitOfWork(db_sessionmaker) as uow:
        saved_pred = await uow.predictions.get(pred_id)
        assert saved_pred is None, "prediction must be rolled back"

        saved_kg = await uow.knowledge_graphs.get(merged_case_id)
        assert saved_kg is None, "knowledge graph must be rolled back"


# ---------------------------------------------------------------------------
# Test 4: get_prediction round-trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_prediction_returns_saved(
    db_sessionmaker,
    prediction_service: PredictionService,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
) -> None:
    """Round-trip: generate_prediction → get_prediction returns the same data."""
    case_id = "roundtrip-case"
    pred_id = "roundtrip-pred"
    kg = _make_kg(case_id=case_id)
    pred = _make_prediction(prediction_id=pred_id, case_id=case_id)
    mock_graph_builder.build.return_value = kg
    mock_engine.predict.return_value = pred

    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(
            _make_session(session_id="sess-roundtrip", case_id=case_id)
        )

    await prediction_service.generate_prediction(case_id)

    result = await prediction_service.get_prediction(pred_id)
    assert result is not None
    assert result["prediction_id"] == pred_id
    assert result["case_id"] == case_id
    assert result["overall_outcome"] == OutcomeType.SPLIT.value


# ---------------------------------------------------------------------------
# Test 5: list_predictions_for_case includes shared cached dispute prediction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_predictions_for_case_includes_shared_cached(
    db_sessionmaker,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
) -> None:
    """
    Tenant has a direct (solo) prediction AND a shared cached dispute prediction.
    list_predictions_for_case must return both, de-duplicated.

    Setup:
    1. Seed tenant session alone → generate solo prediction (pred-solo).
    2. Seed landlord session + link both to a dispute.
    3. Generate again as two-party → shared prediction (pred-shared) written and
       cached on the dispute row.
    4. list_predictions_for_case(tenant_case_id) must include both pred-solo and
       pred-shared.
    """
    tenant_sid = "sess-list-t"
    landlord_sid = "sess-list-l"
    tenant_case = "case-list-tenant"
    landlord_case = "case-list-landlord"
    dispute_id = "dispute-list"
    pred_solo_id = "pred-solo-list"
    pred_shared_id = "pred-shared-list"
    invite = generate_invite_code()
    merged_case_id = tenant_case

    # -- Phase A: solo prediction (tenant only, no dispute yet) --
    kg_solo = _make_kg(case_id=tenant_case)
    pred_solo = _make_prediction(prediction_id=pred_solo_id, case_id=tenant_case)

    mock_graph_builder.build.return_value = kg_solo
    mock_engine.predict.return_value = pred_solo

    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(
            _make_session(session_id=tenant_sid, case_id=tenant_case, role=PartyRole.TENANT)
        )

    svc_a = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )
    await svc_a.generate_prediction(tenant_case)

    # -- Phase B: link landlord + create dispute --
    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(
            _make_session(
                session_id=landlord_sid, case_id=landlord_case, role=PartyRole.LANDLORD
            )
        )
        dispute = DisputeCase(
            dispute_id=dispute_id,
            invite_code=invite,
            created_by_role="tenant",
        )
        dispute.link_tenant_session(tenant_sid)
        dispute.link_landlord_session(landlord_sid)
        await uow.disputes.save(dispute)

    # -- Phase C: generate shared (merged) prediction --
    kg_shared = _make_kg(case_id=merged_case_id)
    pred_shared = _make_prediction(prediction_id=pred_shared_id, case_id=merged_case_id)
    mock_graph_builder.build.return_value = kg_shared
    mock_engine.predict.return_value = pred_shared

    svc_b = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )
    await svc_b.generate_prediction(tenant_case)

    # -- Phase D: list and assert both predictions appear --
    svc_c = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )
    predictions = await svc_c.list_predictions_for_case(tenant_case)

    pred_ids = {p["prediction_id"] for p in predictions}
    assert pred_solo_id in pred_ids, (
        f"Solo prediction {pred_solo_id!r} must appear; got {pred_ids}"
    )
    assert pred_shared_id in pred_ids, (
        f"Shared prediction {pred_shared_id!r} must appear; got {pred_ids}"
    )
    assert len(pred_ids) == 2, f"Expected exactly 2 distinct predictions; got {pred_ids}"


@pytest.mark.asyncio
async def test_generate_prediction_conflicts_if_sessions_change_before_stage3(
    db_sessionmaker,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
) -> None:
    """A merged prediction generated against old session versions must not be persisted."""
    tenant_sid = "sess-conflict-t"
    landlord_sid = "sess-conflict-l"
    tenant_case = "case-conflict-tenant"
    landlord_case = "case-conflict-landlord"
    dispute_id = "dispute-conflict"
    pred_id = "pred-conflict-stale"
    invite = generate_invite_code()

    kg = _make_kg(case_id=tenant_case)
    pred = _make_prediction(prediction_id=pred_id, case_id=tenant_case)
    mock_graph_builder.build.return_value = kg

    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(
            _make_session(session_id=tenant_sid, case_id=tenant_case, role=PartyRole.TENANT)
        )
        await uow.sessions.save(
            _make_session(
                session_id=landlord_sid,
                case_id=landlord_case,
                role=PartyRole.LANDLORD,
            )
        )
        dispute = DisputeCase(
            dispute_id=dispute_id,
            invite_code=invite,
            created_by_role="tenant",
        )
        dispute.link_tenant_session(tenant_sid)
        dispute.link_landlord_session(landlord_sid)
        await uow.disputes.save(dispute)

    async def _predict_and_change_session(*, case_file, knowledge_graph, mode=None):
        async with UnitOfWork(db_sessionmaker) as uow:
            state = await uow.sessions.get(landlord_sid)
            assert state is not None
            state.updated_at = "2026-01-01T00:01:00"
            await uow.sessions.save(state)
        return pred

    mock_engine.predict.side_effect = _predict_and_change_session

    svc = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )

    with pytest.raises(PredictionCacheConflictError):
        await svc.generate_prediction(tenant_case)

    async with UnitOfWork(db_sessionmaker) as uow:
        assert await uow.predictions.get(pred_id) is None
        assert await uow.knowledge_graphs.get(tenant_case) is None
        row_result = await uow.session.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id)
        )
        row = row_result.scalar_one()
        assert row.cached_prediction_id is None
        assert row.prediction_cache_key is None


@pytest.mark.asyncio
async def test_list_predictions_for_case_hides_stale_shared_cached_prediction(
    db_sessionmaker,
    mock_engine: AsyncMock,
    mock_graph_builder: MagicMock,
) -> None:
    """A merged prediction is hidden once either party's intake session version changes."""
    tenant_sid = "sess-stale-list-t"
    landlord_sid = "sess-stale-list-l"
    tenant_case = "case-stale-list-tenant"
    landlord_case = "case-stale-list-landlord"
    dispute_id = "dispute-stale-list"
    pred_id = "pred-stale-list"
    invite = generate_invite_code()

    kg = _make_kg(case_id=tenant_case)
    pred = _make_prediction(prediction_id=pred_id, case_id=tenant_case)
    mock_graph_builder.build.return_value = kg
    mock_engine.predict.return_value = pred

    async with UnitOfWork(db_sessionmaker) as uow:
        await uow.sessions.save(
            _make_session(session_id=tenant_sid, case_id=tenant_case, role=PartyRole.TENANT)
        )
        await uow.sessions.save(
            _make_session(
                session_id=landlord_sid,
                case_id=landlord_case,
                role=PartyRole.LANDLORD,
            )
        )
        dispute = DisputeCase(
            dispute_id=dispute_id,
            invite_code=invite,
            created_by_role="tenant",
        )
        dispute.link_tenant_session(tenant_sid)
        dispute.link_landlord_session(landlord_sid)
        await uow.disputes.save(dispute)

    svc = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=mock_engine,
        graph_builder=mock_graph_builder,
    )
    await svc.generate_prediction(tenant_case)

    async with UnitOfWork(db_sessionmaker) as uow:
        state = await uow.sessions.get(landlord_sid)
        assert state is not None
        state.updated_at = "2026-01-01T00:02:00"
        await uow.sessions.save(state)

    predictions = await svc.list_predictions_for_case(tenant_case)
    assert pred_id not in {p["prediction_id"] for p in predictions}

    async with UnitOfWork(db_sessionmaker) as uow:
        row_result = await uow.session.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id)
        )
        row = row_result.scalar_one()
        assert row.cached_prediction_id is None
        assert row.prediction_cache_key is None
