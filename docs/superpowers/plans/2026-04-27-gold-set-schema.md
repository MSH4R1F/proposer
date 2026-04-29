# Phase 1 — Gold-Case Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Pydantic v2 `GoldCase` schema (with sub-models, validators, and a round-trip JSON fixture) that every downstream gold-set tool builds on.

**Architecture:** Single new package `packages/eval/` mirroring `packages/rag_engine/` conventions: package-local `tests/` dir, `conftest.py` injecting `packages/` on `sys.path`, package-local `pytest.ini`. Schema lives in `packages/eval/schema.py`. Cross-field invariants enforced by Pydantic v2 model validators. Python 3.9-compatible (no `StrEnum`, no PEP 604 `int | None` at runtime — use `from __future__ import annotations` and `Optional[...]`).

**Tech stack:** Python 3.9.6, Pydantic 2.12.5, pytest 8.4.2 (all already installed in `legal-mediation-system/venv/`).

**Out of scope for Phase 1:** dataset loader, temporal split, CLI, metrics, ablation runner. Each gets its own plan.

---

## File structure

| File | Responsibility |
|---|---|
| `packages/eval/__init__.py` | Re-exports `GoldCase` and the public enums for ergonomic imports |
| `packages/eval/schema.py` | All Pydantic models, enums, validators |
| `packages/eval/tests/__init__.py` | Marker only |
| `packages/eval/tests/conftest.py` | `sys.path` injection (mirrors `rag_engine/tests/conftest.py`); shared fixtures |
| `packages/eval/tests/fixtures/gold_case_minimal.json` | Round-trip fixture — one valid synthetic case |
| `packages/eval/tests/test_schema.py` | All schema validation tests |
| `packages/eval/pytest.ini` | Per-package pytest config (mirrors `packages/rag_engine/pytest.ini`) |
| `docs/eval/gold-schema.md` | Human-readable schema documentation; field semantics, allowed enum values, examples |

No other files are touched.

---

## Schema design (locked before coding)

```python
# Enums
class SchemaVersion(str, Enum):
    V1 = "v1"

class ClaimType(str, Enum):
    CLEANING = "cleaning"
    DAMAGES = "damages"
    DEPOSIT_NON_PROTECTION = "deposit_non_protection"
    DISREPAIR = "disrepair"
    END_OF_TENANCY = "end_of_tenancy"

class CaseSize(str, Enum):
    SMALL = "small"   # total claimed <= £1500
    LARGE = "large"   # total claimed >  £1500

class PartyRole(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    AGENT = "agent"

class Winner(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    SPLIT = "split"

# Sub-models
class Party(BaseModel):
    role: PartyRole
    represented: bool

class Evidence(BaseModel):
    kind: str            # free text: "photo", "invoice", "inspection_report", ...
    description: str
    paragraph_ref: Optional[str] = None  # e.g. "para 12"

class StatutoryReference(BaseModel):
    statute: str         # "Housing Act 2004"
    section: str         # "s.213"
    paragraph_ref: Optional[str] = None

class ClaimedAmount(BaseModel):
    issue: str           # human label, must match an issue in per_issue
    amount_gbp: Decimal  # >= 0
    by_party: PartyRole

class IssueOutcome(BaseModel):
    issue: str           # must match a claimed_amounts.issue (not enforced here, enforced at GoldCase level)
    winner: Winner
    awarded_gbp: Decimal # >= 0

class GroundTruthOutcome(BaseModel):
    overall_winner: Winner
    total_awarded_gbp: Decimal  # >= 0
    per_issue: list[IssueOutcome]  # min length 1

class ReasoningQuote(BaseModel):
    text: str            # min length 1
    paragraph_ref: str   # required — every quote must be locatable

# Top-level
class GoldCase(BaseModel):
    schema_version: SchemaVersion
    case_id: str                     # stable ID, e.g. "FTT-PR-2023-0042"
    decision_date: date              # 2019-01-01..2024-12-31
    region: str                      # e.g. "London", "North West", "Wales"
    case_size: CaseSize
    claim_type: ClaimType
    source_pdf_sha256: str           # 64-char lowercase hex
    ocr_confidence: Optional[float]  # 0..1
    parties: list[Party]             # >= 1 tenant AND >= 1 landlord
    facts: str                       # >= 50 chars
    evidence: list[Evidence]
    statutory_basis: list[StatutoryReference]
    claimed_amounts: list[ClaimedAmount]   # >= 1
    ground_truth_outcome: GroundTruthOutcome
    key_reasoning_quotes: list[ReasoningQuote]  # >= 1
```

