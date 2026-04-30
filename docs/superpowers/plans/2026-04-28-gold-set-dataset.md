# Phase 2 — Dataset Loader & Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `packages/eval/dataset.py` so every Phase 4 metric and the Phase 5 ablation runner can read the gold set, filter to train/test, and run a leakage + stratification audit.

**Architecture:** Pure functions over `list[GoldCase]`, plus a thin CLI for CI. Lenient defaults (skip-and-log) for pilot iteration; `strict=True` opt-in for production CI gates. No I/O outside `load()` and the CLI — `train()`, `test()`, `audit()` are pure.

**Tech stack:** Python 3.9.6, Pydantic 2.12.5, pytest 8.4.2, dataclasses (stdlib), argparse (stdlib). No new dependencies.

**Out of scope for Phase 2:** annotation CLI (Phase 3), metric implementations (Phase 4), ablation runner (Phase 5). The annotation CLI will write to `data/gold_standard/housing_v1.jsonl`; this loader will read it.

---

## File structure

| File | Responsibility |
|---|---|
| `packages/eval/dataset.py` | `load()`, `train()`, `test()`, `audit()`, plus dataclasses `LoadResult`, `LoadError`, `AuditReport`, `LeakageViolation` |
| `packages/eval/__main__.py` | Module entry-point: `python -m eval.dataset audit ...` (delegates to `dataset.cli`) — actually we'll embed CLI in `dataset.py` itself, invoked via `python -m eval.dataset` (see Task 6) |
| `packages/eval/tests/test_dataset.py` | All loader/audit tests |
| `packages/eval/tests/conftest.py` | Add `gold_case_dict()` factory + `write_jsonl()` helper |
| `docs/eval/dataset.md` | Brief usage doc — how to call `load`, when to use `strict`, what the audit reports mean |

`packages/eval/__init__.py` re-exports the new public surface.

No production data files are created — `data/gold_standard/housing_v1.jsonl` stays empty until Phase 3 annotates real cases.

---

## API design (locked before coding)

```python
# packages/eval/dataset.py

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from eval.schema import GoldCase, ClaimType, CaseSize


# Cutoff dates per the PILOT methodology (interim report)
TRAIN_CUTOFF = date(2022, 12, 31)
TEST_START   = date(2023, 1, 1)
STRATIFICATION_FLOOR = 5


@dataclass
class LoadError:
    line_number: int           # 1-indexed
    raw_line: str              # the offending JSONL line, untouched
    error: str                 # human-readable error message


@dataclass
class LoadResult:
    cases: list[GoldCase]      # successfully parsed cases
    errors: list[LoadError]    # always populated — empty list on a clean load
    source_path: Path          # the file we read

    @property
    def is_clean(self) -> bool:
        return not self.errors


@dataclass
class LeakageViolation:
    case_id: str
    authority_name: str
    authority_cited_date: date
    cutoff: date


@dataclass
class AuditReport:
    n_cases: int
    train_count: int
    test_count: int
    leakage_violations: list[LeakageViolation] = field(default_factory=list)
    understratified_types: dict[ClaimType, int] = field(default_factory=dict)  # type -> current count, only types below floor
    region_distribution: dict[str, int] = field(default_factory=dict)
    case_size_distribution: dict[CaseSize, int] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.leakage_violations and not self.understratified_types


def load(
    version: str = "housing_v1",
    *,
    base_dir: Optional[Path] = None,
    strict: bool = False,
) -> LoadResult:
    """Read data/gold_standard/<version>.jsonl. Validate each line.

    strict=False (default): collect errors, return valid cases + errors list
    strict=True: raise the first ValidationError or json.JSONDecodeError
    """
    ...


def train(cases: list[GoldCase], *, strict: bool = False) -> list[GoldCase]:
    """Return cases with decision_date <= TRAIN_CUTOFF. Run a leakage check
    (every cited_authorities[].cited_date <= TRAIN_CUTOFF).

    strict=False: log warning per leakage violation, return cases anyway
    strict=True: raise ValueError on first leakage violation
    """
    ...


def test(cases: list[GoldCase]) -> list[GoldCase]:
    """Return cases with decision_date >= TEST_START. Pure filter, no audits."""
    ...


def audit(cases: list[GoldCase]) -> AuditReport:
    """Compute leakage + stratification + region/case-size audit. Pure function."""
    ...
```

