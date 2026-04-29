"""Integration test for backfill commit mode against pytest-postgresql."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.migrations.backfill_json_to_postgres import BackfillError, commit
from apps.api.src.db.repositories import (
    DisputesRepo,
    EvidenceRepo,
    KnowledgeGraphRepo,
    MediationsRepo,
    PredictionsRepo,
    SessionsRepo,
)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _write_session(data_dir: Path) -> None:
    (data_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (data_dir / "sessions" / "sess_x.json").write_text(json.dumps({
        "session_id": "sess-x",
        "case_file": {"case_id": "case-x", "user_role": "tenant"},
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


def _write_dispute(data_dir: Path, dispute_id: str = "DISP-1", invite: str = "ABC123") -> None:
    (data_dir / "disputes").mkdir(parents=True, exist_ok=True)
    (data_dir / "disputes" / f"{dispute_id}.json").write_text(json.dumps({
        "dispute_id": dispute_id,
        "invite_code": invite,
        "status": "waiting_for_landlord",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by_role": "tenant",
        "tenant_session_id": None,
        "landlord_session_id": None,
        "property_address": None,
        "property_postcode": None,
        "deposit_amount": None,
        "notes": None,
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
async def test_backfill_commits_session_dispute_evidence(
    tmp_path: Path,
    db_sessionmaker,
) -> None:
    """End-to-end: write JSON files, run commit, verify rows present via repos."""
    _write_session(tmp_path)
    _write_dispute(tmp_path)
    _write_evidence(tmp_path)

    counts = await commit(tmp_path, db_sessionmaker)

    assert counts["sessions"] == 1
    assert counts["disputes"] == 1
    assert counts["evidence_metadata"] == 1

    # Read back through repos using a fresh session from the same DB.
    async with db_sessionmaker() as fresh:
        sessions_repo = SessionsRepo(fresh)
        disputes_repo = DisputesRepo(fresh)
        evidence_repo = EvidenceRepo(fresh)

        s = await sessions_repo.get("sess-x")
        assert s is not None
        assert s.case_file.case_id == "case-x"

        d = await disputes_repo.get("DISP-1")
        assert d is not None
        assert d.invite_code == "ABC123"

        e = await evidence_repo.get("case-x", "ev-1")
        assert e is not None
        assert e.evidence_type == "receipts"


@pytest.mark.asyncio
async def test_backfill_is_idempotent(tmp_path: Path, db_sessionmaker) -> None:
    """Running commit twice should not error and return equal counts."""
    _write_session(tmp_path)
    _write_dispute(tmp_path)
    counts1 = await commit(tmp_path, db_sessionmaker)
    counts2 = await commit(tmp_path, db_sessionmaker)
    assert counts1 == counts2


@pytest.mark.asyncio
async def test_backfill_refuses_on_invalid_source(
    tmp_path: Path,
    db_sessionmaker,
) -> None:
    """If preflight finds invalid JSON, commit raises and no rows are written."""
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)
    # Missing required fields — Pydantic validation will fail.
    (tmp_path / "sessions" / "bad.json").write_text(json.dumps({"session_id": "x"}))

    with pytest.raises(BackfillError):
        await commit(tmp_path, db_sessionmaker)

    # Verify nothing was persisted.
    async with db_sessionmaker() as check:
        repo = SessionsRepo(check)
        assert await repo.get("x") is None
