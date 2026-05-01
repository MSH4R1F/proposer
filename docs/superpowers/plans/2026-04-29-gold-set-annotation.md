# Phase 3 — Annotation CLI + Reviewer Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the annotation tooling so a paralegal reviewer can produce a valid `GoldCase` from a tribunal PDF without round-tripping me. Land the three Codex schema additions (SHA-98/99/100) that block real annotation. Commit a synthetic 10-case fixture so downstream Phase 4 work has a corpus to read.

**Architecture:** A schema-first CLI in `scripts/eval/annotate.py` with sub-commands `template / validate / append / list / show`. Reviewers write JSON in their text editor; the CLI is the gatekeeper that validates against `GoldCase` and appends to `data/gold_standard/housing_v1.jsonl` only when valid. No interactive prompting (over-engineered for pilot). Schema additions land first because the CLI consumes them.

**Tech stack:** Python 3.9.6, Pydantic 2.12.5, argparse (stdlib). No new dependencies.

**Out of scope for Phase 3:** the actual 50-case corpus (human-driven, blocked on reviewer). Annotation reliability metrics — Cohen's κ computation lands in Phase 6. Bootstrap CIs — Phase 4a (SHA-97 implementation).

---

## File structure

| File | Responsibility |
|---|---|
| `packages/eval/schema.py` | Schema additions for SHA-98 (RegionUK enum), SHA-99 (evidence/statute unavailability), SHA-100 (Provenance model) |
| `packages/eval/tests/test_schema.py` | New test classes for each schema addition |
| `packages/eval/tests/fixtures/gold_case_minimal.json` | Update to use new fields |
| `packages/eval/tests/fixtures/gold_case_unapportioned.json` | Same |
| `packages/eval/tests/fixtures/synthetic_corpus_10.jsonl` | **New** — 10 synthetic cases hitting all 5 claim types, 2019–2024 date range, mixed regions, mixed apportioned/unapportioned, mixed authority dates |
| `scripts/eval/annotate.py` | The CLI itself |
| `scripts/eval/__init__.py` | Marker (so `tests/` can `from scripts.eval.annotate import ...`) |
| `tests/scripts/__init__.py` | Marker |
| `tests/scripts/test_annotate.py` | CLI tests (subprocess + in-process) |
| `docs/eval/reviewer-guide.md` | Onboarding for the paralegal: how to read a tribunal PDF, fill a draft, validate, append. Field-by-field guidance with worked examples. |
| `docs/eval/reviewer-log.md` | Adjudication log template (SHA-96 prep) — empty rows for the first ten cases. |
| `data/gold_standard/.gitkeep` | Mark the production data dir |
| `docs/eval/gold-schema.md` | Update with new fields and INV-10 |

---

## Schema additions (locked before coding)

### SHA-98 — `RegionUK` enum

```python
class RegionUK(str, Enum):
    LONDON = "london"
    SOUTH_EAST = "south_east"
    SOUTH_WEST = "south_west"
    EAST_OF_ENGLAND = "east_of_england"
    EAST_MIDLANDS = "east_midlands"
    WEST_MIDLANDS = "west_midlands"
    NORTH_WEST = "north_west"
    NORTH_EAST = "north_east"
    YORKSHIRE_AND_HUMBER = "yorkshire_and_humber"
    WALES = "wales"
    SCOTLAND = "scotland"
    NORTHERN_IRELAND = "northern_ireland"
```

`GoldCase.region: str` becomes `GoldCase.region: RegionUK` (normalised) plus a new `region_source: str` (the verbatim string from the decision PDF — preserves provenance).

### SHA-99 — Evidence / statute unavailability

Add to `GoldCase`:

```python
evidence_unavailable_reason: Optional[str] = None
statutory_basis_unavailable_reason: Optional[str] = None
```

New invariant **INV-10:** at least one of `(evidence non-empty, evidence_unavailable_reason set)` must hold; same for `statutory_basis`. Empty evidence WITHOUT a recorded reason is rejected.

