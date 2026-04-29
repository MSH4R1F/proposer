import json
from pathlib import Path

from scripts.migrations.audit_json_stores import audit


def test_audit_counts_files_per_dir(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_a.json").write_text("{}")
    (tmp_path / "sessions" / "session_b.json").write_text("{}")
    (tmp_path / "disputes").mkdir()
    (tmp_path / "disputes" / "dispute_x.json").write_text("{}")

    report = audit(tmp_path)

    assert report["counts"]["sessions"] == 2
    assert report["counts"]["disputes"] == 1
    assert report["counts"].get("predictions", 0) == 0


def test_audit_reports_pydantic_validation_errors(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_bad.json").write_text(
        '{"session_id": "x"}'  # missing required fields
    )

    report = audit(tmp_path)

    assert any(
        e["dir"] == "sessions" and e["file"].endswith("session_bad.json")
        for e in report["validation_errors"]
    )