**Cross-field invariants (enforced by `@model_validator(mode='after')` on `GoldCase`):**

| ID | Rule |
|---|---|
| INV-1 | `decision_date` between 2019-01-01 and 2024-12-31 inclusive |
| INV-2 | `parties` includes at least one `TENANT` and one `LANDLORD` |
| INV-3 | `ocr_confidence` (if not None) is in `[0.0, 1.0]` |
| INV-4 | `source_pdf_sha256` matches `^[0-9a-f]{64}$` |
| INV-5 | Every `ground_truth_outcome.per_issue[].issue` matches some `claimed_amounts[].issue` |
| INV-6 | `ground_truth_outcome.total_awarded_gbp` equals `sum(per_issue[].awarded_gbp)` (Decimal exact) |
| INV-7 | `case_size == SMALL` iff `sum(claimed_amounts[].amount_gbp) <= 1500` |
| INV-8 | `Decimal` amounts never negative — enforced per-field with `Field(ge=0)` |

INV-6 uses Decimal exact equality (no float fuzziness). INV-7 is a stratification guard so the 30/70 split can be audited from the data alone.

---

## Tasks

### Task 1: Package skeleton + pytest scaffold

**Files:**
- Create: `packages/eval/__init__.py`
- Create: `packages/eval/tests/__init__.py`
- Create: `packages/eval/tests/conftest.py`
- Create: `packages/eval/pytest.ini`

- [ ] **Step 1.1: Write the package `__init__.py` (empty for now; re-exports come at end of task 5)**

```python
# packages/eval/__init__.py
"""Evaluation harness package: gold-set schema, metrics, ablation runner."""
```

- [ ] **Step 1.2: Write `tests/__init__.py` (empty marker)**

```python
# packages/eval/tests/__init__.py
```

- [ ] **Step 1.3: Write `tests/conftest.py` with sys.path injection (mirror rag_engine)**