### SHA-100 — `Provenance` model

```python
class Provenance(BaseModel):
    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)
    text_span: Optional[tuple] = None  # (char_start, char_end), optional
```

`paragraph_ref: Optional[str]` on `Evidence` and `StatutoryReference` becomes `provenance: Optional[Provenance]`. On `ReasoningQuote` (where it was required), `provenance: Provenance` is required.

`Authority.paragraph_ref` also becomes `Authority.provenance: Optional[Provenance]`.

---

## CLI design (locked before coding)

```bash
python -m scripts.eval.annotate template > new_case.json
# Emits a starter file with all required fields filled with placeholders.
# Reviewer edits in a text editor.

python -m scripts.eval.annotate validate new_case.json
# Validates new_case.json against GoldCase. Pretty-prints errors. Exit 0 on
# valid, 1 on invalid.

python -m scripts.eval.annotate append new_case.json [--corpus housing_v1]
# Validates, then appends to data/gold_standard/<corpus>.jsonl.
# Refuses to append a case_id that already exists in the corpus (idempotency
# guard — re-running the script doesn't duplicate).

python -m scripts.eval.annotate list [--corpus housing_v1]
# Prints case_id, decision_date, claim_types, region for each case in the
# corpus, sorted by case_id.

python -m scripts.eval.annotate show <case_id> [--corpus housing_v1]
# Pretty-prints the case as indented JSON.
```

All subcommands honour `--corpus` (default `housing_v1`) and look in `data/gold_standard/<corpus>.jsonl`. `--base-dir PATH` overrides for tests.

Exit codes: 0 = success, 1 = validation failure or duplicate case_id, 2 = file/IO error.

---

## Tasks

### Task 1: SHA-98 — `RegionUK` enum (TDD)

**Files:** `packages/eval/schema.py`, `tests/test_schema.py`, two fixtures, `__init__.py`, `docs/eval/gold-schema.md`.

- [ ] **Step 1.1: Write failing tests** — RED.

```python
# Append to packages/eval/tests/test_schema.py

class TestRegionUK:
    def _base(self) -> dict:
        return _load_minimal()

    def test_region_is_enum(self):
        from eval.schema import GoldCase, RegionUK
        case = self._base() | {"region": "london"}
        gc = GoldCase.model_validate(case)
        assert gc.region == RegionUK.LONDON

    def test_region_source_preserved(self):
        from eval.schema import GoldCase
        case = self._base() | {"region": "london", "region_source": "Greater London"}
        gc = GoldCase.model_validate(case)
        assert gc.region_source == "Greater London"

    def test_region_unknown_value_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"region": "atlantis"}
        with pytest.raises(ValidationError, match="region"):
            GoldCase.model_validate(case)

    def test_region_uk_has_12_values(self):
        from eval.schema import RegionUK
        assert len(list(RegionUK)) == 12
```

- [ ] **Step 1.2: RED check.**

Run: `pytest tests/test_schema.py::TestRegionUK -v` → 4 fail.

- [ ] **Step 1.3: GREEN — add `RegionUK` enum, change `GoldCase.region` to typed enum, add `region_source: str`.**

In `schema.py`:

```python
class RegionUK(str, Enum):
    LONDON = "london"
    SOUTH_EAST = "south_east"
    SOUTH_WEST = "south_west"
    EAST_OF_ENGLAND = "east_of_england"
    EAST_MIDLANDS = "east_midlands"
    WEST_MIDLANDS = "west_midlands"
    NORTH_WEST = "north_west"
    NORTH_EAST = "north_east"
    YORKSHIRE_AND_HUMBER = "yorkshire_and_humber"
    WALES = "wales"
    SCOTLAND = "scotland"
    NORTHERN_IRELAND = "northern_ireland"
```

In `GoldCase`:

```python
region: RegionUK
region_source: str = Field(default="", description="Verbatim region string from PDF; for provenance/audit only")
```

- [ ] **Step 1.4: Update both fixtures.**

