import json
from pathlib import Path

from scripts.migrations.backfill_json_to_postgres import dry_run


def test_dry_run_reports_planned_counts(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_x.json").write_text(json.dumps({
        "session_id": "x", "case_file": {"case_id": "c", "user_role": "tenant"},
        "messages": [], "current_stage": "greeting",
        "started_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        "stages_completed": [], "current_stage_attempts": 0,
        "last_extraction_successful": True, "extraction_errors": [],
        "role_explicitly_set": False,
    }))

    report = dry_run(tmp_path)

    assert report["planned"]["sessions"] == 1
    assert report["invalid"] == []
