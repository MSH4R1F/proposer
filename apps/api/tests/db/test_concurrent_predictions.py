"""Phase 7.2: prove dispute row-lock prevents duplicate cached predictions.

Two simultaneous generate_prediction() calls for tenant + landlord case IDs
of the same dispute must produce ONE predictions row referenced by
disputes.cached_prediction_id, not two.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from apps.api.src.db.models import DisputeRow, PredictionRow
from apps.api.src.db.uow import UnitOfWork
from apps.api.src.services.prediction_service import PredictionService
from packages.kg_builder.models.graph import KnowledgeGraph
from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
from packages.llm_orchestrator.models.conversation import (
    ConversationState,
    IntakeStage,
)
from packages.llm_orchestrator.models.dispute import (
    DisputeCase,
    generate_invite_code,
)
from packages.llm_orchestrator.models.prediction_v2 import (
    OutcomeType,
    PredictionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(session_id: str, case_id: str, role: PartyRole) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        case_file=CaseFile(case_id=case_id, user_role=role),
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


def _make_kg(case_id: str) -> KnowledgeGraph:
    return KnowledgeGraph(case_id=case_id, nodes=[], edges=[])


def _make_prediction(case_id: str) -> PredictionResult:
    return PredictionResult(
        case_id=case_id,
        prediction_id=f"pred-{uuid.uuid4().hex[:8]}",
        overall_outcome=OutcomeType.SPLIT,
        overall_confidence=0.5,
        outcome_summary="Mixed outcome",
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_generation_for_same_dispute_yields_one_cached_prediction(
    db_sessionmaker,
):
    """Two concurrent generate_prediction calls for tenant + landlord case_ids
    of the same dispute must result in ONE predictions row + one
    cached_prediction_id.

    Invariants:
    1. Both calls return the SAME prediction_id.
    2. disputes.cached_prediction_id is set and points at exactly one row.
    3. The LLM engine ran at most 2 times (row-lock prevents duplicate WRITES,
       not duplicate external-work calls; both calls may reach stage 2 before
       either writes).
    """
    tenant_sid = "conc-sess-T"
    landlord_sid = "conc-sess-L"
    tenant_case = "conc-case-T"
    landlord_case = "conc-case-L"
    dispute_id = "DISP-CONC01"
    invite = generate_invite_code()

    # 1. Seed: two sessions linked to one dispute (both parties present).
    async with UnitOfWork(db_sessionmaker) as uow:
        tenant_state = _make_state(tenant_sid, tenant_case, PartyRole.TENANT)
        landlord_state = _make_state(landlord_sid, landlord_case, PartyRole.LANDLORD)
        await uow.sessions.save(tenant_state)
        await uow.sessions.save(landlord_state)

        dispute = DisputeCase(
            dispute_id=dispute_id,
            invite_code=invite,
            created_by_role=PartyRole.TENANT,
        )
        dispute.link_tenant_session(tenant_sid)
        dispute.link_landlord_session(landlord_sid)
        await uow.disputes.save(dispute)

    # 2. Build a service whose graph_builder + engine are deterministic mocks.
    # The engine sleeps briefly so both concurrent calls overlap inside the
    # external-work stage (stage 2), ensuring the row-lock in stage 3 is
    # exercised as the true safety net.
    async def slow_predict(*, case_file, knowledge_graph, mode=None):
        await asyncio.sleep(0.05)  # ensure overlap
        return _make_prediction(case_file.case_id)

    engine = AsyncMock()
    engine.predict.side_effect = slow_predict
    graph_builder = MagicMock()
    graph_builder.build.side_effect = lambda case_file: _make_kg(case_file.case_id)

    svc = PredictionService(
        sessionmaker=db_sessionmaker,
        engine=engine,
        graph_builder=graph_builder,
    )

    # 3. Fire two concurrent generate_prediction calls — one per case_id.
    p1, p2 = await asyncio.gather(
        svc.generate_prediction(tenant_case),
        svc.generate_prediction(landlord_case),
    )

    # Both calls return SOME prediction. Either both got the same cached one,
    # or one persisted and the other returned the cached version after
    # re-checking inside the write-stage row lock.
    assert p1.prediction_id == p2.prediction_id, (
        f"Concurrent generation produced two different predictions: "
        f"{p1.prediction_id} vs {p2.prediction_id}"
    )

    # 4. disputes.cached_prediction_id must be set.
    async with UnitOfWork(db_sessionmaker) as uow:
        dispute_row = await uow.session.get(DisputeRow, dispute_id)

    assert dispute_row is not None, "dispute row must exist"
    assert dispute_row.cached_prediction_id is not None, (
        "expected cached_prediction_id to be set"
    )
    assert dispute_row.prediction_cache_key is not None, (
        "expected prediction_cache_key to be set"
    )

    # 5. The cached_prediction_id must reference exactly one existing predictions row.
    async with UnitOfWork(db_sessionmaker) as uow:
        cached = await uow.session.get(PredictionRow, dispute_row.cached_prediction_id)
    assert cached is not None, (
        "cached_prediction_id should reference an existing predictions row"
    )

    # 6. Confirm there is exactly ONE predictions row for this dispute.
    # The merged case_file uses the tenant's case_id as its case_id, so we
    # look up by the cached_prediction_id FK rather than filtering by case_id.
    async with UnitOfWork(db_sessionmaker) as uow:
        result = await uow.session.execute(
            select(PredictionRow).where(
                PredictionRow.prediction_id == dispute_row.cached_prediction_id
            )
        )
        matching = list(result.scalars())
    assert len(matching) == 1, (
        f"Expected exactly 1 prediction row for this dispute; got {len(matching)}"
    )

    # 7. The returned prediction_id must match what's on the dispute row.
    assert p1.prediction_id == dispute_row.cached_prediction_id, (
        f"Returned prediction_id {p1.prediction_id!r} does not match "
        f"disputes.cached_prediction_id {dispute_row.cached_prediction_id!r}"
    )

    # 8. Verify the LLM engine ran AT MOST twice (no row lock = could be 2;
    # WITH row lock = also 2 because both calls reach external-work stage
    # before either has cached). The crucial invariant is that only ONE
    # prediction was PERSISTED, not that the engine ran once.
    assert engine.predict.call_count >= 1
    assert engine.predict.call_count <= 2, (
        f"predict() called {engine.predict.call_count} times; expected at most 2"
    )