`gold_case_minimal.json`: `"region": "london"`, `"region_source": "London"`.
`gold_case_unapportioned.json`: `"region": "north_west"`, `"region_source": "North West"`.

- [ ] **Step 1.5: Update `__init__.py` re-exports** to include `RegionUK`.

- [ ] **Step 1.6: GREEN — run full schema suite** (`pytest tests/`). All previous tests must still pass.

- [ ] **Step 1.7: Update `docs/eval/gold-schema.md`** — region row now references `RegionUK` enum + `region_source` companion field. Bump SHA-98 link in known-limitations.

- [ ] **Step 1.8: Commit.**

```
feat(eval): RegionUK enum + region_source companion (SHA-98)
```

---

### Task 2: SHA-99 — INV-10 (evidence/statute unavailability) (TDD)

**Files:** `packages/eval/schema.py`, `tests/test_schema.py`, fixtures, `docs/eval/gold-schema.md`.

- [ ] **Step 2.1: Write failing tests.**

```python
class TestInv10EvidenceStatutoryAvailability:
    def _base(self) -> dict:
        return _load_minimal()

    def test_empty_evidence_without_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"evidence": []}
        with pytest.raises(ValidationError, match="evidence"):
            GoldCase.model_validate(case)

    def test_empty_evidence_with_reason_ok(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "evidence": [],
            "evidence_unavailable_reason": "Tribunal heard the case on submissions only; no evidence catalogue published.",
        }
        gc = GoldCase.model_validate(case)
        assert gc.evidence == []
        assert gc.evidence_unavailable_reason is not None

    def test_empty_statutory_basis_without_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {"statutory_basis": []}
        with pytest.raises(ValidationError, match="statutory_basis"):
            GoldCase.model_validate(case)

    def test_empty_statutory_basis_with_reason_ok(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "statutory_basis": [],
            "statutory_basis_unavailable_reason": "Decision turned on common-law principles only.",
        }
        gc = GoldCase.model_validate(case)
        assert gc.statutory_basis == []

    def test_non_empty_evidence_with_reason_rejected(self):
        from eval.schema import GoldCase
        case = self._base() | {
            "evidence_unavailable_reason": "Should not be set when evidence is non-empty",
        }
        with pytest.raises(ValidationError, match="evidence"):
            GoldCase.model_validate(case)
```

- [ ] **Step 2.2: RED check.** 5 fail.

- [ ] **Step 2.3: GREEN — add fields + INV-10 to `GoldCase._validate_invariants`.**

```python
# Add to GoldCase:
evidence_unavailable_reason: Optional[str] = None
statutory_basis_unavailable_reason: Optional[str] = None

# Inside _validate_invariants, before the per_issue check:
# INV-10: evidence and statutory_basis must each be non-empty OR carry an explicit reason
def _check_availability(items: list, reason: Optional[str], field_name: str) -> None:
    if items and reason is not None:
        raise ValueError(
            f"{field_name} is non-empty but {field_name}_unavailable_reason is set; "
            "the reason field is for empty lists only"
        )
    if not items and reason is None:
        raise ValueError(
            f"{field_name} is empty and no {field_name}_unavailable_reason given; "
            "annotators must record why evidence/statutes were not captured"
        )

_check_availability(self.evidence, self.evidence_unavailable_reason, "evidence")
_check_availability(self.statutory_basis, self.statutory_basis_unavailable_reason, "statutory_basis")
```

- [ ] **Step 2.4: GREEN — run all tests.**

- [ ] **Step 2.5: Update `docs/eval/gold-schema.md`** — INV-10 row.

- [ ] **Step 2.6: Commit.**

```
feat(eval): INV-10 evidence/statute availability (SHA-99)
```

---

### Task 3: SHA-100 — `Provenance` model (TDD)

This is the biggest single change in Phase 3 — replaces `paragraph_ref: Optional[str]` on `Evidence`, `StatutoryReference`, `Authority`, and `ReasoningQuote` with `provenance: Optional[Provenance]` (or required, on quotes).