```python
# packages/eval/tests/conftest.py
"""Pytest config for eval package tests: ensure `packages/` is on sys.path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

- [ ] **Step 1.4: Write `pytest.ini` (mirror rag_engine convention)**

Look at `packages/rag_engine/pytest.ini` first; copy its style. Minimal expected content:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 1.5: Verify pytest discovers the empty test dir without error**

Run: `cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest --collect-only -q`
Expected: `no tests ran`, exit 5 OR exit 0 with `0 collected`. No import errors.

- [ ] **Step 1.6: Commit**

```bash
git add packages/eval/__init__.py packages/eval/tests/__init__.py packages/eval/tests/conftest.py packages/eval/pytest.ini
git commit -m "feat(eval): add package skeleton and pytest scaffold"
```

---

### Task 2: Failing tests for enums + simple sub-models

**Files:**
- Create: `packages/eval/tests/test_schema.py` (initial section)

- [ ] **Step 2.1: Write the failing tests** (cover every enum value + each simple sub-model that has no cross-field rules)

```python
# packages/eval/tests/test_schema.py
"""Tests for the gold-case schema (packages/eval/schema.py)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError


class TestEnums:
    def test_claim_type_values(self):
        from eval.schema import ClaimType
        assert {c.value for c in ClaimType} == {
            "cleaning",
            "damages",
            "deposit_non_protection",
            "disrepair",
            "end_of_tenancy",
        }

    def test_case_size_values(self):
        from eval.schema import CaseSize
        assert {c.value for c in CaseSize} == {"small", "large"}

    def test_party_role_values(self):
        from eval.schema import PartyRole
        assert {c.value for c in PartyRole} == {"tenant", "landlord", "agent"}

    def test_winner_values(self):
        from eval.schema import Winner
        assert {c.value for c in Winner} == {"tenant", "landlord", "split"}

    def test_schema_version_v1_only(self):
        from eval.schema import SchemaVersion
        assert {c.value for c in SchemaVersion} == {"v1"}


class TestParty:
    def test_valid_party(self):
        from eval.schema import Party, PartyRole
        p = Party(role=PartyRole.TENANT, represented=False)
        assert p.role == PartyRole.TENANT and p.represented is False

    def test_unknown_role_rejected(self):
        from eval.schema import Party
        with pytest.raises(ValidationError):
            Party(role="judge", represented=False)


class TestClaimedAmount:
    def test_valid(self):
        from eval.schema import ClaimedAmount, PartyRole
        c = ClaimedAmount(issue="cleaning", amount_gbp=Decimal("250.00"), by_party=PartyRole.LANDLORD)
        assert c.amount_gbp == Decimal("250.00")

    def test_negative_amount_rejected(self):
        from eval.schema import ClaimedAmount, PartyRole
        with pytest.raises(ValidationError):
            ClaimedAmount(issue="cleaning", amount_gbp=Decimal("-1"), by_party=PartyRole.LANDLORD)


class TestReasoningQuote:
    def test_valid(self):
        from eval.schema import ReasoningQuote
        q = ReasoningQuote(text="The deposit was not protected.", paragraph_ref="para 14")
        assert q.paragraph_ref == "para 14"

    def test_paragraph_ref_required(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="x", paragraph_ref=None)  # type: ignore[arg-type]

    def test_empty_text_rejected(self):
        from eval.schema import ReasoningQuote
        with pytest.raises(ValidationError):
            ReasoningQuote(text="", paragraph_ref="para 1")
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_schema.py -v`
Expected: every test errors with `ModuleNotFoundError: No module named 'eval.schema'`.

---

### Task 3: Implement enums + simple sub-models

**Files:**
- Create: `packages/eval/schema.py` (initial section — enums + simple sub-models only)

- [ ] **Step 3.1: Write `schema.py` minimal implementation that makes Task 2 tests pass**

```python
# packages/eval/schema.py
"""Gold-case schema for the evaluation harness.

See docs/eval/gold-schema.md for a human-readable description.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SchemaVersion(str, Enum):
    V1 = "v1"


class ClaimType(str, Enum):
    CLEANING = "cleaning"
    DAMAGES = "damages"
    DEPOSIT_NON_PROTECTION = "deposit_non_protection"
    DISREPAIR = "disrepair"
    END_OF_TENANCY = "end_of_tenancy"


class CaseSize(str, Enum):
    SMALL = "small"
    LARGE = "large"


class PartyRole(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    AGENT = "agent"


class Winner(str, Enum):
    TENANT = "tenant"
    LANDLORD = "landlord"
    SPLIT = "split"


class Party(BaseModel):
    role: PartyRole
    represented: bool


class Evidence(BaseModel):
    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)
    paragraph_ref: Optional[str] = None


class StatutoryReference(BaseModel):
    statute: str = Field(min_length=1)
    section: str = Field(min_length=1)
    paragraph_ref: Optional[str] = None


class ClaimedAmount(BaseModel):
    issue: str = Field(min_length=1)
    amount_gbp: Decimal = Field(ge=0)
    by_party: PartyRole


class IssueOutcome(BaseModel):
    issue: str = Field(min_length=1)
    winner: Winner
    awarded_gbp: Decimal = Field(ge=0)


class ReasoningQuote(BaseModel):
    text: str = Field(min_length=1)
    paragraph_ref: str = Field(min_length=1)