CLI:

```bash
python -m eval.dataset audit data/gold_standard/housing_v1.jsonl
python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --strict
python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --json eval/results/audit.json
python -m eval.dataset audit data/gold_standard/housing_v1.jsonl --evidence
```

Exit codes: 0 on clean, 1 on dirty (only when `--strict` is set; without it, always 0).

---

## Tasks

### Task 1: conftest factories + dataset module skeleton (RED)

**Files:**
- Modify: `packages/eval/tests/conftest.py` (append helpers)
- Create: `packages/eval/dataset.py` (stub: imports + dataclasses + function signatures raising `NotImplementedError`)
- Create: `packages/eval/tests/test_dataset.py` (first failing test)

- [ ] **Step 1.1: Add factories to conftest.py**

```python
# Append to packages/eval/tests/conftest.py

import json as _json
from pathlib import Path as _Path
from typing import Any as _Any


_FIXTURES_DIR = _Path(__file__).parent / "fixtures"


def _load_minimal_dict() -> dict:
    return _json.loads((_FIXTURES_DIR / "gold_case_minimal.json").read_text())


def gold_case_dict(**overrides: _Any) -> dict:
    """Return a fresh, valid GoldCase dict with optional overrides.

    Use to build corpora in tests. Top-level fields are merged shallow.
    Example:
        gold_case_dict(case_id="X", decision_date="2020-05-01")
    """
    base = _load_minimal_dict()
    base.update(overrides)
    return base


def write_jsonl(path: _Path, dicts: list[dict]) -> _Path:
    """Write a list of dicts to a JSONL file at `path`. Returns `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for d in dicts:
            f.write(_json.dumps(d))
            f.write("\n")
    return path
```

- [ ] **Step 1.2: Write first failing test (covers imports + dataclass shape)**

```python
# packages/eval/tests/test_dataset.py
"""Tests for the gold-set dataset loader and audit."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore[import-not-found]


class TestPublicSurface:
    def test_module_exports(self):
        from eval import dataset  # noqa: F401
        from eval.dataset import (
            TRAIN_CUTOFF,
            TEST_START,
            STRATIFICATION_FLOOR,
            LoadError,
            LoadResult,
            LeakageViolation,
            AuditReport,
            load,
            train,
            test as test_split,
            audit,
        )
        assert TRAIN_CUTOFF == date(2022, 12, 31)
        assert TEST_START == date(2023, 1, 1)
        assert STRATIFICATION_FLOOR == 5
```

Note: the import `from eval.tests.conftest import ...` works because conftest is also a regular module on the path; alternatively, the helpers can be exposed via a pytest fixture if import-from-conftest is awkward in CI. **If the import fails in Step 1.4, switch to pytest fixtures (`@pytest.fixture` def `gold_case_dict_factory(...)` returning a callable) and re-run.** The plan assumes direct import works; the fallback is documented here.

- [ ] **Step 1.3: Stub `packages/eval/dataset.py` so imports resolve but functions raise**

```python
"""Gold-set dataset loader and audit for the evaluation harness.

See docs/eval/dataset.md for usage. See packages/eval/schema.py for
GoldCase. See .sisyphus/plans/track-a-plan.md Phase 2 for context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from eval.schema import GoldCase, ClaimType, CaseSize


TRAIN_CUTOFF = date(2022, 12, 31)
TEST_START = date(2023, 1, 1)
STRATIFICATION_FLOOR = 5


@dataclass
class LoadError:
    line_number: int
    raw_line: str
    error: str


@dataclass
class LoadResult:
    cases: list[GoldCase]
    errors: list[LoadError]
    source_path: Path

    @property
    def is_clean(self) -> bool:
        return not self.errors