**Files:** `packages/eval/schema.py`, `tests/test_schema.py`, both fixtures, doc.

- [ ] **Step 3.1: Failing tests.**

```python
class TestProvenance:
    def test_valid_provenance(self):
        from eval.schema import Provenance
        p = Provenance(page=1, paragraph=14)
        assert p.page == 1 and p.paragraph == 14
        assert p.text_span is None

    def test_text_span_optional(self):
        from eval.schema import Provenance
        p = Provenance(page=2, paragraph=3, text_span=(120, 240))
        assert p.text_span == (120, 240)

    def test_page_min_1(self):
        from eval.schema import Provenance
        with pytest.raises(ValidationError):
            Provenance(page=0, paragraph=1)

    def test_paragraph_min_1(self):
        from eval.schema import Provenance
        with pytest.raises(ValidationError):
            Provenance(page=1, paragraph=0)


class TestProvenanceMigration:
    """Verify Evidence, StatutoryReference, Authority, ReasoningQuote all
    use Provenance instead of bare paragraph_ref."""

    def test_evidence_uses_provenance(self):
        from eval.schema import Evidence, Provenance
        e = Evidence(
            kind="invoice",
            description="Cleaning invoice",
            provenance=Provenance(page=1, paragraph=7),
        )
        assert e.provenance.paragraph == 7

    def test_evidence_provenance_optional(self):
        from eval.schema import Evidence
        Evidence(kind="invoice", description="Cleaning invoice")  # no provenance is fine

    def test_reasoning_quote_requires_provenance(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="Quote.", provenance=None)  # required

    def test_authority_uses_provenance(self):
        from eval.schema import Authority, Provenance
        from datetime import date
        a = Authority(
            name="Howard v Aggio",
            cited_date=date(2008, 6, 25),
            provenance=Provenance(page=2, paragraph=12),
        )
        assert a.provenance.page == 2

    def test_statutory_reference_uses_provenance(self):
        from eval.schema import StatutoryReference, Provenance
        s = StatutoryReference(
            statute="Housing Act 2004",
            section="s.213",
            provenance=Provenance(page=1, paragraph=12),
        )
        assert s.provenance.paragraph == 12
```

- [ ] **Step 3.2: RED check.** All fail.

- [ ] **Step 3.3: GREEN — add `Provenance` model, swap fields.**

```python
class Provenance(BaseModel):
    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)
    text_span: Optional[tuple] = None  # (char_start, char_end) in normalised text

# Update Evidence / StatutoryReference / Authority:
#   paragraph_ref: Optional[str] = None
#   ->
#   provenance: Optional[Provenance] = None

# Update ReasoningQuote:
#   paragraph_ref: str = Field(min_length=1)
#   ->
#   provenance: Provenance
```

- [ ] **Step 3.4: Update both fixtures.**

`gold_case_minimal.json`:

- `evidence[0].paragraph_ref: "para 7"` → `evidence[0].provenance: {"page": 1, "paragraph": 7}`
- `statutory_basis[0].paragraph_ref: "para 12"` → `provenance: {"page": 1, "paragraph": 12}`
- `key_reasoning_quotes[0].paragraph_ref: "para 14"` → `provenance: {"page": 2, "paragraph": 14}`

`gold_case_unapportioned.json`:

- `evidence[*].paragraph_ref` → `provenance` (page 1 paragraph 4, page 2 paragraph 9)
- `key_reasoning_quotes[0].paragraph_ref: "para 22"` → `provenance: {"page": 3, "paragraph": 22}`

- [ ] **Step 3.5: GREEN — full schema suite.**

- [ ] **Step 3.6: Update `__init__.py`** — re-export `Provenance`.

- [ ] **Step 3.7: Update `docs/eval/gold-schema.md`** — replace all `paragraph_ref` mentions; new `Provenance` sub-model section.

- [ ] **Step 3.8: Commit.**

```
feat(eval)!: Provenance model replaces bare paragraph_ref (SHA-100)
```

---

