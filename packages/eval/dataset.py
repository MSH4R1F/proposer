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


def train(cases: list, *, strict: bool = False) -> list:
    raise NotImplementedError


def test(cases: list) -> list:
    raise NotImplementedError


def audit(cases: list) -> AuditReport:
    raise NotImplementedError
