"""Integration test for backfill verify mode."""

import json
from pathlib import Path

import pytest

from scripts.migrations.backfill_json_to_postgres import commit, verify


def _write_session(data_dir: Path, session_id="sess-x", case_id="case-x") -> None:
    """Write a fully-populated session JSON so Pydantic validation is deterministic.

    Fields with default_factory=lambda: datetime.now() (e.g. case_file.created_at)
    must be provided explicitly; otherwise each model_validate call produces a
    different timestamp and the source vs. loaded comparison will always differ.
    """
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


@pytest.mark.asyncio
async def test_verify_clean_after_commit(tmp_path: Path, db_sessionmaker) -> None:
    """Commit then verify — no mismatches."""
    _write_session(tmp_path)
    await commit(tmp_path, db_sessionmaker)
    report = await verify(tmp_path, db_sessionmaker)
    assert report["verified"]["sessions"] == 1
    assert report["mismatches"] == []


@pytest.mark.asyncio
async def test_verify_detects_db_mutation(tmp_path: Path, db_sessionmaker) -> None:
    """If the DB row is mutated after commit, verify reports a diff."""
    from sqlalchemy import update
    from apps.api.src.db.models.sessions import IntakeSessionRow

    _write_session(tmp_path)
    await commit(tmp_path, db_sessionmaker)

    # Mutate the payload directly so the round-trip will differ.
    async with db_sessionmaker() as session:
        await session.execute(
            update(IntakeSessionRow)
            .where(IntakeSessionRow.session_id == "sess-x")
            .values(payload={"session_id": "sess-x", "tampered": True})
        )
        await session.commit()

    report = await verify(tmp_path, db_sessionmaker)
    assert report["verified"]["sessions"] == 0
    assert any(
        m["dir"] == "sessions" and m["key"] == "sess-x" and m["kind"] == "diff"
        for m in report["mismatches"]
    )


@pytest.mark.asyncio
async def test_verify_detects_missing_row(tmp_path: Path, db_sessionmaker) -> None:
    """If a row is deleted, verify reports missing."""
    from sqlalchemy import delete
    from apps.api.src.db.models.sessions import IntakeSessionRow

    _write_session(tmp_path)
    await commit(tmp_path, db_sessionmaker)

    async with db_sessionmaker() as session:
        await session.execute(
            delete(IntakeSessionRow).where(IntakeSessionRow.session_id == "sess-x")
        )
        await session.commit()

    report = await verify(tmp_path, db_sessionmaker)
    assert any(
        m["dir"] == "sessions" and m["key"] == "sess-x" and m["kind"] == "missing"
        for m in report["mismatches"]
    )