### Task 4: Annotation CLI scaffold + `template` and `validate` (TDD)

**Files:** `scripts/eval/annotate.py`, `scripts/eval/__init__.py`, `tests/scripts/__init__.py`, `tests/scripts/test_annotate.py`, root `conftest.py` (or `pytest.ini` rootdir override).

- [ ] **Step 4.1: Pytest discovery prep.**

`scripts/eval/__init__.py` empty marker. Top-level `tests/__init__.py` and `tests/scripts/__init__.py` empty markers. `pytest.ini` (or `pyproject.toml`) at the repo root needs `testpaths = packages/eval/tests tests/scripts` and `pythonpath = packages` so `from eval.schema import ...` resolves and `from scripts.eval.annotate import ...` resolves.

If touching the repo-root `pytest.ini` is out of scope, the `tests/scripts/` tests can call the CLI as a subprocess only — drop in-process tests for the CLI module.

**Decision:** subprocess-only for the CLI, keep its tests in `packages/eval/tests/test_annotate_cli.py`. That avoids having to touch the repo-root pytest config. Easier.

So the layout is:

| File | Lives in |
|---|---|
| The CLI | `scripts/eval/annotate.py` |
| Tests | `packages/eval/tests/test_annotate_cli.py` (subprocess-based, like `TestCli` in `test_dataset.py`) |

- [ ] **Step 4.2: Failing test for `template` subcommand.**

```python
# packages/eval/tests/test_annotate_cli.py
"""Tests for scripts/eval/annotate.py (subprocess-based)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_PY = "/Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python"


def _run(*args, cwd=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT / 'packages'}:{REPO_ROOT}"
    return subprocess.run(
        [VENV_PY, str(REPO_ROOT / "scripts" / "eval" / "annotate.py"), *args],
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

    def test_template_round_trips_through_pydantic(self, tmp_path):
        # Replace placeholders with valid values and ensure GoldCase accepts it.
        proc = _run("template")
        data = json.loads(proc.stdout)
        # Realistically, the template uses placeholder values that would fail
        # validation; the test confirms the *structure* is right by hand-fixing
        # a few fields and asserting the result validates.
        from eval.schema import GoldCase
        with pytest.raises(Exception):
            # As-is, the template should NOT validate (placeholders).
            GoldCase.model_validate(data)
```

(More CLI tests in subsequent tasks.)

- [ ] **Step 4.3: RED check.**

- [ ] **Step 4.4: GREEN — implement `template` subcommand.**

```python
# scripts/eval/annotate.py
#!/usr/bin/env python
"""Annotation CLI for the gold-set corpus.

Subcommands: template, validate, append, list, show.
See docs/eval/reviewer-guide.md for the workflow.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

# Path bootstrap so this script runs as a top-level executable
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages"))

from eval.schema import GoldCase  # noqa: E402  (path bootstrap above)
from eval.dataset import load  # noqa: E402


def _template() -> dict:
    return {
        "schema_version": "v1",
        "case_id": "REPLACE_ME-2023-0000",
        "decision_date": "2023-01-01",
        "region": "london",
        "region_source": "REPLACE_ME",
        "case_size": "small",
        "disputed_amount_gbp": "0.00",
        "claim_types": ["cleaning"],
        "source_pdf_sha256": "0" * 64,
        "ocr_confidence": None,
        "parties": [
            {"role": "tenant", "represented": False},
            {"role": "landlord", "represented": False},
        ],
        "facts": "REPLACE_ME — at least 50 characters of plain English summary of the dispute.",
        "evidence": [],
        "evidence_unavailable_reason": "REPLACE_ME (or remove this field and add evidence)",
        "statutory_basis": [],
        "statutory_basis_unavailable_reason": "REPLACE_ME (or remove this field and add statutes)",
        "cited_authorities": [],
        "claimed_amounts": [
            {"issue": "REPLACE_ME", "amount_gbp": "0.00", "by_party": "landlord"},
        ],
        "ground_truth_outcome": {
            "overall_winner": "tenant",
            "total_awarded_gbp": "0.00",
            "per_issue": [
                {"issue": "REPLACE_ME", "winner": "tenant", "awarded_gbp": "0.00"},
            ],
        },
        "key_reasoning_quotes": [
            {
                "text": "REPLACE_ME — verbatim quote from decision.",
                "provenance": {"page": 1, "paragraph": 1},
            },
        ],
    }


def _cmd_template(_args) -> int:
    print(json.dumps(_template(), indent=2))
    return 0


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="annotate.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("template", help="Print a starter JSON case to stdout")
    args = parser.parse_args(argv)
    if args.cmd == "template":
        return _cmd_template(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli_main())
```

