"""Tests for the `python -m eval.ablate` CLI.

Mix of in-process (`_cli_main`) tests for coverage and one subprocess test
to verify the actual entry point. Reuses the synthetic 10-case fixture +
hand-crafted per-mode prediction JSONLs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from eval.ablate import _cli_main, _parse_predictions_arg
from eval.metrics import IssuePrediction, Prediction
from eval.schema import Winner


FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLD_PATH = FIXTURES_DIR / "synthetic_corpus_10.jsonl"


# ---------- Helpers ----------


def _write_perfect_jsonl(path: Path, gold_cases: list, mode: str) -> None:
    """Write a JSONL of perfect predictions for the given gold corpus."""
    with path.open("w") as f:
        for g in gold_cases:
            gt = g.ground_truth_outcome
            p_landlord = 1.0 if gt.overall_winner is Winner.LANDLORD else 0.0
            per_issue = []
            for io in gt.per_issue:
                per_issue.append(
                    {
                        "issue": io.issue,
                        "predicted_winner": io.winner.value,
                        "win_probability": (
                            1.0 if io.winner is Winner.LANDLORD else 0.0
                        ),
                        "predicted_amount_gbp": str(io.awarded_gbp),
                    }
                )
            row = {
                "case_id": g.case_id,
                "overall_winner": gt.overall_winner.value,
                "overall_win_probability": p_landlord,
                "total_predicted_gbp": str(gt.total_awarded_gbp),
                "per_issue": per_issue,
            }
            f.write(json.dumps(row) + "\n")


def _write_coinflip_jsonl(path: Path, gold_cases: list) -> None:
    with path.open("w") as f:
        for g in gold_cases:
            gt = g.ground_truth_outcome
            per_issue = [
                {
                    "issue": io.issue,
                    "predicted_winner": "split",
                    "win_probability": 0.5,
                    "predicted_amount_gbp": "0",
                }
                for io in gt.per_issue
            ]
            row = {
                "case_id": g.case_id,
                "overall_winner": "split",
                "overall_win_probability": 0.5,
                "total_predicted_gbp": "0",
                "per_issue": per_issue,
            }
            f.write(json.dumps(row) + "\n")


@pytest.fixture
def gold_cases():
    from eval.dataset import load

    return load("synthetic_corpus_10", base_dir=FIXTURES_DIR, strict=True).cases


@pytest.fixture
def perfect_predictions_path(tmp_path: Path, gold_cases) -> Path:
    p = tmp_path / "perfect.jsonl"
    _write_perfect_jsonl(p, gold_cases, mode="hybrid")
    return p


@pytest.fixture
def coinflip_predictions_path(tmp_path: Path, gold_cases) -> Path:
    p = tmp_path / "coinflip.jsonl"
    _write_coinflip_jsonl(p, gold_cases)
    return p


# ---------- Argument parsing ----------


class TestParsePredictionsArg:
    def test_single_mode_path_pair(self):
        out = _parse_predictions_arg(["hybrid=/tmp/h.jsonl"])
        assert out == {"hybrid": Path("/tmp/h.jsonl")}

    def test_multiple_mode_path_pairs(self):
        out = _parse_predictions_arg(
            [
                "hybrid=/tmp/h.jsonl",
                "rag_only=/tmp/r.jsonl",
                "kg_only=/tmp/k.jsonl",
                "llm_only=/tmp/l.jsonl",
            ]
        )
        assert set(out) == {"hybrid", "rag_only", "kg_only", "llm_only"}

    def test_missing_equals_raises(self):
        with pytest.raises(ValueError):
            _parse_predictions_arg(["hybrid"])

    def test_empty_mode_raises(self):
        with pytest.raises(ValueError):
            _parse_predictions_arg(["=/tmp/h.jsonl"])

    def test_empty_path_raises(self):
        with pytest.raises(ValueError):
            _parse_predictions_arg(["hybrid="])

    def test_duplicate_mode_raises(self):
        with pytest.raises(ValueError):
            _parse_predictions_arg(
                ["hybrid=/tmp/a.jsonl", "hybrid=/tmp/b.jsonl"]
            )


# ---------- In-process CLI ----------


class TestInProcessCli:
    def test_writes_report_to_out_path(
        self, tmp_path, gold_cases, perfect_predictions_path
    ):
        out_path = tmp_path / "report.json"
        rc = _cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={perfect_predictions_path}",
                "--out",
                str(out_path),
                "--no-bootstrap",
            ]
        )
        assert rc == 0
        assert out_path.exists()
        report = json.loads(out_path.read_text())
        assert report["n_cases"] == len(gold_cases)
        assert len(report["modes"]) == 1
        assert report["modes"][0]["mode"] == "hybrid"

    def test_two_modes_appear_in_report(
        self,
        tmp_path,
        perfect_predictions_path,
        coinflip_predictions_path,
    ):
        out_path = tmp_path / "two.json"
        rc = _cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={perfect_predictions_path}",
                "--predictions",
                f"llm_only={coinflip_predictions_path}",
                "--out",
                str(out_path),
                "--no-bootstrap",
            ]
        )
        assert rc == 0
        report = json.loads(out_path.read_text())
        modes = {m["mode"] for m in report["modes"]}
        assert modes == {"hybrid", "llm_only"}

    def test_perfect_mode_beats_coinflip_on_accuracy(
        self,
        tmp_path,
        perfect_predictions_path,
        coinflip_predictions_path,
    ):
        out_path = tmp_path / "ranking.json"
        rc = _cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={perfect_predictions_path}",
                "--predictions",
                f"llm_only={coinflip_predictions_path}",
                "--out",
                str(out_path),
                "--no-bootstrap",
            ]
        )
        assert rc == 0
        report = json.loads(out_path.read_text())
        by_mode = {m["mode"]: m for m in report["modes"]}
        assert by_mode["hybrid"]["accuracy"]["point"] > by_mode["llm_only"]["accuracy"]["point"]
        # Brier: lower is better; perfect should be < coinflip.
        assert by_mode["hybrid"]["brier"]["point"] < by_mode["llm_only"]["brier"]["point"]

    def test_alignment_failure_returns_nonzero(
        self, tmp_path, gold_cases, perfect_predictions_path
    ):
        # Drop a line so length mismatches.
        truncated = tmp_path / "bad.jsonl"
        with perfect_predictions_path.open() as src, truncated.open("w") as dst:
            lines = src.readlines()
            dst.writelines(lines[:-1])

        out_path = tmp_path / "report.json"
        rc = _cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={truncated}",
                "--out",
                str(out_path),
                "--no-bootstrap",
            ]
        )
        assert rc != 0

    def test_missing_predictions_file_returns_nonzero(self, tmp_path):
        out_path = tmp_path / "report.json"
        rc = _cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={tmp_path / 'does_not_exist.jsonl'}",
                "--out",
                str(out_path),
                "--no-bootstrap",
            ]
        )
        assert rc != 0

    def test_seed_recorded_in_output(
        self, tmp_path, perfect_predictions_path
    ):
        out_path = tmp_path / "seeded.json"
        rc = _cli_main(
            [
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={perfect_predictions_path}",
                "--out",
                str(out_path),
                "--seed",
                "7",
                "--n-resamples",
                "100",
            ]
        )
        assert rc == 0
        report = json.loads(out_path.read_text())
        assert report["seed"] == 7
        assert report["n_resamples"] == 100


# ---------- Subprocess (real entry point) ----------


class TestSubprocessEntry:
    def test_invoking_eval_ablate_module_writes_report(
        self, tmp_path, perfect_predictions_path
    ):
        out_path = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "eval.ablate",
                "--gold",
                str(GOLD_PATH),
                "--predictions",
                f"hybrid={perfect_predictions_path}",
                "--out",
                str(out_path),
                "--no-bootstrap",
            ],
            cwd=str(Path(__file__).resolve().parents[3]),  # repo root
            env={
                **__import__("os").environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert out_path.exists()
        report = json.loads(out_path.read_text())
        assert report["modes"][0]["mode"] == "hybrid"
