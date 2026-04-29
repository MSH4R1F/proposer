"""Integration test for dump_postgres_to_json rollback round-trip."""

import json
from pathlib import Path

import pytest

from scripts.migrations.backfill_json_to_postgres import commit
from scripts.migrations.dump_postgres_to_json import dump


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _write_session(data_dir: Path, session_id: str = "sess-x", case_id: str = "case-x") -> None:
    (data_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (data_dir / "sessions" / f"{session_id}.json").write_text(json.dumps({
        "session_id": session_id,
        "case_file": {
            "case_id": case_id,
            "user_role": "tenant",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        },
        "messages": [],
        "current_stage": "greeting",
        "started_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "stages_completed": [],
        "current_stage_attempts": 0,
        "last_extraction_successful": True,
        "extraction_errors": [],
        "role_explicitly_set": False,
    }))


def _write_evidence(
    data_dir: Path, case_id: str = "case-x", evidence_id: str = "ev-1"
) -> None:
    sub = data_dir / "evidence_metadata" / case_id
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"{evidence_id}.json").write_text(json.dumps({
        "case_id": case_id,
        "evidence_id": evidence_id,
        "evidence_type": "receipts",
        "file_url": "https://example.com/foo",
        "file_name": "foo.pdf",
        "file_type": "application/pdf",
        "description": "A receipt",
        "extracted_text": None,
        "image_description": None,
    }))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_then_dump_roundtrip(
    tmp_path: Path,
    db_sessionmaker,
) -> None:
    """Backfill + dump produces the same shape (with same payloads) as the source."""
    src = tmp_path / "src"
    out = tmp_path / "dump"
    _write_session(src)
    _write_evidence(src)

    await commit(src, db_sessionmaker)
    counts = await dump(db_sessionmaker, out)

    assert counts["sessions"] == 1
    assert counts["evidence_metadata"] == 1

    # Compare round-trip equality after passing through Pydantic — raw JSON key
    # ordering / formatting differences don't matter; only semantic equality does.
    from packages.llm_orchestrator.models.conversation import ConversationState
    from packages.llm_orchestrator.models.evidence import EvidenceMetadata

    src_session = ConversationState.model_validate(
        json.loads((src / "sessions" / "sess-x.json").read_text())
    )
    dumped_session = ConversationState.model_validate(
        json.loads((out / "sessions" / "session_sess-x.json").read_text())
    )
    assert src_session.model_dump(mode="json") == dumped_session.model_dump(mode="json")

    src_evidence = EvidenceMetadata.model_validate(
        json.loads((src / "evidence_metadata" / "case-x" / "ev-1.json").read_text())
    )
    dumped_evidence = EvidenceMetadata.model_validate(
        json.loads((out / "evidence_metadata" / "case-x" / "ev-1.json").read_text())
    )
    assert src_evidence.model_dump(mode="json") == dumped_evidence.model_dump(mode="json")


@pytest.mark.asyncio
async def test_dump_emits_dispute_predictions_mapping(
    tmp_path: Path,
    db_sessionmaker,
) -> None:
    """Dispute with cached_prediction_id should produce a dispute_predictions/<id>.json file."""
    from apps.api.src.db.repositories import DisputesRepo, PredictionsRepo
    from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus
    from packages.llm_orchestrator.models.case_file import PartyRole
    from packages.llm_orchestrator.models.prediction_v2 import (
        OutcomeType,
        PredictionResult,
    )

    # Build a prediction + dispute with cached_prediction_id wired up.
    async with db_sessionmaker() as session:
        pred_repo = PredictionsRepo(session)
        disp_repo = DisputesRepo(session)

        p = PredictionResult(
            case_id="case-1",
            prediction_id="p-1",
            timestamp="2026-01-01T00:00:00",
            overall_outcome=OutcomeType.SPLIT,
            overall_confidence=0.5,
            outcome_summary="x",
            tenant_recovery_amount=0.0,
            landlord_recovery_amount=0.0,
            issue_predictions=[],
            reasoning_trace=[],
            retrieved_cases=[],
            total_cases_analyzed=1,
            key_strengths=[],
            key_weaknesses=[],
            uncertainties=[],
            missing_information=[],
            model_version="2.0",
            pipeline_version="v2",
        )
        d = DisputeCase(
            dispute_id="DISP-1",
            invite_code="ABC",
            status=DisputeStatus.WAITING_FOR_LANDLORD,
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            created_by_role=PartyRole.TENANT,
        )
        await pred_repo.save(p)
        await disp_repo.save(d)
        await disp_repo.set_cached_prediction_id("DISP-1", "p-1")
        await session.commit()

    out = tmp_path / "dump"
    counts = await dump(db_sessionmaker, out)
    assert counts["dispute_predictions"] == 1

    mapping_path = out / "dispute_predictions" / "DISP-1.json"
    assert mapping_path.exists()
    mapping = json.loads(mapping_path.read_text())
    assert mapping == {"dispute_id": "DISP-1", "prediction_id": "p-1"}
