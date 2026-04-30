"""Phase 11.3: --archive-json finalization step."""

import json
from pathlib import Path

import pytest

from scripts.migrations.backfill_json_to_postgres import (
    archive_json, BackfillError, commit,
)


@pytest.mark.asyncio
async def test_archive_moves_data_dirs_outside_repo(
    tmp_path, db_sessionmaker,
):
    src = tmp_path / "data"
    archive_root = tmp_path / "archive"
    src.mkdir()
    (src / "sessions").mkdir()
    # case_file.created_at / updated_at must be explicit so that
    # model_validate produces the same timestamp each call (no default_factory
    # drift between commit and verify).
    (src / "sessions" / "sess_x.json").write_text(json.dumps({
        "session_id": "sess-x",
        "case_file": {
            "case_id": "case-x",
            "user_role": "tenant",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        },
        "messages": [], "current_stage": "greeting",
        "started_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "stages_completed": [], "current_stage_attempts": 0,
        "last_extraction_successful": True, "extraction_errors": [],
        "role_explicitly_set": False,
    }))

    await commit(src, db_sessionmaker)
    manifest = await archive_json(src, archive_root, sessionmaker=db_sessionmaker)

    # source dir should no longer have sessions/
    assert not (src / "sessions").exists()
    # archive should have sessions/sess_x.json under timestamped dir
    archived = list(archive_root.rglob("sess_x.json"))
    assert len(archived) == 1
    # manifest written into the repo
    manifests = list(src.glob("_archive_manifest_*.json"))
    assert len(manifests) == 1


@pytest.mark.asyncio
async def test_archive_refuses_archive_inside_data_dir(tmp_path, db_sessionmaker):
    src = tmp_path / "data"
    archive_inside = src / "archive"
    src.mkdir()
    archive_inside.mkdir(parents=True)
    with pytest.raises(BackfillError, match="inside data dir"):
        await archive_json(src, archive_inside, sessionmaker=db_sessionmaker)
