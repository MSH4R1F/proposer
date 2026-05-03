"""Tests for ``scripts/eval/auto_label.py`` (Phase 10).

End-to-end on a synthetic fixture, no real network call. The CLI is
called in-process via ``_cli_main(argv=...)`` so we don't pay subprocess
overhead and so we can inject a stub client factory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(_SCRIPTS))


def _import_cli() -> object:
    """Import scripts/eval/auto_label.py as a module for in-process calls."""
    import importlib.util

    if "auto_label_cli" in sys.modules:
        return sys.modules["auto_label_cli"]
    spec = importlib.util.spec_from_file_location(
        "auto_label_cli", _SCRIPTS / "auto_label.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auto_label_cli"] = mod  # register BEFORE exec for dataclass
    spec.loader.exec_module(mod)
    return mod


class TestAutoLabelOfflineEndToEnd:
    def test_offline_run_writes_artifact(self, tmp_path: Path) -> None:
        cli = _import_cli()

        pdf = tmp_path / "FTT-2023-0001.txt"
        pdf.write_text(
            "The tenant occupied the flat from 2022 until 2023. "
            "The landlord retained 400 GBP of the deposit citing carpet damage."
        )

        canned_a = tmp_path / "canned_a.json"
        canned_a.write_text(
            json.dumps(
                {
                    "facts": "Tenant occupied the flat then moved out; deposit partly retained.",
                    "claim_types": ["cleaning"],
                }
            )
        )
        canned_b = tmp_path / "canned_b.json"
        canned_b.write_text(
            json.dumps(
                {
                    "facts": "Tenant lived at the property; landlord kept 400 GBP of the deposit.",
                    "claim_types": ["cleaning"],
                }
            )
        )

        artifacts_root = tmp_path / "artifacts"
        rc = cli._cli_main(  # type: ignore[attr-defined]
            [
                "--case-id",
                "FTT-2023-0001",
                "--pdf",
                str(pdf),
                "--domain-id",
                "housing.deposit.v1",
                "--run-id",
                "run-test-001",
                "--labeler-a",
                "anthropic:claude-sonnet-4-20250514",
                "--labeler-b",
                "openai:gpt-5.5",
                "--artifacts-root",
                str(artifacts_root),
                "--offline",
                "--canned-a",
                str(canned_a),
                "--canned-b",
                str(canned_b),
            ]
        )
        assert rc == 0

        artifact = artifacts_root / "run-test-001" / "FTT-2023-0001.json"
        assert artifact.exists(), f"artifact not at {artifact}"
        payload = json.loads(artifact.read_text())
        # Provider independence is replayable from the artifact.
        assert payload["labeler_a"]["spec"]["provider"] == "anthropic"
        assert payload["labeler_b"]["spec"]["provider"] == "openai"
        assert payload["labeler_a"]["partial_case"]["facts"].startswith("Tenant occupied")
        # Every reproducibility hash recorded.
        assert "prompt_template_hash" in payload
        assert "source_pdf_sha256" in payload

    def test_refuses_same_provider_for_a_and_b(self, tmp_path: Path) -> None:
        cli = _import_cli()
        pdf = tmp_path / "x.txt"
        pdf.write_text("hello")
        canned = tmp_path / "c.json"
        canned.write_text("{}")

        with pytest.raises(SystemExit) as exc:
            cli._cli_main(  # type: ignore[attr-defined]
                [
                    "--case-id",
                    "X",
                    "--pdf",
                    str(pdf),
                    "--domain-id",
                    "housing.deposit.v1",
                    "--run-id",
                    "run-x",
                    "--labeler-a",
                    "anthropic:claude-sonnet-4-20250514",
                    "--labeler-b",
                    "anthropic:claude-haiku-4-5-20251001",
                    "--artifacts-root",
                    str(tmp_path / "artifacts"),
                    "--offline",
                    "--canned-a",
                    str(canned),
                    "--canned-b",
                    str(canned),
                ]
            )
        assert "different" in str(exc.value).lower()

    def test_refuses_artifacts_under_gold_standard(self, tmp_path: Path) -> None:
        cli = _import_cli()
        pdf = tmp_path / "x.txt"
        pdf.write_text("hello")
        canned = tmp_path / "c.json"
        canned.write_text("{}")
        bad_root = tmp_path / "data" / "gold_standard"
        bad_root.mkdir(parents=True)

        with pytest.raises(SystemExit) as exc:
            cli._cli_main(  # type: ignore[attr-defined]
                [
                    "--case-id",
                    "X",
                    "--pdf",
                    str(pdf),
                    "--domain-id",
                    "housing.deposit.v1",
                    "--run-id",
                    "run-x",
                    "--labeler-a",
                    "anthropic:claude-sonnet-4-20250514",
                    "--labeler-b",
                    "openai:gpt-5.5",
                    "--artifacts-root",
                    str(bad_root),
                    "--offline",
                    "--canned-a",
                    str(canned),
                    "--canned-b",
                    str(canned),
                ]
            )
        assert "gold_standard" in str(exc.value)