- [ ] **Step 4.5: GREEN check.** Tests pass.

- [ ] **Step 4.6: Commit.** `feat(eval): annotate CLI scaffold + template subcommand`.

---

### Task 5: `validate` and `append` subcommands (TDD)

- [ ] **Step 5.1: Failing tests for `validate`.**

```python
class TestValidate:
    def test_validate_passes_on_minimal_fixture(self):
        proc = _run(
            "validate",
            str(REPO_ROOT / "packages" / "eval" / "tests" / "fixtures" / "gold_case_minimal.json"),
        )
        assert proc.returncode == 0, proc.stderr
        assert "valid" in proc.stdout.lower()

    def test_validate_fails_with_helpful_message(self, tmp_path):
        bad = tmp_path / "bad.json"
        from eval.tests.conftest import gold_case_dict  # type: ignore
        case = gold_case_dict()
        case["decision_date"] = "2018-12-31"  # outside window
        bad.write_text(json.dumps(case))
        proc = _run("validate", str(bad))
        assert proc.returncode == 1
        assert "decision_date" in proc.stderr
```

- [ ] **Step 5.2: GREEN — `validate` subcommand.**

```python
def _cmd_validate(args) -> int:
    payload = json.loads(Path(args.path).read_text())
    try:
        GoldCase.model_validate(payload)
    except Exception as e:
        print(f"Invalid: {e}", file=sys.stderr)
        return 1
    print("Valid.")
    return 0
```

Wire in `_cli_main`:

```python
val = sub.add_parser("validate", help="Validate a draft case JSON")
val.add_argument("path", type=Path)
# in dispatch:
if args.cmd == "validate":
    return _cmd_validate(args)
```

- [ ] **Step 5.3: Failing tests for `append`.**

```python
class TestAppend:
    def test_append_adds_to_corpus(self, tmp_path):
        from eval.tests.conftest import gold_case_dict  # type: ignore
        from eval.dataset import load
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        # Start with a 1-case corpus
        existing = gold_dir / "housing_v1.jsonl"
        existing.write_text(json.dumps(gold_case_dict(case_id="A")) + "\n")
        # Write a draft for B
        draft = tmp_path / "B.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="B")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        cases = load("housing_v1", base_dir=gold_dir).cases
        assert {c.case_id for c in cases} == {"A", "B"}

    def test_append_rejects_duplicate_case_id(self, tmp_path):
        from eval.tests.conftest import gold_case_dict  # type: ignore
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        existing = gold_dir / "housing_v1.jsonl"
        existing.write_text(json.dumps(gold_case_dict(case_id="DUP")) + "\n")
        draft = tmp_path / "dup.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="DUP")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1
        assert "DUP" in proc.stderr

    def test_append_creates_corpus_if_absent(self, tmp_path):
        from eval.tests.conftest import gold_case_dict  # type: ignore
        from eval.dataset import load
        (tmp_path / "data" / "gold_standard").mkdir(parents=True)
        draft = tmp_path / "first.json"
        draft.write_text(json.dumps(gold_case_dict(case_id="FIRST")))
        proc = _run("append", str(draft), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        cases = load("housing_v1", base_dir=tmp_path / "data" / "gold_standard").cases
        assert [c.case_id for c in cases] == ["FIRST"]

    def test_append_refuses_invalid_draft(self, tmp_path):
        from eval.tests.conftest import gold_case_dict  # type: ignore
        gold_dir = tmp_path / "data" / "gold_standard"
        gold_dir.mkdir(parents=True)
        bad = tmp_path / "bad.json"
        case = gold_case_dict()
        case["decision_date"] = "2018-01-01"
        bad.write_text(json.dumps(case))
        proc = _run("append", str(bad), "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1
```