@dataclass
class LeakageViolation:
    case_id: str
    authority_name: str
    authority_cited_date: date
    cutoff: date


@dataclass
class AuditReport:
    n_cases: int
    train_count: int
    test_count: int
    leakage_violations: list[LeakageViolation] = field(default_factory=list)
    understratified_types: dict[ClaimType, int] = field(default_factory=dict)
    region_distribution: dict[str, int] = field(default_factory=dict)
    case_size_distribution: dict[CaseSize, int] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.leakage_violations and not self.understratified_types


def load(
    version: str = "housing_v1",
    *,
    base_dir: Optional[Path] = None,
    strict: bool = False,
) -> LoadResult:
    raise NotImplementedError


def train(cases: list[GoldCase], *, strict: bool = False) -> list[GoldCase]:
    raise NotImplementedError


def test(cases: list[GoldCase]) -> list[GoldCase]:
    raise NotImplementedError


def audit(cases: list[GoldCase]) -> AuditReport:
    raise NotImplementedError
```

- [ ] **Step 1.4: Verify the test passes**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_dataset.py::TestPublicSurface -v
```

Expected: PASS. If `from eval.tests.conftest import ...` fails, switch helpers to fixtures (see note in Step 1.2).

- [ ] **Step 1.5: Commit**

```bash
git add packages/eval/dataset.py packages/eval/tests/test_dataset.py packages/eval/tests/conftest.py
git commit -m "feat(eval): scaffold dataset module + test factories (Phase 2 setup)"
```

---

### Task 2: `load()` — happy path + lenient/strict error modes

**Files:**
- Modify: `packages/eval/dataset.py` (implement `load`)
- Modify: `packages/eval/tests/test_dataset.py` (append `TestLoad`)

- [ ] **Step 2.1: Write the failing tests**

```python
# Append to packages/eval/tests/test_dataset.py


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
        assert result.errors == []
        assert result.source_path == path

    def test_load_default_base_dir(self, tmp_path, monkeypatch):
        # When base_dir is None, look in cwd / data/gold_standard
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
        assert result.errors[0].line_number == 2
        assert "{not json" in result.errors[0].raw_line

    def test_load_lenient_skips_validation_errors(self, tmp_path):
        from eval.dataset import load
        path = tmp_path / "housing_v1.jsonl"
        bad_case = gold_case_dict(case_id="BAD")
        bad_case["decision_date"] = "2018-12-31"  # outside permitted window
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
        bad_case = gold_case_dict()
        bad_case["decision_date"] = "2018-12-31"
        path.write_text(
            json.dumps(gold_case_dict(case_id="OK")) + "\n"
            + json.dumps(bad_case) + "\n"
        )
        with pytest.raises((ValidationError, ValueError)):
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
```

- [ ] **Step 2.2: Verify RED**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_dataset.py::TestLoad -v
```

Expected: every test fails with `NotImplementedError`.

- [ ] **Step 2.3: Implement `load()`**

```python
# In packages/eval/dataset.py — replace the NotImplementedError stub

import json
from pydantic import ValidationError


