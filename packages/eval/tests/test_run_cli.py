"""Tests for packages/eval/run.py CLI orchestrator."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[3]
_VENV_PY = sys.executable
_FIXTURES = Path(__file__).parent / "fixtures"


def _run(*args, cwd=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_ROOT / "packages")
    return subprocess.run(
        [_VENV_PY, "-m", "eval.run", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def synthetic_corpus(tmp_path):
    """Copy the synthetic 10-case fixture + predictions into tmp_path."""
    gold_dst = tmp_path / "synthetic_corpus_10.jsonl"
    pred_dst = tmp_path / "predictions.jsonl"
    shutil.copy(_FIXTURES / "synthetic_corpus_10.jsonl", gold_dst)
    shutil.copy(
        _FIXTURES / "predictions_for_synthetic_corpus_10.jsonl", pred_dst
    )
    return gold_dst, pred_dst


class TestRunCli:
    def test_accuracy_against_synthetic_corpus(self, synthetic_corpus):
        gold, preds = synthetic_corpus
        proc = _run("--metric", "accuracy", "--gold", str(gold), "--predictions", str(preds))
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["metric"] == "issue_winner_accuracy"
        assert 0.0 <= report["point"] <= 1.0
        assert report["lower_95"] <= report["point"] <= report["upper_95"]
        assert report["n"] == 10
        assert report["n_resamples"] == 1000

    def test_brier_against_synthetic_corpus(self, synthetic_corpus):
        gold, preds = synthetic_corpus
        proc = _run("--metric", "brier", "--gold", str(gold), "--predictions", str(preds))
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["metric"] == "brier_score"
        # Predictions are calibrated near actual; expect Brier well below 0.25
        assert 0.0 <= report["point"] <= 0.25

    def test_ece_against_synthetic_corpus(self, synthetic_corpus):
        gold, preds = synthetic_corpus
        proc = _run("--metric", "ece", "--gold", str(gold), "--predictions", str(preds))
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["metric"] == "expected_calibration_error"
        assert 0.0 <= report["point"] <= 1.0

    def test_no_bootstrap_collapses_ci(self, synthetic_corpus):
        gold, preds = synthetic_corpus
        proc = _run(
            "--metric", "accuracy",
            "--gold", str(gold),
            "--predictions", str(preds),
            "--no-bootstrap",
        )
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["lower_95"] == report["point"] == report["upper_95"]
        assert report["n_resamples"] == 0

    def test_out_writes_file(self, synthetic_corpus, tmp_path):
        gold, preds = synthetic_corpus
        out = tmp_path / "results" / "accuracy.json"
        proc = _run(
            "--metric", "accuracy",
            "--gold", str(gold),
            "--predictions", str(preds),
            "--out", str(out),
        )
        assert proc.returncode == 0, proc.stderr
        assert out.exists()
        report = json.loads(out.read_text())
        assert report["metric"] == "issue_winner_accuracy"
        assert proc.stdout == ""  # nothing on stdout when --out given

    def test_unknown_metric_exits_two(self, synthetic_corpus):
        gold, preds = synthetic_corpus
        proc = _run(
            "--metric", "no_such_metric",
            "--gold", str(gold),
            "--predictions", str(preds),
        )
        # argparse exits 2 on bad choices
        assert proc.returncode == 2

    def test_alignment_mismatch_exits_one(self, tmp_path):
        # gold has case_id A; predictions has case_id B
        gold_path = tmp_path / "gold.jsonl"
        write_jsonl(gold_path, [gold_case_dict(case_id="A")])
        pred_path = tmp_path / "preds.jsonl"
        pred_path.write_text(json.dumps({
            "case_id": "B",
            "overall_winner": "tenant",
            "overall_win_probability": 0.5,
            "total_predicted_gbp": "100.00",
            "per_issue": [],
        }) + "\n")
        proc = _run("--metric", "accuracy", "--gold", str(gold_path), "--predictions", str(pred_path))
        assert proc.returncode == 1
        assert "case_id mismatch" in proc.stderr or "length mismatch" in proc.stderr

    def test_invalid_gold_row_exits_one_instead_of_silent_drop(self, tmp_path):
        gold_path = tmp_path / "gold.jsonl"
        gold_path.write_text(
            json.dumps(gold_case_dict(case_id="A")) + "\n"
            + json.dumps(gold_case_dict(case_id="BROKEN", decision_date="2018-01-01")) + "\n"
        )
        pred_path = tmp_path / "preds.jsonl"
        pred_path.write_text(json.dumps({
            "case_id": "A",
            "overall_winner": "tenant",
            "overall_win_probability": 0.5,
            "total_predicted_gbp": "100.00",
            "per_issue": [],
        }) + "\n")
        proc = _run("--metric", "accuracy", "--gold", str(gold_path), "--predictions", str(pred_path))
        assert proc.returncode == 1
        assert "Gold set load error" in proc.stderr

    def test_invalid_prediction_probability_exits_one(self, tmp_path):
        gold_path = tmp_path / "gold.jsonl"
        write_jsonl(gold_path, [gold_case_dict(case_id="A")])
        pred_path = tmp_path / "preds.jsonl"
        pred_path.write_text(json.dumps({
            "case_id": "A",
            "overall_winner": "tenant",
            "overall_win_probability": 2.0,
            "total_predicted_gbp": "100.00",
            "per_issue": [
                {
                    "issue": "carpet_cleaning",
                    "predicted_winner": "tenant",
                    "win_probability": 2.0,
                    "predicted_amount_gbp": "100.00",
                }
            ],
        }) + "\n")
        proc = _run("--metric", "brier", "--gold", str(gold_path), "--predictions", str(pred_path))
        assert proc.returncode == 1
        assert "Predictions load error" in proc.stderr

    def test_deterministic_seed(self, synthetic_corpus):
        gold, preds = synthetic_corpus
        a = _run("--metric", "accuracy", "--gold", str(gold), "--predictions", str(preds), "--seed", "7")
        b = _run("--metric", "accuracy", "--gold", str(gold), "--predictions", str(preds), "--seed", "7")
        rep_a = json.loads(a.stdout)
        rep_b = json.loads(b.stdout)
        assert rep_a["point"] == rep_b["point"]
        assert rep_a["lower_95"] == rep_b["lower_95"]
        assert rep_a["upper_95"] == rep_b["upper_95"]


class TestRunCliInProcess:
    """In-process for coverage credit."""

    def test_cli_main_accuracy(self, synthetic_corpus, capsys):
        from eval.run import _cli_main
        gold, preds = synthetic_corpus
        rc = _cli_main([
            "--metric", "accuracy",
            "--gold", str(gold),
            "--predictions", str(preds),
            "--no-bootstrap",
        ])
        captured = capsys.readouterr()
        assert rc == 0
        report = json.loads(captured.out)
        assert report["metric"] == "issue_winner_accuracy"
        assert report["n_resamples"] == 0

    def test_load_predictions_handles_blank_lines(self, tmp_path):
        from eval.run import _load_predictions
        path = tmp_path / "p.jsonl"
        path.write_text(
            "\n"
            + json.dumps({
                "case_id": "X",
                "overall_winner": "tenant",
                "overall_win_probability": 0.5,
                "total_predicted_gbp": "100.00",
                "per_issue": [],
            }) + "\n"
            + "\n"
        )
        preds = _load_predictions(path)
        assert len(preds) == 1
        assert preds[0].case_id == "X"

    def test_load_predictions_missing_file(self, tmp_path):
        from eval.run import _load_predictions
        with pytest.raises(FileNotFoundError):
            _load_predictions(tmp_path / "ghost.jsonl")

    def test_load_predictions_bad_line_includes_line_number(self, tmp_path):
        from eval.run import _load_predictions
        path = tmp_path / "p.jsonl"
        path.write_text(
            json.dumps({
                "case_id": "X",
                "overall_winner": "tenant",
                "overall_win_probability": 0.5,
                "total_predicted_gbp": "100.00",
                "per_issue": [],
            }) + "\n"
            + json.dumps({"missing": "fields"}) + "\n"
        )
        with pytest.raises(ValueError, match="line 2"):
            _load_predictions(path)