```

- [ ] **Step 3.2: Run Task 2 tests to verify they pass**

Run: `cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/test_schema.py -v`
Expected: all Task 2 tests pass.

- [ ] **Step 3.3: Commit**

```bash
git add packages/eval/schema.py packages/eval/tests/test_schema.py
git commit -m "feat(eval): add enums and leaf models for gold-case schema (TDD)"
```

---

### Task 4: Failing tests for `GroundTruthOutcome` + cross-field invariants

**Files:**
- Modify: `packages/eval/tests/test_schema.py` (append section)

- [ ] **Step 4.1: Append failing tests**

```python
# Append to packages/eval/tests/test_schema.py


class TestGroundTruthOutcome:
    def test_per_issue_must_be_non_empty(self):
        from eval.schema import GroundTruthOutcome, Winner
        with pytest.raises(ValidationError):
            GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("0"),
                per_issue=[],
            )

    def test_total_must_match_sum_of_per_issue(self):
        from eval.schema import GroundTruthOutcome, IssueOutcome, Winner
        with pytest.raises(ValidationError):
            GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("100"),
                per_issue=[
                    IssueOutcome(issue="cleaning", winner=Winner.TENANT, awarded_gbp=Decimal("60")),
                    IssueOutcome(issue="damages", winner=Winner.TENANT, awarded_gbp=Decimal("50")),
                ],
            )

    def test_total_matches_sum_ok(self):
        from eval.schema import GroundTruthOutcome, IssueOutcome, Winner
        gto = GroundTruthOutcome(
            overall_winner=Winner.TENANT,
            total_awarded_gbp=Decimal("110"),
            per_issue=[
                IssueOutcome(issue="cleaning", winner=Winner.TENANT, awarded_gbp=Decimal("60")),
                IssueOutcome(issue="damages", winner=Winner.TENANT, awarded_gbp=Decimal("50")),
            ],
        )
        assert gto.total_awarded_gbp == Decimal("110")
```

- [ ] **Step 4.2: Run failing tests**

Run: `... pytest tests/test_schema.py::TestGroundTruthOutcome -v`
Expected: all three tests fail (ImportError on `GroundTruthOutcome`).

---

### Task 5: Implement `GroundTruthOutcome`

**Files:**
- Modify: `packages/eval/schema.py` (append)

- [ ] **Step 5.1: Append `GroundTruthOutcome`**

```python
# Append to packages/eval/schema.py
from pydantic import model_validator


class GroundTruthOutcome(BaseModel):
    overall_winner: Winner
    total_awarded_gbp: Decimal = Field(ge=0)
    per_issue: list[IssueOutcome] = Field(min_length=1)

    @model_validator(mode="after")
    def _total_matches_sum(self) -> "GroundTruthOutcome":
        s = sum((io.awarded_gbp for io in self.per_issue), start=Decimal("0"))
        if s != self.total_awarded_gbp:
            raise ValueError(
                f"total_awarded_gbp ({self.total_awarded_gbp}) "
                f"!= sum(per_issue.awarded_gbp) ({s})"
            )
        return self
