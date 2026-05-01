"""Tests for the gold-set dataset loader and audit (packages/eval/dataset.py)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore[import-not-found]


class TestPublicSurface:
    def test_module_constants(self):
        from eval.dataset import STRATIFICATION_FLOOR, TEST_START, TRAIN_CUTOFF
        assert TRAIN_CUTOFF == date(2022, 12, 31)
        assert TEST_START == date(2023, 1, 1)
        assert STRATIFICATION_FLOOR == 5

    def test_module_exports(self):
        from eval.dataset import (  # noqa: F401
            AuditReport,
            LeakageViolation,
            LoadError,
            LoadResult,
            audit,
            load,
            test as _test_fn,
            train,
        )

    def test_load_result_is_clean_when_no_errors(self):
        from eval.dataset import LoadResult
        r = LoadResult(cases=[], errors=[], source_path=Path("/tmp/x.jsonl"))
        assert r.is_clean

    def test_audit_report_is_clean_when_empty(self):
        from eval.dataset import AuditReport
        r = AuditReport(n_cases=0, train_count=0, test_count=0)
        assert r.is_clean


class TestLoad:
    def test_load_clean_corpus(self, tmp_path):
        from eval.dataset import load
        path = tmp_path / "data" / "gold_standard" / "housing_v1.jsonl"
        write_jsonl(path, [
            gold_case_dict(case_id="A-2020", decision_date="2020-05-01"),
            gold_case_dict(case_id="B-2023", decision_date="2023-08-15"),
        ])
        result = load("housing_v1", base_dir=tmp_path / "data" / "gold_standard")
        assert result.is_clean
        assert len(result.cases) == 2
        assert {c.case_id for c in result.cases} == {"A-2020", "B-2023"}
        assert result.errors == []
        assert result.source_path == path

    def test_load_default_base_dir_is_cwd_data_gold_standard(self, tmp_path, monkeypatch):
        from eval.dataset import load
        (tmp_path / "data" / "gold_standard").mkdir(parents=True)
        write_jsonl(
            tmp_path / "data" / "gold_standard" / "housing_v1.jsonl",
            [gold_case_dict()],
        )
        monkeypatch.chdir(tmp_path)
        result = load("housing_v1")
        assert len(result.cases) == 1

    def test_load_missing_file_raises(self, tmp_path):
        from eval.dataset import load
        with pytest.raises(FileNotFoundError):
            load("housing_v1", base_dir=tmp_path)

    def test_load_lenient_skips_malformed_json(self, tmp_path):
        from eval.dataset import load
        path = tmp_path / "housing_v1.jsonl"
        path.write_text(
            json.dumps(gold_case_dict(case_id="OK")) + "\n"
            + "{not json\n"
            + json.dumps(gold_case_dict(case_id="OK2")) + "\n"
        )
        result = load("housing_v1", base_dir=tmp_path)
        assert [c.case_id for c in result.cases] == ["OK", "OK2"]
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err.line_number == 2
        assert "{not json" in err.raw_line

    def test_load_lenient_skips_validation_errors(self, tmp_path):
        from eval.dataset import load
        path = tmp_path / "housing_v1.jsonl"
        bad_case = gold_case_dict(case_id="BAD", decision_date="2018-12-31")  # outside window
        path.write_text(
            json.dumps(gold_case_dict(case_id="OK")) + "\n"
            + json.dumps(bad_case) + "\n"
        )
        result = load("housing_v1", base_dir=tmp_path)
        assert [c.case_id for c in result.cases] == ["OK"]
        assert len(result.errors) == 1
        assert result.errors[0].line_number == 2
        assert "decision_date" in result.errors[0].error

    def test_load_strict_raises_on_first_error(self, tmp_path):
        from eval.dataset import load
        from pydantic import ValidationError
        path = tmp_path / "housing_v1.jsonl"
        bad_case = gold_case_dict(decision_date="2018-12-31")
        path.write_text(
            json.dumps(gold_case_dict(case_id="OK")) + "\n"
            + json.dumps(bad_case) + "\n"
        )
        with pytest.raises((ValidationError, ValueError)):
            load("housing_v1", base_dir=tmp_path, strict=True)

    def test_load_strict_raises_on_malformed_json(self, tmp_path):
        from eval.dataset import load
        path = tmp_path / "housing_v1.jsonl"
        path.write_text("{not json\n")
        with pytest.raises(json.JSONDecodeError):
            load("housing_v1", base_dir=tmp_path, strict=True)

    def test_load_skips_blank_lines(self, tmp_path):
        from eval.dataset import load
        path = tmp_path / "housing_v1.jsonl"
        path.write_text(
            "\n"
            + json.dumps(gold_case_dict(case_id="OK")) + "\n"
            + "\n"
            + "   \n"
        )
        result = load("housing_v1", base_dir=tmp_path)
        assert len(result.cases) == 1
        assert result.errors == []


class TestSplits:
    def _build(self, dicts):
        from eval.schema import GoldCase
        return [GoldCase.model_validate(d) for d in dicts]

    def test_train_filters_by_cutoff(self):
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(case_id="X-2020", decision_date="2020-05-01"),
            gold_case_dict(case_id="X-2022-edge", decision_date="2022-12-31"),
            gold_case_dict(case_id="X-2023-edge", decision_date="2023-01-01"),
            gold_case_dict(case_id="X-2024", decision_date="2024-06-15"),
        ])
        result = train(cases)
        assert {c.case_id for c in result} == {"X-2020", "X-2022-edge"}

    def test_test_split_filters_by_start(self):
        from eval.dataset import test as test_split
        cases = self._build([
            gold_case_dict(case_id="X-2022", decision_date="2022-12-31"),
            gold_case_dict(case_id="X-2023", decision_date="2023-01-01"),
            gold_case_dict(case_id="X-2024", decision_date="2024-06-15"),
        ])
        result = test_split(cases)
        assert {c.case_id for c in result} == {"X-2023", "X-2024"}

    def test_train_lenient_returns_cases_despite_leakage(self, caplog):
        import logging
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(
                case_id="LEAK",
                decision_date="2021-04-01",
                cited_authorities=[
                    {"name": "Future v Past", "cited_date": "2024-03-01"}
                ],
            ),
            gold_case_dict(case_id="OK", decision_date="2020-05-01"),
        ])
        with caplog.at_level(logging.WARNING, logger="eval.dataset"):
            result = train(cases)
        assert {c.case_id for c in result} == {"LEAK", "OK"}
        assert any("LEAK" in record.message for record in caplog.records)

    def test_train_strict_raises_on_leakage(self):
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(
                case_id="LEAK",
                decision_date="2021-04-01",
                cited_authorities=[
                    {"name": "Future v Past", "cited_date": "2024-03-01"}
                ],
            ),
        ])
        with pytest.raises(ValueError, match="LEAK"):
            train(cases, strict=True)

    def test_train_strict_clean_corpus_returns_cases(self):
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(case_id="OK", decision_date="2020-05-01"),
        ])
        result = train(cases, strict=True)
        assert len(result) == 1

    def test_train_authority_dated_exactly_at_cutoff_is_ok(self):
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(
                case_id="EDGE",
                decision_date="2020-05-01",
                cited_authorities=[
                    {"name": "Edge v Case", "cited_date": "2022-12-31"}
                ],
            ),
        ])
        result = train(cases, strict=True)
        assert len(result) == 1

    def test_train_ignores_test_case_authority_dates(self):
        # A test case (2024) citing a 2024 authority is NOT leakage —
        # leakage only applies to train cases.
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(
                case_id="TEST-OK",
                decision_date="2024-03-01",
                cited_authorities=[
                    {"name": "2024 Auth", "cited_date": "2024-01-01"}
                ],
            ),
        ])
        # train() returns only train cases (none here); no exception expected
        result = train(cases, strict=True)
        assert result == []


class TestAudit:
    def _build(self, dicts):
        from eval.schema import GoldCase
        return [GoldCase.model_validate(d) for d in dicts]

    def test_audit_counts(self):
        from eval.dataset import audit
        cases = self._build([
            gold_case_dict(case_id="A", decision_date="2020-05-01"),
            gold_case_dict(case_id="B", decision_date="2022-12-31"),
            gold_case_dict(case_id="C", decision_date="2023-01-01"),
        ])
        report = audit(cases)
        assert report.n_cases == 3
        assert report.train_count == 2
        assert report.test_count == 1

    def test_audit_no_leakage_on_clean_corpus(self):
        from eval.dataset import audit
        cases = self._build([
            gold_case_dict(
                case_id="A",
                decision_date="2020-05-01",
                cited_authorities=[
                    {"name": "Howard v Aggio", "cited_date": "2008-06-25"},
                ],
            ),
        ])
        assert audit(cases).leakage_violations == []

    def test_audit_reports_leakage(self):
        from eval.dataset import audit
        cases = self._build([
            gold_case_dict(
                case_id="LEAK",
                decision_date="2021-04-01",
                cited_authorities=[
                    {"name": "Future v Past", "cited_date": "2024-03-01"},
                ],
            ),
        ])
        report = audit(cases)
        assert len(report.leakage_violations) == 1
        v = report.leakage_violations[0]
        assert v.case_id == "LEAK"
        assert v.authority_name == "Future v Past"

    def test_audit_understratified_types(self):
        # 4 cleaning cases; floor is 5 -> cleaning is under-stratified
        from eval.dataset import audit
        from eval.schema import ClaimType
        cases = self._build([
            gold_case_dict(case_id=f"C{i}", claim_types=["cleaning"])
            for i in range(4)
        ])
        report = audit(cases)
        assert ClaimType.CLEANING in report.understratified_types
        assert report.understratified_types[ClaimType.CLEANING] == 4
        # Other types absent => count 0 => below floor => present too
        assert ClaimType.DAMAGES in report.understratified_types
        assert report.understratified_types[ClaimType.DAMAGES] == 0

    def test_audit_multi_type_case_counts_toward_each(self):
        # 5 cases each tagged [cleaning, damages] -> both at 5; under floor for the rest
        from eval.dataset import audit
        from eval.schema import ClaimType
        cases = self._build([
            gold_case_dict(case_id=f"M{i}", claim_types=["cleaning", "damages"])
            for i in range(5)
        ])
        report = audit(cases)
        assert ClaimType.CLEANING not in report.understratified_types
        assert ClaimType.DAMAGES not in report.understratified_types
        assert ClaimType.DISREPAIR in report.understratified_types

    def test_audit_distributions(self):
        from eval.dataset import audit
        from eval.schema import CaseSize, RegionUK
        cases = self._build([
            gold_case_dict(case_id="L1", region="london", region_source="London"),
            gold_case_dict(case_id="L2", region="london", region_source="London"),
            gold_case_dict(case_id="W1", region="wales", region_source="Wales"),
        ])
        report = audit(cases)
        assert report.region_distribution == {RegionUK.LONDON: 2, RegionUK.WALES: 1}
        assert report.case_size_distribution[CaseSize.SMALL] == 3

    def test_audit_is_clean_when_all_types_at_floor(self):
        from eval.dataset import audit
        from eval.schema import ClaimType
        cases = self._build([
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType
            for i in range(5)
        ])
        report = audit(cases)
        # Every type has exactly 5; STRATIFICATION_FLOOR is inclusive.
        assert report.is_clean is True

    def test_audit_empty_corpus(self):
        from eval.dataset import audit
        from eval.schema import ClaimType
        report = audit([])
        assert report.n_cases == 0
        assert report.train_count == 0
        assert report.test_count == 0
        # Every claim type is "0 cases" — all five are under-stratified.
        assert set(report.understratified_types) == set(ClaimType)
        assert report.is_clean is False


class TestSyntheticCorpus10:
    """The 10-case fixture is the seed corpus every metric module
    develops against. Loading must be clean."""

    def test_loads_without_errors(self):
        from eval.dataset import load
        result = load(
            "synthetic_corpus_10",
            base_dir=Path(__file__).parent / "fixtures",
        )
        assert result.is_clean
        assert len(result.cases) == 10

    def test_every_claim_type_represented(self):
        from eval.dataset import load
        from eval.schema import ClaimType
        result = load(
            "synthetic_corpus_10",
            base_dir=Path(__file__).parent / "fixtures",
        )
        types_seen = set()
        for c in result.cases:
            types_seen.update(c.claim_types)
        assert types_seen == set(ClaimType)

    def test_train_test_split_is_meaningful(self):
        from eval.dataset import load, train, test as test_split
        result = load(
            "synthetic_corpus_10",
            base_dir=Path(__file__).parent / "fixtures",
        )
        assert len(train(result.cases)) >= 4
        assert len(test_split(result.cases)) >= 3


class TestCli:
    """End-to-end CLI tests via subprocess. Exercises the real entry point
    (`python -m eval.dataset audit ...`) rather than mocking argparse."""

    REPO_ROOT = Path(__file__).resolve().parents[3]
    VENV_PY = sys.executable

    @classmethod
    def _run(cls, *args, cwd=None):
        import os
        import subprocess
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cls.REPO_ROOT / "packages")
        return subprocess.run(
            [cls.VENV_PY, "-m", "eval.dataset", *args],
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
        )

    def _write_corpus(self, path: Path, cases: list):
        from eval.tests.conftest import write_jsonl  # type: ignore
        write_jsonl(path, cases)

    def test_cli_audit_clean_corpus_exit_zero(self, tmp_path):
        from eval.schema import ClaimType
        path = tmp_path / "housing_v1.jsonl"
        cases = [
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType
            for i in range(5)
        ]
        self._write_corpus(path, cases)
        proc = self._run("audit", str(path))
        assert proc.returncode == 0, proc.stderr
        assert "n_cases: 25" in proc.stdout
        assert "is_clean: True" in proc.stdout

    def test_cli_audit_dirty_lenient_exit_zero(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        self._write_corpus(path, [gold_case_dict()])
        proc = self._run("audit", str(path))
        # Default mode reports but does not fail
        assert proc.returncode == 0
        assert "understratified" in proc.stdout.lower()
        assert "is_clean: False" in proc.stdout

    def test_cli_audit_dirty_strict_exit_one(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        self._write_corpus(path, [gold_case_dict()])
        proc = self._run("audit", str(path), "--strict")
        assert proc.returncode == 1

    def test_cli_audit_clean_strict_exit_zero(self, tmp_path):
        from eval.schema import ClaimType
        path = tmp_path / "housing_v1.jsonl"
        cases = [
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType
            for i in range(5)
        ]
        self._write_corpus(path, cases)
        proc = self._run("audit", str(path), "--strict")
        assert proc.returncode == 0, proc.stderr

    def test_cli_audit_strict_fails_on_load_errors(self, tmp_path):
        from eval.schema import ClaimType
        path = tmp_path / "housing_v1.jsonl"
        cases = [
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType
            for i in range(5)
        ]
        self._write_corpus(path, cases)
        with path.open("a") as f:
            f.write(json.dumps(gold_case_dict(case_id="BROKEN", decision_date="2018-01-01")))
            f.write("\n")
        proc = self._run("audit", str(path), "--strict")
        assert proc.returncode == 1
        assert "Load error" in proc.stderr

    def test_cli_audit_json_output(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        self._write_corpus(path, [gold_case_dict()])
        out_json = tmp_path / "audit.json"
        proc = self._run("audit", str(path), "--json", str(out_json))
        assert proc.returncode == 0
        assert out_json.exists()
        payload = json.loads(out_json.read_text())
        assert payload["n_cases"] == 1
        assert payload["is_clean"] is False

    def test_cli_audit_evidence_flag(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        self._write_corpus(path, [gold_case_dict()])
        proc = self._run("audit", str(path), "--evidence", cwd=tmp_path)
        assert proc.returncode == 0
        evidence_dir = tmp_path / ".sisyphus" / "evidence" / "eval"
        assert evidence_dir.exists()
        files = list(evidence_dir.glob("audit_*.json"))
        assert len(files) == 1, f"expected exactly one audit_<date>.json file, got {files}"


class TestCliInProcess:
    """In-process unit tests for the CLI internals — covers _format_report,
    _report_to_dict, and _cli_main without paying the subprocess cost.
    Pairs with TestCli (subprocess-based) for full coverage."""

    def _build(self, dicts):
        from eval.schema import GoldCase
        return [GoldCase.model_validate(d) for d in dicts]

    def test_format_report_clean(self):
        from eval.dataset import _format_report, audit
        from eval.schema import ClaimType
        cases = self._build([
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType for i in range(5)
        ])
        report = audit(cases)
        text = _format_report(report)
        assert "n_cases: 25" in text
        assert "stratification: all types at or above floor" in text
        assert "leakage violations: none" in text
        assert "is_clean: True" in text

    def test_format_report_with_leakage(self):
        from eval.dataset import _format_report, audit
        cases = self._build([
            gold_case_dict(
                case_id="LEAK",
                decision_date="2021-04-01",
                cited_authorities=[
                    {"name": "Future v Past", "cited_date": "2024-03-01"}
                ],
            ),
        ])
        text = _format_report(audit(cases))
        assert "leakage violations (1)" in text
        assert "LEAK" in text
        assert "Future v Past" in text

    def test_report_to_dict_round_trips_through_json(self):
        from eval.dataset import _report_to_dict, audit
        cases = self._build([
            gold_case_dict(
                case_id="LEAK",
                decision_date="2021-04-01",
                cited_authorities=[
                    {"name": "Future v Past", "cited_date": "2024-03-01"}
                ],
            ),
        ])
        d = _report_to_dict(audit(cases))
        # All values must be JSON-serialisable
        s = json.dumps(d)
        again = json.loads(s)
        assert again["n_cases"] == 1
        assert again["leakage_violations"][0]["case_id"] == "LEAK"
        assert again["leakage_violations"][0]["authority_cited_date"] == "2024-03-01"
        assert again["case_size_distribution"]["small"] == 1

    def test_cli_main_audit_clean_returns_zero(self, tmp_path):
        from eval.dataset import _cli_main
        path = tmp_path / "housing_v1.jsonl"
        from eval.schema import ClaimType
        write_jsonl(path, [
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType for i in range(5)
        ])
        rc = _cli_main(["audit", str(path)])
        assert rc == 0

    def test_cli_main_audit_strict_dirty_returns_one(self, tmp_path):
        from eval.dataset import _cli_main
        path = tmp_path / "housing_v1.jsonl"
        write_jsonl(path, [gold_case_dict()])
        rc = _cli_main(["audit", str(path), "--strict"])
        assert rc == 1

    def test_cli_main_audit_writes_json_and_evidence(self, tmp_path, monkeypatch):
        from eval.dataset import _cli_main
        path = tmp_path / "housing_v1.jsonl"
        write_jsonl(path, [gold_case_dict()])
        out_json = tmp_path / "audit.json"
        monkeypatch.chdir(tmp_path)
        rc = _cli_main(["audit", str(path), "--json", str(out_json), "--evidence"])
        assert rc == 0
        assert out_json.exists()
        evidence_files = list((tmp_path / ".sisyphus" / "evidence" / "eval").glob("audit_*.json"))
        assert len(evidence_files) == 1

    def test_cli_main_audit_surfaces_load_errors_on_stderr(self, tmp_path, capsys):
        from eval.dataset import _cli_main
        path = tmp_path / "housing_v1.jsonl"
        path.write_text(
            json.dumps(gold_case_dict(case_id="OK")) + "\n"
            + "{not json\n"
        )
        rc = _cli_main(["audit", str(path)])
        captured = capsys.readouterr()
        assert "Load errors (1)" in captured.err
        assert rc == 0  # lenient default doesn't fail on parse errors
