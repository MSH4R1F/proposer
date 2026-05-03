"""Tests for ``scripts/eval/adjudicate.py`` (Phase 11).

End-to-end on a synthetic fixture: pre-build an artifact via Phase 10,
then run ``adjudicate.py append`` with a decisions JSON. The append gate
must pass and a row must land in the corpus JSONL.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(_SCRIPTS))


def _load_module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _auto_label_cli():
    return _load_module("auto_label_cli", _SCRIPTS / "auto_label.py")


def _adjudicate_cli():
    return _load_module("adjudicate_cli", _SCRIPTS / "adjudicate.py")


_FIXTURES = Path(__file__).parent / "fixtures"


def _build_artifact(tmp_path: Path) -> tuple[Path, Path]:
    """Run auto_label.py offline to land an artifact, return (artifact, artifacts_root)."""
    cli = _auto_label_cli()
    pdf = tmp_path / "FTT-2023-0001.txt"
    pdf.write_text("Tenant occupied flat from 2022-01-01 to 2023-05-31.")
    canned = tmp_path / "canned.json"
    canned.write_text(json.dumps({"facts": "tenant moved out"}))
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
            "--gold-schema-hash",
            "g" * 16,
            "--corpus-manifest-hash",
            "c" * 16,
            "--offline",
            "--canned-a",
            str(canned),
            "--canned-b",
            str(canned),
        ]
    )
    assert rc == 0
    artifact = artifacts_root / "run-test-001" / "FTT-2023-0001.json"
    assert artifact.exists()
    return artifact, artifacts_root


def _decisions_payload(case_id: str = "FTT-2023-0001") -> dict:
    """Hand-build a complete adjudicator decision for an end-to-end run."""
    base = json.loads((_FIXTURES / "gold_case_minimal.json").read_text())
    base["case_id"] = case_id
    base["source_pdf_sha256"] = "0" * 64  # filled-in by the test below
    base["domain_id"] = "housing.deposit.v1"
    base["forum"] = "ftt_pc"
    base["retrieval_namespace_id"] = "housing.deposit.v1"
    base["target_source_id"] = "src-housing-deposit-2023-0001"
    base["corpus_version"] = "housing_v1@2026-05-03"
    base["source_publisher"] = "ftt"
    base["source_kind"] = "tribunal_decision"
    base["source_license"] = "OGL-3.0"
    base["matter_type"] = "deposit_deduction"

    # MandatoryReviewSet coverage: every field in the constant + per-issue
    # paths derived from the case's per_issue list.
    from eval.auto_label.append_gate import MANDATORY_REVIEW_FIELDS

    paths: set[str] = set(MANDATORY_REVIEW_FIELDS)
    for io in base["ground_truth_outcome"]["per_issue"]:
        paths.add(f"ground_truth_outcome.per_issue[issue={io['issue']}].winner")
        paths.add(f"ground_truth_outcome.per_issue[issue={io['issue']}].awarded_gbp")

    field_provenance = [
        {
            "field_path": p,
            "source": "human_mandatory_review",
            "source_spans": [{"page": 1, "paragraph": 2}],
            "reviewer_rationale": "confirmed against PDF",
        }
        for p in sorted(paths)
    ]

    return {
        "case": base,
        "labeling_provenance": {
            "human_adjudicator": "Mohamed",
            "labeler_models": [
                {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                {"provider": "openai", "model": "gpt-5.5"},
            ],
            "is_human_only_anchor": False,
            "anchor_set_id": None,
            "mandatory_review_completed_at": datetime(
                2026, 5, 3, 13, 0, tzinfo=timezone.utc
            ).isoformat(),
            "adjudicated_fields": ["facts"],
            "inter_model_agreement_rate": 0.95,
            "audit_flip_rate": 0.05,
            "mandatory_review_flip_rate": 0.10,
            "field_provenance": field_provenance,
        },
    }


# ---------------------------------------------------------------------------
# list / queues subcommands
# ---------------------------------------------------------------------------


class TestListSubcommand:
    def test_list_prints_artifact_path(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _build_artifact(tmp_path)
        cli = _adjudicate_cli()
        rc = cli._cli_main(  # type: ignore[attr-defined]
            [
                "list",
                "--artifacts-root",
                str(tmp_path / "artifacts"),
                "--run-id",
                "run-test-001",
            ]
        )
        assert rc == 0
        captured = capsys.readouterr().out
        assert "FTT-2023-0001" in captured


class TestQueuesSubcommand:
    def test_queues_emits_three_buckets(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _build_artifact(tmp_path)
        capsys.readouterr()  # drain the auto_label "Wrote ..." line
        cli = _adjudicate_cli()
        rc = cli._cli_main(  # type: ignore[attr-defined]
            [
                "queues",
                "--artifacts-root",
                str(tmp_path / "artifacts"),
                "--run-id",
                "run-test-001",
                "--case-id",
                "FTT-2023-0001",
                "--audit-seed",
                "1",
            ]
        )
        assert rc == 0
        body = json.loads(capsys.readouterr().out)
        assert "mandatory_review" in body
        assert "disagreements" in body
        assert "audit_overlay" in body
        # MandatoryReviewSet always has the core fields populated.
        assert "facts" in body["mandatory_review"]
        assert "ground_truth_outcome.overall_winner" in body["mandatory_review"]

    def test_queues_include_unapportioned_reason_when_labeler_emits_it(
        self,
        tmp_path: Path,
    ) -> None:
        artifact_path, _artifacts_root = _build_artifact(tmp_path)
        artifact = json.loads(artifact_path.read_text())
        for side in ("labeler_a", "labeler_b"):
            artifact[side]["partial_case"]["ground_truth_outcome"] = {
                "overall_winner": "tenant",
                "total_awarded_gbp": "220.00",
                "per_issue": [],
                "unapportioned_reason": "Tribunal gave one global figure.",
            }
        cli = _adjudicate_cli()
        queues = cli.derive_queues(artifact, audit_seed=1)  # type: ignore[attr-defined]
        assert (
            "ground_truth_outcome.unapportioned_reason"
            in queues["mandatory_review"]
        )
        assert not any("per_issue" in p for p in queues["mandatory_review"])


# ---------------------------------------------------------------------------
# append subcommand — end-to-end
# ---------------------------------------------------------------------------


class TestAppendSubcommand:
    def test_end_to_end_appends_to_jsonl(self, tmp_path: Path) -> None:
        artifact_path, artifacts_root = _build_artifact(tmp_path)
        artifact = json.loads(artifact_path.read_text())

        decisions = _decisions_payload()
        # Match artifact hashes so the append gate's hash check passes.
        decisions["case"]["source_pdf_sha256"] = artifact["source_pdf_sha256"]
        # The CLI must derive the persisted model provenance from the artifact,
        # not trust a human decisions file to echo the richer LabelerModelSpec.
        decisions["labeling_provenance"]["labeler_models"] = [
            {"provider": "openai", "model": "wrong-model", "store": False}
        ]

        decisions_path = tmp_path / "decisions.json"
        decisions_path.write_text(json.dumps(decisions))

        gold_dir = tmp_path / "gold"
        reviewer_log = tmp_path / "reviewer-log.md"

        cli = _adjudicate_cli()
        rc = cli._cli_main(  # type: ignore[attr-defined]
            [
                "append",
                "--artifacts-root",
                str(artifacts_root),
                "--run-id",
                "run-test-001",
                "--case-id",
                "FTT-2023-0001",
                "--decisions",
                str(decisions_path),
                "--gold-corpus",
                "housing_v1",
                "--gold-dir",
                str(gold_dir),
                "--reviewer-log",
                str(reviewer_log),
            ]
        )
        assert rc == 0

        jsonl = gold_dir / "housing_v1.jsonl"
        assert jsonl.exists()
        rows = jsonl.read_text().splitlines()
        assert len(rows) == 1
        appended = json.loads(rows[0])
        assert appended["case_id"] == "FTT-2023-0001"
        assert appended["labeling_provenance"]["run_id"] == "run-test-001"
        assert appended["labeling_provenance"]["human_adjudicator"] == "Mohamed"
        assert appended["labeling_provenance"]["labeler_models"] == [
            {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "api_version": None},
            {"provider": "openai", "model": "gpt-5.5", "api_version": None},
        ]
        # Reviewer log row landed.
        assert reviewer_log.exists()
        log = reviewer_log.read_text()
        assert "FTT-2023-0001" in log
        assert "Mohamed" in log

    def test_append_refuses_when_provenance_incomplete(self, tmp_path: Path) -> None:
        artifact_path, artifacts_root = _build_artifact(tmp_path)
        artifact = json.loads(artifact_path.read_text())
        decisions = _decisions_payload()
        decisions["case"]["source_pdf_sha256"] = artifact["source_pdf_sha256"]
        # Strip MandatoryReviewSet coverage to provoke the gate.
        decisions["labeling_provenance"]["field_provenance"] = []
        decisions_path = tmp_path / "decisions.json"
        decisions_path.write_text(json.dumps(decisions))

        cli = _adjudicate_cli()
        rc = cli._cli_main(  # type: ignore[attr-defined]
            [
                "append",
                "--artifacts-root",
                str(artifacts_root),
                "--run-id",
                "run-test-001",
                "--case-id",
                "FTT-2023-0001",
                "--decisions",
                str(decisions_path),
                "--gold-corpus",
                "housing_v1",
                "--gold-dir",
                str(tmp_path / "gold"),
                "--reviewer-log",
                str(tmp_path / "reviewer-log.md"),
            ]
        )
        assert rc == 1  # gate refused
        # No jsonl created.
        assert not (tmp_path / "gold" / "housing_v1.jsonl").exists()