```

- [ ] **Step 5.2: Run Task 4 tests**

Run: `... pytest tests/test_schema.py::TestGroundTruthOutcome -v`
Expected: all three pass.

- [ ] **Step 5.3: Commit**

```bash
git add packages/eval/schema.py packages/eval/tests/test_schema.py
git commit -m "feat(eval): add GroundTruthOutcome with total-matches-sum validator"
```

---

### Task 6: Failing tests for top-level `GoldCase` and INV-1..INV-8

**Files:**
- Modify: `packages/eval/tests/test_schema.py` (append)
- Create: `packages/eval/tests/fixtures/gold_case_minimal.json`

- [ ] **Step 6.1: Write the synthetic round-trip fixture**

`packages/eval/tests/fixtures/gold_case_minimal.json`:

```json
{
  "schema_version": "v1",
  "case_id": "SYNTH-2023-0001",
  "decision_date": "2023-06-15",
  "region": "London",
  "case_size": "small",
  "claim_type": "cleaning",
  "source_pdf_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "ocr_confidence": 0.92,
  "parties": [
    {"role": "tenant", "represented": false},
    {"role": "landlord", "represented": true}
  ],
  "facts": "Tenant occupied flat from 2022-01-01 to 2023-05-31; landlord retained £400 of the £1200 deposit citing carpet cleaning.",
  "evidence": [
    {"kind": "invoice", "description": "Carpet cleaning invoice for £180", "paragraph_ref": "para 7"}
  ],
  "statutory_basis": [
    {"statute": "Housing Act 2004", "section": "s.213", "paragraph_ref": "para 12"}
  ],
  "claimed_amounts": [
    {"issue": "carpet_cleaning", "amount_gbp": "400.00", "by_party": "landlord"}
  ],
  "ground_truth_outcome": {
    "overall_winner": "tenant",
    "total_awarded_gbp": "220.00",
    "per_issue": [
      {"issue": "carpet_cleaning", "winner": "tenant", "awarded_gbp": "220.00"}
    ]
  },
  "key_reasoning_quotes": [
    {"text": "The landlord adduced no evidence beyond a single invoice.", "paragraph_ref": "para 14"}
  ]
}
```

- [ ] **Step 6.2: Append failing tests**

```python
# Append to packages/eval/tests/test_schema.py
import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_minimal() -> dict:
    return json.loads((FIXTURES_DIR / "gold_case_minimal.json").read_text())


class TestGoldCaseRoundTrip:
    def test_minimal_fixture_validates(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_minimal())
        assert gc.case_id == "SYNTH-2023-0001"

    def test_round_trip_json_stable(self):
        from eval.schema import GoldCase
        gc = GoldCase.model_validate(_load_minimal())
        again = GoldCase.model_validate(json.loads(gc.model_dump_json()))
        assert again == gc


class TestGoldCaseInvariants:
    def _base(self) -> dict:
        return _load_minimal()

    def test_inv1_decision_date_in_range(self):
        from eval.schema import GoldCase
        bad = self._base() | {"decision_date": "2018-12-31"}
        with pytest.raises(ValidationError, match="decision_date"):
            GoldCase.model_validate(bad)
        bad2 = self._base() | {"decision_date": "2025-01-01"}
        with pytest.raises(ValidationError, match="decision_date"):
            GoldCase.model_validate(bad2)

    def test_inv2_requires_tenant_and_landlord(self):
        from eval.schema import GoldCase
        bad = self._base() | {"parties": [{"role": "tenant", "represented": False}]}
        with pytest.raises(ValidationError, match="parties"):
            GoldCase.model_validate(bad)

    def test_inv3_ocr_confidence_in_unit_interval(self):
        from eval.schema import GoldCase
        bad = self._base() | {"ocr_confidence": 1.5}
        with pytest.raises(ValidationError, match="ocr_confidence"):
            GoldCase.model_validate(bad)
        bad2 = self._base() | {"ocr_confidence": -0.01}
        with pytest.raises(ValidationError, match="ocr_confidence"):
            GoldCase.model_validate(bad2)
        ok = self._base() | {"ocr_confidence": None}
        GoldCase.model_validate(ok)  # None permitted

    def test_inv4_pdf_sha256_format(self):
        from eval.schema import GoldCase
        bad = self._base() | {"source_pdf_sha256": "ZZZ"}
        with pytest.raises(ValidationError, match="source_pdf_sha256"):
            GoldCase.model_validate(bad)

    def test_inv5_per_issue_must_match_claimed(self):
        from eval.schema import GoldCase
        case = self._base()
        case["ground_truth_outcome"]["per_issue"][0]["issue"] = "ghost_issue"
        with pytest.raises(ValidationError, match="ghost_issue"):
            GoldCase.model_validate(case)

    def test_inv7_case_size_consistent_small(self):
        from eval.schema import GoldCase
        bad = self._base() | {"case_size": "large"}  # but total claimed = £400 -> should be small
        with pytest.raises(ValidationError, match="case_size"):
            GoldCase.model_validate(bad)

    def test_inv7_case_size_consistent_large(self):
        from eval.schema import GoldCase
        case = self._base()
        case["claimed_amounts"][0]["amount_gbp"] = "1600.00"
        case["ground_truth_outcome"]["total_awarded_gbp"] = "220.00"
        case["ground_truth_outcome"]["per_issue"][0]["awarded_gbp"] = "220.00"
        # case_size is still "small" but claimed total is now £1600 -> mismatch
        with pytest.raises(ValidationError, match="case_size"):
            GoldCase.model_validate(case)
