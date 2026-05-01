"""Tests for scripts/eval/annotate.py (subprocess-based + in-process).

Subprocess tests exercise the real entry point. In-process tests cover
internals (`_template`, `_cli_main(argv=...)`) for coverage credit without
paying the subprocess cost on every assertion.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[3]
_VENV_PY = sys.executable
_SCRIPT = _REPO_ROOT / "scripts" / "eval" / "annotate.py"


def _run(*args, cwd=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_REPO_ROOT / 'packages'}:{_REPO_ROOT}"
    return subprocess.run(
        [_VENV_PY, str(_SCRIPT), *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )


class TestTemplate:
    def test_template_emits_valid_json(self):
        proc = _run("template")
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["schema_version"] == "v1"
        assert "case_id" in data and "decision_date" in data
        assert "claim_types" in data and isinstance(data["claim_types"], list)

    def test_template_is_intentionally_invalid(self):
        # The template carries REPLACE_ME placeholders and a 0-amount on the
        # outcome path; running it through GoldCase should fail. Confirms the
        # template's role is to scaffold structure, not produce a valid case.
        proc = _run("template")
        from eval.schema import GoldCase
        with pytest.raises(Exception):
            GoldCase.model_validate(json.loads(proc.stdout))


class TestValidate:
    def test_validate_passes_on_minimal_fixture(self):
        proc = _run(
            "validate",
            str(_REPO_ROOT / "packages" / "eval" / "tests" / "fixtures" / "gold_case_minimal.json"),
        )
        assert proc.returncode == 0, proc.stderr
        assert "valid" in proc.stdout.lower()

    def test_validate_fails_with_helpful_message(self, tmp_path):
        bad = tmp_path / "bad.json"
        case = gold_case_dict(decision_date="2018-12-31")
        bad.write_text(json.dumps(case))
        proc = _run("validate", str(bad))
        assert proc.returncode == 1
        assert "decision_date" in proc.stderr


class TestAppend:
    def test_append_adds_to_corpus(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        existing = gold_dir / "housing_v1.jsonl"
        existing.write_text(json.dumps(gold_case_dict(case_id="A")) + "\n")
        draft = tmp_path / "B.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="B")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        from eval.dataset import load
        cases = load("housing_v1", base_dir=gold_dir).cases
        assert {c.case_id for c in cases} == {"A", "B"}

    def test_append_rejects_duplicate_case_id(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        existing = gold_dir / "housing_v1.jsonl"
        existing.write_text(json.dumps(gold_case_dict(case_id="DUP")) + "\n")
        draft = tmp_path / "dup.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="DUP")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1
        assert "DUP" in proc.stderr

    def test_append_refuses_invalid_existing_corpus(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        existing = gold_dir / "housing_v1.jsonl"
        existing.write_text("{not json\n")
        draft = tmp_path / "case.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="SAFE")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1
        assert "existing corpus" in proc.stderr

    def test_append_creates_corpus_if_absent(self, tmp_path):
        (tmp_path / "data" / "gold_standard").mkdir(parents=True)
        draft = tmp_path / "first.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="FIRST")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        from eval.dataset import load
        cases = load("housing_v1", base_dir=tmp_path / "data" / "gold_standard").cases
        assert [c.case_id for c in cases] == ["FIRST"]

    def test_append_refuses_invalid_draft(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        bad = tmp_path / "bad.json"
        case = gold_case_dict(decision_date="2018-01-01")
        bad.write_text(json.dumps(case))
        proc = _run("append", str(bad), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1


class TestListAndShow:
    def test_list_prints_case_summaries(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        write_jsonl(gold_dir / "housing_v1.jsonl", [
            gold_case_dict(case_id="A", decision_date="2020-05-01"),
            gold_case_dict(case_id="B", decision_date="2023-07-15"),
        ])
        proc = _run("list", "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert "A" in proc.stdout and "B" in proc.stdout
        assert "2020-05-01" in proc.stdout

    def test_show_pretty_prints_one_case(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        write_jsonl(gold_dir / "housing_v1.jsonl", [gold_case_dict(case_id="X")])
        proc = _run("show", "X", "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["case_id"] == "X"

    def test_show_unknown_case_id_exits_one(self, tmp_path):
        gold_dir = tmp_path / "data" / "gold_standard"
        write_jsonl(gold_dir / "housing_v1.jsonl", [gold_case_dict(case_id="X")])
        proc = _run("show", "MISSING", "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1


class TestInProcessForCoverage:
    """In-process unit tests so coverage tracker sees the CLI internals."""

    def test_template_function_returns_dict(self):
        # Import requires path bootstrap; do it manually here.
        import sys
        scripts_dir = str(_REPO_ROOT)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from scripts.eval.annotate import _template
        d = _template()
        assert d["schema_version"] == "v1"
        assert "REPLACE_ME" in d["case_id"]

    def test_cli_main_template_returns_zero(self, capsys):
        import sys
        scripts_dir = str(_REPO_ROOT)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from scripts.eval.annotate import _cli_main
        rc = _cli_main(["template"])
        captured = capsys.readouterr()
        assert rc == 0
        # Output is valid JSON
        json.loads(captured.out)

    def test_cli_main_validate_invalid_returns_one(self, tmp_path, capsys):
        import sys
        scripts_dir = str(_REPO_ROOT)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from scripts.eval.annotate import _cli_main
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(gold_case_dict(decision_date="2018-01-01")))
        rc = _cli_main(["validate", str(bad)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "decision_date" in captured.err

    def test_cli_main_validate_valid_returns_zero(self, tmp_path, capsys):
        import sys
        scripts_dir = str(_REPO_ROOT)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from scripts.eval.annotate import _cli_main
        good = tmp_path / "good.json"
        good.write_text(json.dumps(gold_case_dict()))
        rc = _cli_main(["validate", str(good)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "valid" in captured.out.lower()

    def test_cli_main_append_then_list_then_show(self, tmp_path, capsys, monkeypatch):
        import sys
        scripts_dir = str(_REPO_ROOT)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from scripts.eval.annotate import _cli_main
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        draft = tmp_path / "case.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="X")))
        monkeypatch.chdir(tmp_path)

        # append
        rc = _cli_main(["append", str(draft), "--corpus", "housing_v1"])
        assert rc == 0
        # list
        rc = _cli_main(["list", "--corpus", "housing_v1"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "X" in captured.out
        # show found
        rc = _cli_main(["show", "X", "--corpus", "housing_v1"])
        captured = capsys.readouterr()
        assert rc == 0
        # show missing
        rc = _cli_main(["show", "MISSING", "--corpus", "housing_v1"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "MISSING" in captured.err