def load(
    version: str = "housing_v1",
    *,
    base_dir: Optional[Path] = None,
    strict: bool = False,
) -> LoadResult:
    if base_dir is None:
        base_dir = Path.cwd() / "data" / "gold_standard"
    path = base_dir / f"{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Gold-set file not found: {path}")

    cases: list[GoldCase] = []
    errors: list[LoadError] = []
    with path.open() as f:
        for line_number, raw in enumerate(f, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as e:
                if strict:
                    raise
                errors.append(LoadError(line_number=line_number, raw_line=raw.rstrip("\n"), error=str(e)))
                continue
            try:
                cases.append(GoldCase.model_validate(payload))
            except ValidationError as e:
                if strict:
                    raise
                errors.append(LoadError(line_number=line_number, raw_line=raw.rstrip("\n"), error=str(e)))
    return LoadResult(cases=cases, errors=errors, source_path=path)
```

- [ ] **Step 2.4: Verify GREEN**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: all `TestLoad` plus all existing tests pass.

- [ ] **Step 2.5: Commit**

```bash
git add packages/eval/dataset.py packages/eval/tests/test_dataset.py
git commit -m "feat(eval): dataset.load() with lenient + strict modes"
```

---

### Task 3: `train()` and `test()` with leakage check

**Files:**
- Modify: `packages/eval/dataset.py`
- Modify: `packages/eval/tests/test_dataset.py` (append `TestSplits`)

- [ ] **Step 3.1: Write failing tests**

```python
# Append to packages/eval/tests/test_dataset.py


class TestSplits:
    def _build(self, dicts):
        from eval.schema import GoldCase
        return [GoldCase.model_validate(d) for d in dicts]

    def test_train_filters_by_cutoff(self):
        from eval.dataset import train
        cases = self._build([
            gold_case_dict(case_id="X-2020", decision_date="2020-05-01"),
            gold_case_dict(case_id="X-2022", decision_date="2022-12-31"),
            gold_case_dict(case_id="X-2023", decision_date="2023-01-01"),
            gold_case_dict(case_id="X-2024", decision_date="2024-06-15"),
        ])
        result = train(cases)
        assert {c.case_id for c in result} == {"X-2020", "X-2022"}

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
```

- [ ] **Step 3.2: Verify RED**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_dataset.py::TestSplits -v
```

Expected: every test fails with `NotImplementedError`.

- [ ] **Step 3.3: Implement `train()` and `test()`**

```python
# Add to packages/eval/dataset.py

import logging

_log = logging.getLogger(__name__)


def _leakage_violations(cases: list[GoldCase]) -> list[LeakageViolation]:
    violations: list[LeakageViolation] = []
    for case in cases:
        for authority in case.cited_authorities:
            if authority.cited_date > TRAIN_CUTOFF:
                violations.append(
                    LeakageViolation(
                        case_id=case.case_id,
                        authority_name=authority.name,
                        authority_cited_date=authority.cited_date,
                        cutoff=TRAIN_CUTOFF,
                    )
                )
    return violations


def train(cases: list[GoldCase], *, strict: bool = False) -> list[GoldCase]:
    train_cases = [c for c in cases if c.decision_date <= TRAIN_CUTOFF]
    violations = _leakage_violations(train_cases)
    if violations:
        if strict:
            v = violations[0]
            raise ValueError(
                f"Temporal leakage in train case {v.case_id!r}: cites authority "
                f"{v.authority_name!r} dated {v.authority_cited_date} "
                f"(cutoff {v.cutoff}). Total {len(violations)} violation(s)."
            )
        for v in violations:
            _log.warning(
                "Temporal leakage in train case %r: cites %r dated %s (cutoff %s)",
                v.case_id, v.authority_name, v.authority_cited_date, v.cutoff,
            )
    return train_cases


def test(cases: list[GoldCase]) -> list[GoldCase]:
    return [c for c in cases if c.decision_date >= TEST_START]
```

- [ ] **Step 3.4: Verify GREEN**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

- [ ] **Step 3.5: Commit**

```bash
git add packages/eval/dataset.py packages/eval/tests/test_dataset.py
git commit -m "feat(eval): dataset.train()/test() splits with leakage audit"
```

---

### Task 4: `audit()` — leakage + stratification + distributions

**Files:**
- Modify: `packages/eval/dataset.py`
- Modify: `packages/eval/tests/test_dataset.py` (append `TestAudit`)

- [ ] **Step 4.1: Write failing tests**

```python
# Append to packages/eval/tests/test_dataset.py


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
        # 4 cleaning cases; floor is 5 → cleaning is under-stratified
        from eval.dataset import audit
        from eval.schema import ClaimType
        cases = self._build([
            gold_case_dict(case_id=f"C{i}", claim_types=["cleaning"])
            for i in range(4)
        ])
        report = audit(cases)
        assert ClaimType.CLEANING in report.understratified_types
        assert report.understratified_types[ClaimType.CLEANING] == 4

    def test_audit_multi_type_case_counts_toward_each(self):
        # 5 cases each tagged [cleaning, damages] → both at 5, neither under-stratified
        from eval.dataset import audit
        from eval.schema import ClaimType
        cases = self._build([
            gold_case_dict(case_id=f"M{i}", claim_types=["cleaning", "damages"])
            for i in range(5)
        ])
        report = audit(cases)
        assert ClaimType.CLEANING not in report.understratified_types
        assert ClaimType.DAMAGES not in report.understratified_types

    def test_audit_distributions(self):
        from eval.dataset import audit
        from eval.schema import CaseSize
        cases = self._build([
            gold_case_dict(case_id="L1", region="London"),
            gold_case_dict(case_id="L2", region="London"),
            gold_case_dict(case_id="W1", region="Wales"),
        ])
        report = audit(cases)
        assert report.region_distribution == {"London": 2, "Wales": 1}
        assert report.case_size_distribution[CaseSize.SMALL] == 3

    def test_audit_is_clean_property(self):
        from eval.dataset import audit
        # Clean corpus = no leakage AND every represented type at floor
        # Easiest clean corpus: 5 cases of every claim type
        from eval.schema import ClaimType
        types = list(ClaimType)
        cases = self._build([
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in types
            for i in range(5)
        ])
        report = audit(cases)
        # Every type has exactly 5; STRATIFICATION_FLOOR is 5
        # Question: is "exactly 5" under-stratified? No — floor is inclusive.
        assert report.is_clean is True

    def test_audit_empty_corpus(self):
        from eval.dataset import audit
        report = audit([])
        assert report.n_cases == 0
        assert report.train_count == 0
        assert report.test_count == 0
        # All five claim types present in zero cases means all five are under-stratified
        from eval.schema import ClaimType
        assert set(report.understratified_types) == set(ClaimType)
```

- [ ] **Step 4.2: Verify RED**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_dataset.py::TestAudit -v
```

- [ ] **Step 4.3: Implement `audit()`**

```python
# Add to packages/eval/dataset.py

from collections import Counter


def audit(cases: list[GoldCase]) -> AuditReport:
    train_cases = [c for c in cases if c.decision_date <= TRAIN_CUTOFF]
    test_cases = [c for c in cases if c.decision_date >= TEST_START]

    leakage = _leakage_violations(train_cases)

    # Stratification: count cases per claim type (multi-type counts toward each)
    type_counts: Counter[ClaimType] = Counter()
    for case in cases:
        for t in case.claim_types:
            type_counts[t] += 1
    understratified = {
        t: type_counts.get(t, 0)
        for t in ClaimType
        if type_counts.get(t, 0) < STRATIFICATION_FLOOR
    }

    region_dist: dict[str, int] = {}
    size_dist: dict[CaseSize, int] = {}
    for case in cases:
        region_dist[case.region] = region_dist.get(case.region, 0) + 1
        size_dist[case.case_size] = size_dist.get(case.case_size, 0) + 1

    return AuditReport(
        n_cases=len(cases),
        train_count=len(train_cases),
        test_count=len(test_cases),
        leakage_violations=leakage,
        understratified_types=understratified,
        region_distribution=region_dist,
        case_size_distribution=size_dist,
    )
```

- [ ] **Step 4.4: Verify GREEN**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/ -v 2>&1 | tail -15
```

- [ ] **Step 4.5: Commit**

```bash
git add packages/eval/dataset.py packages/eval/tests/test_dataset.py
git commit -m "feat(eval): dataset.audit() with leakage + stratification + distribution"
```

---

### Task 5: CLI — `python -m eval.dataset audit ...`

**Files:**
- Modify: `packages/eval/dataset.py` (add `_cli_main`, `_format_report`)
- Create: `packages/eval/__main__.py` (delegates to `dataset._cli_main`)
- Modify: `packages/eval/tests/test_dataset.py` (append `TestCli`)

- [ ] **Step 5.1: Write failing tests** (subprocess-based; lighter, more honest than mocking argparse)

```python
# Append to packages/eval/tests/test_dataset.py
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]   # worktree root
VENV_PY = "/Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python"


def _run_cli(*args, cwd=None):
    return subprocess.run(
        [VENV_PY, "-m", "eval.dataset", *args],
        cwd=str(cwd) if cwd else None,
        env={"PYTHONPATH": str(REPO_ROOT / "packages")},
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_cli_audit_clean_corpus_exit_zero(self, tmp_path):
        from eval.schema import ClaimType
        # Build a healthy corpus — 5 of each claim type, no leakage
        path = tmp_path / "housing_v1.jsonl"
        cases = [
            gold_case_dict(case_id=f"{t.value}-{i}", claim_types=[t.value])
            for t in ClaimType for i in range(5)
        ]
        write_jsonl(path, cases)
        proc = _run_cli("audit", str(path))
        assert proc.returncode == 0, proc.stderr
        assert "n_cases: 25" in proc.stdout

    def test_cli_audit_dirty_lenient_exit_zero(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        write_jsonl(path, [gold_case_dict()])  # only 1 case; understratified
        proc = _run_cli("audit", str(path))
        # Default mode reports but does not fail
        assert proc.returncode == 0
        assert "understratified" in proc.stdout.lower()

    def test_cli_audit_dirty_strict_exit_one(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        write_jsonl(path, [gold_case_dict()])
        proc = _run_cli("audit", str(path), "--strict")
        assert proc.returncode == 1

    def test_cli_audit_json_output(self, tmp_path):
        path = tmp_path / "housing_v1.jsonl"
        write_jsonl(path, [gold_case_dict()])
        out_json = tmp_path / "audit.json"
        proc = _run_cli("audit", str(path), "--json", str(out_json))
        assert proc.returncode == 0
        assert out_json.exists()
        payload = json.loads(out_json.read_text())
        assert payload["n_cases"] == 1

    def test_cli_audit_evidence_flag(self, tmp_path, monkeypatch):
        # --evidence copies into <cwd>/.sisyphus/evidence/eval/audit_<date>.json
        path = tmp_path / "housing_v1.jsonl"
        write_jsonl(path, [gold_case_dict()])
        proc = _run_cli("audit", str(path), "--evidence", cwd=tmp_path)
        assert proc.returncode == 0
        evidence_dir = tmp_path / ".sisyphus" / "evidence" / "eval"
        assert evidence_dir.exists()
        # one audit_<date>.json file expected
        files = list(evidence_dir.glob("audit_*.json"))
        assert len(files) == 1
```

- [ ] **Step 5.2: Verify RED** (will fail because `__main__.py` doesn't exist yet)

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_dataset.py::TestCli -v
```

- [ ] **Step 5.3: Add CLI to `packages/eval/dataset.py`**

```python
# Add to packages/eval/dataset.py

import argparse
import sys
from datetime import datetime
from typing import Sequence


def _format_report(report: AuditReport) -> str:
    lines = [
        f"n_cases: {report.n_cases}",
        f"train_count (decision_date <= {TRAIN_CUTOFF}): {report.train_count}",
        f"test_count  (decision_date >= {TEST_START}): {report.test_count}",
    ]
    if report.leakage_violations:
        lines.append(f"\nleakage violations ({len(report.leakage_violations)}):")
        for v in report.leakage_violations:
            lines.append(
                f"  - {v.case_id}: cites {v.authority_name!r} dated {v.authority_cited_date} "
                f"(cutoff {v.cutoff})"
            )
    else:
        lines.append("\nleakage violations: none")
    if report.understratified_types:
        lines.append(f"\nunderstratified types (floor {STRATIFICATION_FLOOR}):")
        for t, n in sorted(report.understratified_types.items(), key=lambda x: x[0].value):
            lines.append(f"  - {t.value}: {n}")
    else:
        lines.append("\nstratification: all types at or above floor")
    lines.append(f"\nregion_distribution: {report.region_distribution}")
    lines.append(
        "case_size_distribution: "
        + str({k.value: v for k, v in report.case_size_distribution.items()})
    )
    lines.append(f"\nis_clean: {report.is_clean}")
    return "\n".join(lines)


def _report_to_dict(report: AuditReport) -> dict:
    return {
        "n_cases": report.n_cases,
        "train_count": report.train_count,
        "test_count": report.test_count,
        "leakage_violations": [
            {
                "case_id": v.case_id,
                "authority_name": v.authority_name,
                "authority_cited_date": v.authority_cited_date.isoformat(),
                "cutoff": v.cutoff.isoformat(),
            }
            for v in report.leakage_violations
        ],
        "understratified_types": {t.value: n for t, n in report.understratified_types.items()},
        "region_distribution": dict(report.region_distribution),
        "case_size_distribution": {
            k.value: v for k, v in report.case_size_distribution.items()
        },
        "is_clean": report.is_clean,
    }


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.dataset")
    sub = parser.add_subparsers(dest="cmd", required=True)

    audit_p = sub.add_parser("audit", help="Audit a gold-set JSONL file")
    audit_p.add_argument("path", type=Path, help="Path to <version>.jsonl")
    audit_p.add_argument("--strict", action="store_true",
                         help="Exit non-zero if the corpus is not clean")
    audit_p.add_argument("--json", type=Path, default=None,
                         help="Write the report as JSON to PATH")
    audit_p.add_argument("--evidence", action="store_true",
                         help="Also write JSON into "
                              ".sisyphus/evidence/eval/audit_<date>.json (cwd-relative)")

    args = parser.parse_args(argv)

    if args.cmd == "audit":
        # Use the file's parent as the base_dir; load() expects <version>.jsonl
        version = args.path.stem
        result = load(version, base_dir=args.path.parent)
        if result.errors:
            print(f"Load errors ({len(result.errors)}):", file=sys.stderr)
            for err in result.errors:
                print(f"  line {err.line_number}: {err.error}", file=sys.stderr)
        report = audit(result.cases)
        print(_format_report(report))
        if args.json is not None:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(_report_to_dict(report), indent=2))
        if args.evidence:
            today = datetime.now().strftime("%Y-%m-%d")
            evidence_path = Path.cwd() / ".sisyphus" / "evidence" / "eval" / f"audit_{today}.json"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(json.dumps(_report_to_dict(report), indent=2))
        return 1 if (args.strict and not report.is_clean) else 0

    return 2  # unreachable
```

- [ ] **Step 5.4: Create `packages/eval/__main__.py`**

```python
"""Entry-point for `python -m eval.dataset` and `python -m eval`."""
from eval.dataset import _cli_main

raise SystemExit(_cli_main())
```

Wait — `python -m eval.dataset` needs `dataset.py` itself to be runnable, not `__main__.py`. Two options:

- **A.** Put `if __name__ == "__main__": raise SystemExit(_cli_main())` at the bottom of `dataset.py`. Then `python -m eval.dataset` works and we don't need `__main__.py` at all.
- **B.** Keep `__main__.py` for `python -m eval ...` and also add the bottom-of-file guard.

Go with **A** — single file, simpler. Skip Step 5.4 (no `__main__.py`).

```python
# Append to packages/eval/dataset.py (very last line):

if __name__ == "__main__":
    raise SystemExit(_cli_main())
```

- [ ] **Step 5.5: Verify GREEN**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/ -v 2>&1 | tail -15
```

- [ ] **Step 5.6: Manual smoke**

```bash
cd /Users/msharif/Documents/Projects/proposer/worktrees/sha-28-gold-set
PYTHONPATH=packages /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python \
  -m eval.dataset audit packages/eval/tests/fixtures/gold_case_minimal.json 2>&1 || true
```

This will fail because the fixture is a single-case **JSON** file, not a JSONL corpus. That's fine — it confirms the CLI runs. To smoke-test against a real JSONL, build one quickly:

```bash
mkdir -p /tmp/gold && \
  cat packages/eval/tests/fixtures/gold_case_minimal.json | tr -d '\n' > /tmp/gold/housing_v1.jsonl && \
  echo "" >> /tmp/gold/housing_v1.jsonl && \
  PYTHONPATH=packages /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python \
    -m eval.dataset audit /tmp/gold/housing_v1.jsonl
```

Expected: `n_cases: 1`, `understratified` listing the missing types, `is_clean: False`, exit 0.

- [ ] **Step 5.7: Commit**

```bash
git add packages/eval/dataset.py packages/eval/tests/test_dataset.py
git commit -m "feat(eval): CLI for dataset audit (lenient default, --strict opt-in)"
```

---

### Task 6: Public API re-exports + docs

**Files:**
- Modify: `packages/eval/__init__.py` (re-export the dataset surface)
- Create: `docs/eval/dataset.md` (usage doc)

- [ ] **Step 6.1: Update `__init__.py`**

```python
# Append to packages/eval/__init__.py
from eval.dataset import (
    AuditReport,
    LeakageViolation,
    LoadError,
    LoadResult,
    STRATIFICATION_FLOOR,
    TEST_START,
    TRAIN_CUTOFF,
    audit,
    load,
    test,
    train,
)

# extend the __all__ list (preserve schema entries)
__all__ += [
    "AuditReport",
    "LeakageViolation",
    "LoadError",
    "LoadResult",
    "STRATIFICATION_FLOOR",
    "TEST_START",
    "TRAIN_CUTOFF",
    "audit",
    "load",
    "test",
    "train",
]
```

- [ ] **Step 6.2: Verify re-exports**

```bash
cd /Users/msharif/Documents/Projects/proposer/worktrees/sha-28-gold-set && \
PYTHONPATH=packages /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python \
  -c "from eval import load, train, test, audit, AuditReport; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 6.3: Write `docs/eval/dataset.md`**

Document: purpose; default lenient / strict opt-in pattern; the four functions with short examples; the audit report fields; CLI usage with all four flags; how this lands in CI; pointers to SHA-90 (leakage data), SHA-92 (multi-type stratification). Keep under 150 lines.

- [ ] **Step 6.4: Run full test suite + coverage**

```bash
cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python \
  -m pytest tests/ --cov=eval --cov-report=term-missing 2>&1 | tail -15
```

Expected: ≥80% on `eval/dataset.py` (target hit easily — 7 test classes covering every branch). Save evidence to `.sisyphus/evidence/eval/phase2-coverage.txt`.

- [ ] **Step 6.5: Commit**

```bash
git add packages/eval/__init__.py docs/eval/dataset.md .sisyphus/evidence/eval/phase2-coverage.txt
git commit -m "docs(eval): dataset module re-exports and usage doc"
```

---

## Phase 2 exit checklist

- [ ] `packages/eval/dataset.py` exists with `load`, `train`, `test`, `audit` and dataclasses
- [ ] `from eval import load, train, test, audit, AuditReport` works
- [ ] `python -m eval.dataset audit <path>` runs (lenient default, `--strict` opt-in, `--json`, `--evidence`)
- [ ] All 5 design decisions implemented as specified:
  1. `train()` lenient by default, strict on flag
  2. `audit()` reports always; CLI `--strict` makes it gate
  3. `load()` skips bad lines lenient, strict raises on first
  4. No auto-audit on `load()` / `train()` / `test()` — explicit `audit(cases)` call
  5. Audit text → stdout; `--json PATH`, `--evidence` flags optional
- [ ] Coverage ≥80% on `eval/dataset.py`
- [ ] All existing schema tests still pass (53 + new dataset tests)
- [ ] 6 commits in `git log`, scoped, conventional-commits style
- [ ] Linear ticket opened (parent SHA-28) and moved to Done at end

Once all checked, halt and request review before opening the PR for the whole branch.

---

## Linear handling

After Step 6.5 lands, open a single Phase 2 ticket parented to SHA-28:

- Title: "Phase 2: dataset loader (load/train/test/audit) + CLI"
- Labels: Thesis, Eval
- Priority: 1 (Urgent — it's the prerequisite for Phase 4)
- Body: link to this plan; list the 6 commits; DoD = Phase 2 exit checklist above
- Move to Done immediately upon ticket creation (work is complete by then).
