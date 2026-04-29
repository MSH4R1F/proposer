"""Tests for the gold-set dataset loader and audit (packages/eval/dataset.py)."""
from __future__ import annotations

import json
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