```

- [ ] **Step 6.3: Run failing tests**

Run: `... pytest tests/test_schema.py::TestGoldCaseRoundTrip tests/test_schema.py::TestGoldCaseInvariants -v`
Expected: all fail with ImportError on `GoldCase` (or, after import added, with the relevant invariant violation as a *positive* test result — confirm the expected failure mode for each).

---

### Task 7: Implement `GoldCase` with all invariants

**Files:**
- Modify: `packages/eval/schema.py` (append)

- [ ] **Step 7.1: Append `GoldCase`**

```python
# Append to packages/eval/schema.py
import re
from datetime import date

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MIN_DECISION_DATE = date(2019, 1, 1)
_MAX_DECISION_DATE = date(2024, 12, 31)
_SMALL_CASE_THRESHOLD = Decimal("1500")


class GoldCase(BaseModel):
    schema_version: SchemaVersion
    case_id: str = Field(min_length=1)
    decision_date: date
    region: str = Field(min_length=1)
    case_size: CaseSize
    claim_type: ClaimType
    source_pdf_sha256: str
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    parties: list[Party] = Field(min_length=2)
    facts: str = Field(min_length=50)
    evidence: list[Evidence]
    statutory_basis: list[StatutoryReference]
    claimed_amounts: list[ClaimedAmount] = Field(min_length=1)
    ground_truth_outcome: GroundTruthOutcome
    key_reasoning_quotes: list[ReasoningQuote] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_invariants(self) -> "GoldCase":
        if not (_MIN_DECISION_DATE <= self.decision_date <= _MAX_DECISION_DATE):
            raise ValueError(
                f"decision_date {self.decision_date} outside permitted "
                f"window [{_MIN_DECISION_DATE}, {_MAX_DECISION_DATE}]"
            )
        roles = {p.role for p in self.parties}
        if PartyRole.TENANT not in roles or PartyRole.LANDLORD not in roles:
            raise ValueError("parties must include at least one tenant and one landlord")
        if not _SHA256_RE.match(self.source_pdf_sha256):
            raise ValueError(
                f"source_pdf_sha256 must be 64 lowercase hex chars; got {self.source_pdf_sha256!r}"
            )
        claimed_issues = {ca.issue for ca in self.claimed_amounts}
        for io in self.ground_truth_outcome.per_issue:
            if io.issue not in claimed_issues:
                raise ValueError(
                    f"ground_truth_outcome refers to issue {io.issue!r} "
                    f"not present in claimed_amounts {sorted(claimed_issues)}"
                )
        total_claimed = sum(
            (ca.amount_gbp for ca in self.claimed_amounts), start=Decimal("0")
        )
        is_small = total_claimed <= _SMALL_CASE_THRESHOLD
        expected = CaseSize.SMALL if is_small else CaseSize.LARGE
        if self.case_size != expected:
            raise ValueError(
                f"case_size {self.case_size.value!r} inconsistent with "
                f"total_claimed=£{total_claimed} (expected {expected.value!r})"
            )
        return self
```

- [ ] **Step 7.2: Run all schema tests**

Run: `cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/ -v`
Expected: every test passes.

- [ ] **Step 7.3: Update `packages/eval/__init__.py` re-exports**

```python
# packages/eval/__init__.py
"""Evaluation harness package: gold-set schema, metrics, ablation runner."""
from eval.schema import (
    CaseSize,
    ClaimType,
    ClaimedAmount,
    Evidence,
    GoldCase,
    GroundTruthOutcome,
    IssueOutcome,
    Party,
    PartyRole,
    ReasoningQuote,
    SchemaVersion,
    StatutoryReference,
    Winner,
)

