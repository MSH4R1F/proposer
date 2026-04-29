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
