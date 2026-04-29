"""Gold-set dataset loader and audit for the evaluation harness.

Pure functions over `list[GoldCase]`, plus a thin CLI for CI. Lenient
defaults (skip-and-log) for pilot iteration; `strict=True` opt-in for
production CI gates.

See docs/eval/dataset.md for usage. See packages/eval/schema.py for
GoldCase. See .sisyphus/plans/track-a-plan.md Phase 2 for context.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from eval.schema import CaseSize, ClaimType, GoldCase

_log = logging.getLogger(__name__)

# Cutoff dates per the PILOT methodology (interim report).
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
    cases: list
    errors: list
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
    leakage_violations: list = field(default_factory=list)
    understratified_types: dict = field(default_factory=dict)
    region_distribution: dict = field(default_factory=dict)
    case_size_distribution: dict = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.leakage_violations and not self.understratified_types


def load(
    version: str = "housing_v1",
    *,
    base_dir: Optional[Path] = None,
    strict: bool = False,
) -> LoadResult:
    """Read `<base_dir>/<version>.jsonl`. Validate each line as a `GoldCase`.

    Lenient default: collect parse and validation errors, return the valid
    cases plus the error list. Strict (`strict=True`): re-raise the first
    `json.JSONDecodeError` or `pydantic.ValidationError`.

    `FileNotFoundError` is raised regardless of `strict` when the file is
    missing — there's no graceful interpretation of "the corpus does not
    exist."
    """
    if base_dir is None:
        base_dir = Path.cwd() / "data" / "gold_standard"
    path = base_dir / f"{version}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Gold-set file not found: {path}")

    cases: list = []
    errors: list = []
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
                errors.append(
                    LoadError(
                        line_number=line_number,
                        raw_line=raw.rstrip("\n"),
                        error=str(e),
                    )
                )
                continue
            try:
                cases.append(GoldCase.model_validate(payload))
            except ValidationError as e:
                if strict:
                    raise
                errors.append(
                    LoadError(
                        line_number=line_number,
                        raw_line=raw.rstrip("\n"),
                        error=str(e),
                    )
                )
    return LoadResult(cases=cases, errors=errors, source_path=path)


def _leakage_violations(train_cases: list) -> list:
    """Return all leakage violations in the given pre-filtered train cases."""
    violations: list = []
    for case in train_cases:
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


def train(cases: list, *, strict: bool = False) -> list:
    """Return cases with `decision_date <= TRAIN_CUTOFF`. Run a leakage check
    on the train subset (every `cited_authorities[].cited_date` must be
    `<= TRAIN_CUTOFF`).

    Lenient default: log one warning per violation, return cases anyway.
    Strict (`strict=True`): raise `ValueError` on the first violation.
    """
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


def test(cases: list) -> list:
    """Return cases with `decision_date >= TEST_START`. No audits — test
    cases may cite future-dated authorities by construction (they ARE the
    future relative to the train window)."""
    return [c for c in cases if c.decision_date >= TEST_START]


def audit(cases: list) -> AuditReport:
    """Compute leakage + stratification + region/case-size distribution. Pure.

    No I/O, no side effects — callers decide what to do with the report.
    `AuditReport.is_clean` is True iff there are no leakage violations and
    every `ClaimType` has at least `STRATIFICATION_FLOOR` cases (multi-type
    cases count toward each of their types, per SHA-92).
    """
    train_cases = [c for c in cases if c.decision_date <= TRAIN_CUTOFF]
    test_cases = [c for c in cases if c.decision_date >= TEST_START]

    leakage = _leakage_violations(train_cases)

    type_counts: Counter = Counter()
    for case in cases:
        for t in case.claim_types:
            type_counts[t] += 1
    understratified = {
        t: type_counts.get(t, 0)
        for t in ClaimType
        if type_counts.get(t, 0) < STRATIFICATION_FLOOR
    }

    region_dist: dict = {}
    size_dist: dict = {}
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