__all__ = [
    "CaseSize",
    "ClaimType",
    "ClaimedAmount",
    "Evidence",
    "GoldCase",
    "GroundTruthOutcome",
    "IssueOutcome",
    "Party",
    "PartyRole",
    "ReasoningQuote",
    "SchemaVersion",
    "StatutoryReference",
    "Winner",
]
```

- [ ] **Step 7.4: Coverage check**

Run: `cd packages/eval && /Users/msharif/Documents/Projects/proposer/legal-mediation-system/venv/bin/python -m pytest tests/ --cov=eval.schema --cov-report=term-missing 2>/dev/null` (skip if `pytest-cov` not installed; document in evidence file as a follow-up)

Expected: ≥80% line coverage on `eval/schema.py`. If `pytest-cov` is missing, install via `pip install pytest-cov` (development-only dep) before running and note in commit message.

- [ ] **Step 7.5: Commit**

```bash
git add packages/eval/schema.py packages/eval/__init__.py packages/eval/tests/test_schema.py packages/eval/tests/fixtures/gold_case_minimal.json
git commit -m "feat(eval): GoldCase top-level schema with invariants INV-1..INV-8"
```

---

### Task 8: Schema documentation + Codex sparring stub

**Files:**
- Create: `docs/eval/gold-schema.md`
- Create: `.sisyphus/codex/sha-28-schema-2026-04-27.md` (template — to be filled by Codex sparring session)

- [ ] **Step 8.1: Write `docs/eval/gold-schema.md`**

Document: purpose, file location (`data/gold_standard/housing_v1.jsonl`), field-by-field semantics with allowed values, the eight invariants verbatim, link to fixture, links to SHA-28 / SHA-14 in Linear, and a "schema versioning policy" paragraph (`v1` is frozen once the first reviewer-signed-off case is committed; bump to `v2` on any field change). Include the synthetic fixture inline as an example. Keep under 200 lines.

- [ ] **Step 8.2: Write Codex sparring template**

`.sisyphus/codex/sha-28-schema-2026-04-27.md`:

```markdown
# Codex sparring — SHA-28 schema (2026-04-27)

## Prompt sent to Codex

> Below is the proposed Pydantic v2 gold-case schema for an evaluation harness over UK
> housing-tribunal decisions. Cases are 2019–2024, OCR'd from public PDFs, annotated by a
> paralegal. Eight cross-field invariants are enforced (see INV-1..INV-8). Identify the
> failure modes you would expect this schema to hit under noisy real-world tribunal text.
> Where could an annotator legitimately be unable to produce a valid case? Where is the
> schema too strict? Where is it not strict enough? What field is missing?

[Paste the contents of `packages/eval/schema.py` and `docs/eval/gold-schema.md` here.]

## Codex response

<TO BE FILLED IN AFTER SPARRING SESSION>

## Action items extracted

- [ ] (none yet — fill after sparring)
```

- [ ] **Step 8.3: Commit**

```bash
git add docs/eval/gold-schema.md .sisyphus/codex/sha-28-schema-2026-04-27.md
git commit -m "docs(eval): gold-case schema documentation and Codex sparring template"
```

---

## Phase 1 exit checklist

- [ ] All `tests/test_schema.py` tests pass.
- [ ] `from eval import GoldCase` works (re-exports from `__init__.py`).
- [ ] Synthetic fixture `gold_case_minimal.json` round-trips through `model_validate` → `model_dump_json` → `model_validate` unchanged.
- [ ] Every invariant in INV-1..INV-8 has at least one positive and one negative test.
- [ ] Coverage ≥80% on `packages/eval/schema.py`.
- [ ] Schema doc committed at `docs/eval/gold-schema.md`.
- [ ] Codex sparring template committed (sparring session itself happens in a separate session).
- [ ] All five commits are in `git log`, scoped, conventional-commits style.

Once all checked, halt and request review before starting Phase 2 (dataset loader).
