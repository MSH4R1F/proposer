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

from eval.constants import HOUSING_REPAIRS_MATTER_TYPES
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
    matter_type_distribution: dict = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.leakage_violations and not self.understratified_types

    @property
    def clean_failure_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.leakage_violations:
            reasons.append(
                f"{len(self.leakage_violations)} temporal leakage violation(s)"
            )
        for type_key, count in sorted(
            self.understratified_types.items(), key=lambda item: _key_value(item[0])
        ):
            reasons.append(
                f"{_key_value(type_key)} has {count} case(s), below "
                f"STRATIFICATION_FLOOR={STRATIFICATION_FLOOR}"
            )
        return reasons


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
    matter_counts = Counter(
        getattr(case, "matter_type", None)
        for case in cases
        if getattr(case, "domain_id", None) == "housing.repairs_social.v1"
        and getattr(case, "matter_type", None)
    )
    if matter_counts:
        understratified.update(
            {
                matter_type: matter_counts.get(matter_type, 0)
                for matter_type in HOUSING_REPAIRS_MATTER_TYPES
                if matter_counts.get(matter_type, 0) < STRATIFICATION_FLOOR
            }
        )

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
        matter_type_distribution=dict(matter_counts),
    )


# -- CLI -----------------------------------------------------------------------


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
                f"  - {v.case_id}: cites {v.authority_name!r} dated "
                f"{v.authority_cited_date} (cutoff {v.cutoff})"
            )
    else:
        lines.append("\nleakage violations: none")
    if report.understratified_types:
        lines.append(f"\nunderstratified types (floor {STRATIFICATION_FLOOR}):")
        for t, n in sorted(
            report.understratified_types.items(), key=lambda x: _key_value(x[0])
        ):
            lines.append(f"  - {_key_value(t)}: {n}")
    else:
        lines.append("\nstratification: all types at or above floor")
    lines.append(
        "\nregion_distribution: "
        + str({k.value: v for k, v in report.region_distribution.items()})
    )
    lines.append(
        "case_size_distribution: "
        + str({k.value: v for k, v in report.case_size_distribution.items()})
    )
    if report.matter_type_distribution:
        lines.append(
            "matter_type_distribution: " + str(report.matter_type_distribution)
        )
    lines.append(f"\nis_clean: {report.is_clean}")
    if not report.is_clean:
        lines.append("clean_failure_reasons:")
        for reason in report.clean_failure_reasons:
            lines.append(f"  - {reason}")
    return "\n".join(lines)


def _key_value(key) -> str:
    return str(getattr(key, "value", key))


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
        "understratified_types": {
            _key_value(t): n for t, n in report.understratified_types.items()
        },
        "region_distribution": {k.value: v for k, v in report.region_distribution.items()},
        "case_size_distribution": {
            k.value: v for k, v in report.case_size_distribution.items()
        },
        "matter_type_distribution": report.matter_type_distribution,
        "is_clean": report.is_clean,
        "clean_failure_reasons": report.clean_failure_reasons,
    }


def _cli_main(argv=None) -> int:
    import argparse
    import sys
    from datetime import datetime

    parser = argparse.ArgumentParser(prog="python -m eval.dataset")
    sub = parser.add_subparsers(dest="cmd", required=True)

    audit_p = sub.add_parser("audit", help="Audit a gold-set JSONL file")
    audit_p.add_argument("path", type=Path, help="Path to <version>.jsonl")
    audit_p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if the corpus is not clean",
    )
    audit_p.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_out",
        help="Write the audit report as JSON to PATH",
    )
    audit_p.add_argument(
        "--evidence",
        action="store_true",
        help=(
            "Also write the audit report into "
            ".sisyphus/evidence/eval/audit_<date>.json (cwd-relative)"
        ),
    )

    args = parser.parse_args(argv)

    if args.cmd == "audit":
        version = args.path.stem
        try:
            result = load(version, base_dir=args.path.parent, strict=args.strict)
        except FileNotFoundError as e:
            # SHA-20 Phase 7 / audit D2: a missing gold file MUST fail
            # closed and never be silently substituted with synthetic data.
            print(f"Gold-set file missing (fail-closed): {e}", file=sys.stderr)
            return 1
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"Load error: {e}", file=sys.stderr)
            return 1
        if result.errors:
            print(f"Load errors ({len(result.errors)}):", file=sys.stderr)
            for err in result.errors:
                print(f"  line {err.line_number}: {err.error}", file=sys.stderr)
        report = audit(result.cases)
        print(_format_report(report))
        if args.json_out is not None:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(_report_to_dict(report), indent=2))
        if args.evidence:
            today = datetime.now().strftime("%Y-%m-%d")
            evidence_path = (
                Path.cwd() / ".sisyphus" / "evidence" / "eval" / f"audit_{today}.json"
            )
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(json.dumps(_report_to_dict(report), indent=2))
        if args.strict and (result.errors or not report.is_clean):
            return 1
        return 0

    return 2  # unreachable


if __name__ == "__main__":
    raise SystemExit(_cli_main())