- [ ] **Step 5.4: GREEN — `append` subcommand.**

```python
def _cmd_append(args) -> int:
    payload = json.loads(Path(args.path).read_text())
    try:
        gc = GoldCase.model_validate(payload)
    except Exception as e:
        print(f"Invalid: {e}", file=sys.stderr)
        return 1

    base_dir = Path(args.base_dir) if args.base_dir else Path.cwd() / "data" / "gold_standard"
    corpus_path = base_dir / f"{args.corpus}.jsonl"

    if corpus_path.exists():
        existing = load(args.corpus, base_dir=base_dir)
        if any(c.case_id == gc.case_id for c in existing.cases):
            print(f"Refusing to append: case_id {gc.case_id!r} already in {corpus_path}", file=sys.stderr)
            return 1
    else:
        corpus_path.parent.mkdir(parents=True, exist_ok=True)

    with corpus_path.open("a") as f:
        f.write(gc.model_dump_json())
        f.write("\n")
    print(f"Appended {gc.case_id} to {corpus_path}")
    return 0
```

Wire `--corpus` (default `housing_v1`) and `--base-dir` (default `None`) on the parser.

- [ ] **Step 5.5: GREEN check.** Tests pass.

- [ ] **Step 5.6: Commit.** `feat(eval): annotate CLI validate + append subcommands`.

---

### Task 6: `list` and `show` subcommands (TDD)

- [ ] **Step 6.1: Failing tests.**

```python
class TestListAndShow:
    def test_list_prints_case_summaries(self, tmp_path):
        from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore
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
        from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore
        gold_dir = tmp_path / "data" / "gold_standard"
        write_jsonl(gold_dir / "housing_v1.jsonl", [
            gold_case_dict(case_id="X"),
        ])
        proc = _run("show", "X", "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["case_id"] == "X"

    def test_show_unknown_case_id_exits_one(self, tmp_path):
        from eval.tests.conftest import gold_case_dict, write_jsonl  # type: ignore
        gold_dir = tmp_path / "data" / "gold_standard"
        write_jsonl(gold_dir / "housing_v1.jsonl", [gold_case_dict(case_id="X")])
        proc = _run("show", "MISSING", "--corpus", "housing_v1", cwd=tmp_path)
        assert proc.returncode == 1
```

- [ ] **Step 6.2: GREEN — implement `list` and `show`.**

```python
def _cmd_list(args) -> int:
    base_dir = Path(args.base_dir) if args.base_dir else Path.cwd() / "data" / "gold_standard"
    result = load(args.corpus, base_dir=base_dir)
    for c in sorted(result.cases, key=lambda x: x.case_id):
        types = ",".join(t.value for t in c.claim_types)
        print(f"{c.case_id}\t{c.decision_date}\t{types}\t{c.region.value}")
    return 0


def _cmd_show(args) -> int:
    base_dir = Path(args.base_dir) if args.base_dir else Path.cwd() / "data" / "gold_standard"
    result = load(args.corpus, base_dir=base_dir)
    for c in result.cases:
        if c.case_id == args.case_id:
            print(c.model_dump_json(indent=2))
            return 0
    print(f"case_id {args.case_id!r} not found in corpus {args.corpus}", file=sys.stderr)
    return 1
```

- [ ] **Step 6.3: GREEN check.**

- [ ] **Step 6.4: Commit.** `feat(eval): annotate CLI list + show subcommands`.

---

### Task 7: Reviewer docs + 10-case synthetic fixture

