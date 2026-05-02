"""Tests for scripts/eval/predict_all.py — the Phase 5b live runner.

The runner loops `(gold_case, mode)` pairs through:
  gold_case_to_case_file → predict_fn → from_prediction_result → JSONL

In `--engine stub` mode (default), `predict_fn = make_stub_prediction`,
no LLM is called, and the runner produces 4 prediction JSONLs (one per
mode) plus an alignment summary. CI exercises this path.

`--engine live` is a TODO sentinel — raises NotImplementedError with a
clear message until a real LLM client is wired in.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Import the script as a module via importlib so we can call _cli_main /
# _run directly. The entry point is scripts/eval/predict_all.py.
SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "eval" / "predict_all.py"
)


def _import_script_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("eval_predict_all", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIXTURES = Path(__file__).parent / "fixtures"
GOLD_PATH = FIXTURES / "synthetic_corpus_10.jsonl"


# ---------- In-process ----------


class TestStubModeWritesPerModeJsonl:
    def test_default_writes_four_files(self, tmp_path):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
            ]
        )
        assert rc == 0
        for mode in ("hybrid", "rag_only", "kg_only", "llm_only"):
            assert (tmp_path / f"{mode}.jsonl").exists()

    def test_each_jsonl_has_one_row_per_gold_case(self, tmp_path):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
            ]
        )
        assert rc == 0
        for mode in ("hybrid", "rag_only", "kg_only", "llm_only"):
            with (tmp_path / f"{mode}.jsonl").open() as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 10
            for row in lines:
                # eval.run._load_predictions and eval.compare expect these keys
                assert "case_id" in row
                assert "overall_winner" in row
                assert "overall_win_probability" in row
                assert "total_predicted_gbp" in row
                assert "per_issue" in row

    def test_modes_filter_writes_only_requested(self, tmp_path):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
                "--modes",
                "hybrid,llm_only",
            ]
        )
        assert rc == 0
        assert (tmp_path / "hybrid.jsonl").exists()
        assert (tmp_path / "llm_only.jsonl").exists()
        assert not (tmp_path / "rag_only.jsonl").exists()
        assert not (tmp_path / "kg_only.jsonl").exists()

    def test_limit_caps_case_count(self, tmp_path):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
                "--limit",
                "3",
                "--modes",
                "hybrid",
            ]
        )
        assert rc == 0
        with (tmp_path / "hybrid.jsonl").open() as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 3

    def test_unambiguous_gold_issue_labels_are_used_for_metric_join(self, tmp_path):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
                "--limit",
                "1",
                "--modes",
                "hybrid",
            ]
        )
        assert rc == 0
        row = json.loads((tmp_path / "hybrid.jsonl").read_text().splitlines()[0])
        assert row["per_issue"][0]["issue"] == "primary_issue"


class TestAlignmentReport:
    def test_summary_reports_unmappable_claim_types(self, tmp_path, capsys):
        mod = _import_script_module()
        # synthetic_corpus_10 includes SYN-DISREPAIR (disrepair) +
        # SYN-EOT (end_of_tenancy) which are unmappable.
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
                "--modes",
                "hybrid",
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "disrepair" in captured.out
        assert "end_of_tenancy" in captured.out


class TestLiveModeRequiresExplicitClient:
    """SHA-20 Phase 7: --engine live requires --client; refuses to run
    silently against the stub. The deterministic stub client is the test
    path; production clients (claude/openai) need credentials."""

    def test_engine_live_without_client_returns_nonzero(self, tmp_path, capsys):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "live",
                "--modes",
                "hybrid",
            ]
        )
        assert rc != 0
        captured = capsys.readouterr()
        assert "client" in captured.err.lower()

    def test_engine_live_with_client_stub_runs(self, tmp_path):
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "live",
                "--client",
                "stub",
                "--modes",
                "hybrid",
                "--limit",
                "1",
            ]
        )
        assert rc == 0
        assert (tmp_path / "hybrid.jsonl").exists()


# ---------- Subprocess (real entry point) ----------


class TestSubprocessEntry:
    def test_invoking_script_writes_jsonl(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
                "--modes",
                "hybrid",
            ],
            cwd=str(SCRIPT_PATH.resolve().parents[2]),
            env={
                **os.environ,
                "PYTHONPATH": str(SCRIPT_PATH.resolve().parents[2] / "packages"),
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "hybrid.jsonl").exists()


# ---------- Output integrates with eval.ablate ----------


class TestOutputAblationCompatible:
    def test_predictions_round_trip_through_eval_ablate(self, tmp_path):
        """End-to-end: gold → predict_all → eval.ablate produces a
        valid ComparisonReport. This is the chain SHA-68 will replay."""
        mod = _import_script_module()
        rc = mod._cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--out-dir",
                str(tmp_path),
                "--engine",
                "stub",
            ]
        )
        assert rc == 0

        from eval.ablate import _cli_main as ablate_main

        report_path = tmp_path / "report.json"
        rc_a = ablate_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={tmp_path / 'hybrid.jsonl'}",
                "--predictions",
                f"rag_only={tmp_path / 'rag_only.jsonl'}",
                "--predictions",
                f"kg_only={tmp_path / 'kg_only.jsonl'}",
                "--predictions",
                f"llm_only={tmp_path / 'llm_only.jsonl'}",
                "--out",
                str(report_path),
                "--no-bootstrap",
            ]
        )
        assert rc_a == 0
        report = json.loads(report_path.read_text())
        assert report["n_cases"] == 10
        assert {m["mode"] for m in report["modes"]} == {
            "hybrid",
            "rag_only",
            "kg_only",
            "llm_only",
        }
