"""SHA-20 Phase 4 closure: tests for the ``cleanup-corpus`` CLI subcommand.

The CLI lists corpus version directories under
``data_dir/corpora/{namespace_id}/``, retains the latest ``--keep-last``
+ any version still referenced by persisted predictions, and deletes the
rest only when ``--apply`` is passed.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from rag_engine.cli import cli


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Strip ``DATABASE_URL`` so the CLI's optional DB lookup short-circuits."""
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _populate_versions(data_dir: Path, namespace_id: str, versions: list[str]) -> Path:
    root = data_dir / "corpora" / namespace_id
    root.mkdir(parents=True, exist_ok=True)
    for v in versions:
        (root / v).mkdir(exist_ok=True)
        (root / v / "manifest.json").write_text("{}")
    return root


def test_cleanup_corpus_dry_run_default_no_deletion(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    versions = ["v_2024_01", "v_2024_06", "v_2025_01", "v_2025_06"]
    root = _populate_versions(data_dir, "housing_deposit_v1_legacy", versions)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--data-dir",
            str(data_dir),
            "cleanup-corpus",
            "--domain",
            "housing.deposit.v1",
            "--keep-last",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    # No deletions on dry-run.
    for v in versions:
        assert (root / v).exists()
    # Output mentions dry-run.
    assert "dry-run" in result.output


def test_cleanup_corpus_apply_deletes_old_versions(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    versions = ["v_2024_01", "v_2024_06", "v_2025_01", "v_2025_06"]
    root = _populate_versions(data_dir, "housing_deposit_v1_legacy", versions)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--data-dir",
            str(data_dir),
            "cleanup-corpus",
            "--domain",
            "housing.deposit.v1",
            "--keep-last",
            "2",
            "--apply",
        ],
    )
    assert result.exit_code == 0, result.output
    # The two newest versions remain.
    assert (root / "v_2025_06").exists()
    assert (root / "v_2025_01").exists()
    # Older versions removed.
    assert not (root / "v_2024_06").exists()
    assert not (root / "v_2024_01").exists()


def test_cleanup_corpus_no_corpora_dir_is_a_no_op(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--data-dir",
            str(data_dir),
            "cleanup-corpus",
            "--domain",
            "housing.deposit.v1",
            "--keep-last",
            "2",
            "--apply",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "nothing to clean up" in result.output.lower()


def test_cleanup_corpus_rejects_keep_last_zero(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--data-dir",
            str(data_dir),
            "cleanup-corpus",
            "--domain",
            "housing.deposit.v1",
            "--keep-last",
            "0",
        ],
    )
    assert result.exit_code != 0
    assert "keep-last" in result.output


def test_cleanup_corpus_rejects_unknown_namespace(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--data-dir",
            str(data_dir),
            "cleanup-corpus",
            "--domain",
            "housing.deposit.v1",
            "--namespace-id",
            "does_not_exist",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