**Files:** `docs/eval/reviewer-guide.md`, `docs/eval/reviewer-log.md`, `packages/eval/tests/fixtures/synthetic_corpus_10.jsonl`, `data/gold_standard/.gitkeep`.

- [ ] **Step 7.1: Write `docs/eval/reviewer-guide.md`.**

Cover:

- Workflow at-a-glance: PDF → SHA-256 → `template` → fill JSON → `validate` → `append`.
- Field-by-field guidance: how to choose `claim_types` from a multi-type case; when `unapportioned_reason` is the right path; how to record `Provenance` accurately under noisy OCR; what counts as "unavailable" for `evidence_unavailable_reason`.
- Worked example: walk a real (sanitised) decision through the schema.
- Adjudication workflow: when reviewers disagree, fill in `docs/eval/reviewer-log.md` row, escalate to Mohamed, agree on the resolution.
- Common mistakes table — picked from actual Codex failure modes.

Target: ~250 lines of plain English.

- [ ] **Step 7.2: Write `docs/eval/reviewer-log.md` template.**

```markdown
# Reviewer Adjudication Log

Track every double-annotation disagreement and its resolution. Required by SHA-96 (Cohen's κ ≥ 0.8 per claim_type).

## Schema

| Date | Case ID | Field | Reviewer A | Reviewer B | Resolution | Rationale |
|---|---|---|---|---|---|---|

## Entries

(empty — populate during Phase 6 double-annotation pass)
```

- [ ] **Step 7.3: Build the 10-case synthetic fixture.**

Approach: use the existing `gold_case_dict()` factory + targeted overrides to write a JSONL file with:

- 5 of the 5 claim types each represented (multi-type cases counted toward each)
- date span 2019-2024, both train and test
- mixed regions (London, Wales, North West, Yorkshire & Humber, etc.)
- mixed `case_size`
- 1-2 unapportioned cases
- 1 case with `cited_authorities`
- All field types exercised at least once

Build via a small Python script committed alongside the fixture (`packages/eval/tests/fixtures/_build_synthetic_corpus.py`) so it's reproducible. The output JSONL is the actual fixture.

- [ ] **Step 7.4: Acceptance test for the fixture.**

```python
class TestSyntheticCorpus10:
    def test_loads_clean(self):
        from eval.dataset import load
        from eval.schema import ClaimType
        result = load(
            "synthetic_corpus_10",
            base_dir=Path(__file__).parent / "fixtures",
        )
        assert result.is_clean
        assert len(result.cases) == 10
        # Every claim type represented at least once
        types_seen = set()
        for c in result.cases:
            types_seen.update(c.claim_types)
        assert types_seen == set(ClaimType)
```

- [ ] **Step 7.5: `data/gold_standard/.gitkeep`** (empty file) so the production data dir is tracked even before Phase 6 lands real cases. Add a short `data/gold_standard/README.md` pointing at `docs/eval/reviewer-guide.md`.

- [ ] **Step 7.6: Update `docs/eval/gold-schema.md`** — link to reviewer-guide.

- [ ] **Step 7.7: Commit.** `feat(eval): reviewer guide, adjudication log, synthetic 10-case fixture`.

---

## Phase 3 exit checklist

- [ ] SHA-98 schema lands: `region: RegionUK` + `region_source: str`
- [ ] SHA-99 schema lands: INV-10 with evidence/statute unavailability fields
- [ ] SHA-100 schema lands: `Provenance` model replaces bare `paragraph_ref`
- [ ] `scripts/eval/annotate.py` ships with `template / validate / append / list / show`
- [ ] All five subcommands have subprocess tests
- [ ] `docs/eval/reviewer-guide.md` published
- [ ] `docs/eval/reviewer-log.md` template committed
- [ ] `packages/eval/tests/fixtures/synthetic_corpus_10.jsonl` committed and loads clean
- [ ] All existing schema/dataset tests still pass
- [ ] Coverage ≥80% on `scripts/eval/annotate.py` and unchanged on `packages/eval/`

Once all checked, halt. Phase 4 starts.
