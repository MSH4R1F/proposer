#!/usr/bin/env python3
"""Build a deterministic 50-case Housing Ombudsman eval manifest.

The output is an eval *selection* manifest, not a fully adjudicated GoldCase
file. It records the source documents that should be labelled/reviewed next
and preserves the strata used to sample them from the 1,000-case scrape.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_ID = "housing.repairs_social.v1"
FORUM = "housing_ombudsman"
SOURCE_PUBLISHER = "housing_ombudsman"
SOURCE_KIND = "ombudsman_determination"
SOURCE_LICENSE = "unknown_housing_ombudsman_decisions_permission_pending"
RETRIEVAL_NAMESPACE_ID = "housing_repairs_social_v1"
CORPUS_VERSION = "research_seed_2026_05"
SCHEMA_VERSION = "housing_ombudsman_eval_manifest_v1"
DEFAULT_SIZE = 50
DEFAULT_SEED = 42

MATTER_PRIORITY = (
    "repairs_damp_mould",
    "repairs_disrepair",
    "complaint_handling_failure",
)


def _resolve_data_dir(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    env_value = os.getenv("DATA_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()
    if (REPO_ROOT / "raw" / "housing_ombudsman").exists():
        return REPO_ROOT
    return REPO_ROOT / "data"


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def _primary_matter_type(matter_types: list[str]) -> str:
    for matter_type in MATTER_PRIORITY:
        if matter_type in matter_types:
            return matter_type
    return matter_types[0] if matter_types else "unknown"


def _stable_score(seed: int, case_id: str) -> str:
    return hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()


def _allocate_quotas(counts: Counter[str], total: int) -> dict[str, int]:
    labels = [label for label, count in counts.items() if count > 0]
    if total < len(labels):
        raise ValueError(
            f"sample size {total} is smaller than non-empty strata {len(labels)}"
        )

    quotas = {label: 1 for label in labels}
    remaining = total - len(labels)
    corpus_total = sum(counts[label] for label in labels)

    exact: dict[str, float] = {
        label: (remaining * counts[label] / corpus_total) for label in labels
    }
    for label, value in exact.items():
        quotas[label] += int(value)

    allocated = sum(quotas.values())
    leftovers = total - allocated
    ranked_remainders = sorted(
        labels,
        key=lambda label: (
            exact[label] - int(exact[label]),
            counts[label],
            label,
        ),
        reverse=True,
    )
    for label in ranked_remainders[:leftovers]:
        quotas[label] += 1

    return quotas


def _allocate_balanced_quotas(counts: Counter[str], total: int) -> dict[str, int]:
    """Near-balance outcome strata for a harder evaluation set."""
    labels = sorted(label for label, count in counts.items() if count > 0)
    if total < len(labels):
        raise ValueError(
            f"sample size {total} is smaller than non-empty strata {len(labels)}"
        )

    quotas = {label: 0 for label in labels}
    allocated = 0
    while allocated < total:
        progressed = False
        for label in labels:
            if allocated >= total:
                break
            if quotas[label] >= counts[label]:
                continue
            quotas[label] += 1
            allocated += 1
            progressed = True
        if not progressed:
            break

    if allocated < total:
        raise ValueError(
            f"could only allocate {allocated} cases from available strata; "
            f"requested {total}"
        )
    return quotas


def _select_with_matter_diversity(
    candidates: list[dict[str, Any]],
    quota: int,
    *,
    seed: int,
) -> list[dict[str, Any]]:
    by_matter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_matter[row["primary_matter_type"]].append(row)

    for rows in by_matter.values():
        rows.sort(key=lambda row: _stable_score(seed, row["target_source_id"]))

    matter_order = sorted(
        by_matter,
        key=lambda matter: (len(by_matter[matter]), matter),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    while len(selected) < quota and matter_order:
        next_order: list[str] = []
        for matter in matter_order:
            rows = by_matter[matter]
            if rows and len(selected) < quota:
                selected.append(rows.pop(0))
            if rows:
                next_order.append(matter)
        matter_order = next_order

    return selected


def _load_rows(data_dir: Path) -> list[dict[str, Any]]:
    raw_root = data_dir / "raw" / "housing_ombudsman"
    master_path = raw_root / "master_index.json"
    if not master_path.exists():
        raise FileNotFoundError(f"master index not found: {master_path}")

    master = json.loads(master_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []

    for source_slug, entry in sorted(master.items()):
        if not entry.get("kept"):
            continue

        storage_path = Path(entry["raw_storage_path"])
        parsed_path = storage_path / "parsed.json"
        raw_text_path = storage_path / "raw.txt"
        if not parsed_path.exists() or not raw_text_path.exists():
            continue

        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        raw_text = raw_text_path.read_text(encoding="utf-8")
        case_reference = str(parsed.get("case_reference") or source_slug)
        matter_types = list(entry.get("matter_types") or [])
        outcome = str(parsed.get("outcome_normalized") or "unknown")

        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "case_id": f"housing-ombudsman-{case_reference}",
                "target_source_id": case_reference,
                "source_slug": source_slug,
                "domain_id": DOMAIN_ID,
                "forum": FORUM,
                "source_publisher": SOURCE_PUBLISHER,
                "source_kind": SOURCE_KIND,
                "source_license": SOURCE_LICENSE,
                "retrieval_namespace_id": RETRIEVAL_NAMESPACE_ID,
                "corpus_version": CORPUS_VERSION,
                "train_test_split": "test",
                "annotation_status": "needs_gold_labeling",
                "decision_date": parsed.get("decision_date")
                or entry.get("decision_date"),
                "title": parsed.get("title"),
                "landlord_name": parsed.get("landlord_name"),
                "source_url": parsed.get("source_url") or entry.get("source_url"),
                "source_storage_path": _relative(storage_path, data_dir),
                "parsed_json_path": _relative(parsed_path, data_dir),
                "raw_text_path": _relative(raw_text_path, data_dir),
                "raw_text_sha256": hashlib.sha256(
                    raw_text.encode("utf-8")
                ).hexdigest(),
                "content_sha256": entry.get("content_sha256"),
                "raw_text_chars": len(raw_text),
                "matter_types": matter_types,
                "primary_matter_type": _primary_matter_type(matter_types),
                "outcome_raw": parsed.get("outcome_raw"),
                "outcome_normalized": outcome,
                "strata": {
                    "outcome_normalized": outcome,
                    "primary_matter_type": _primary_matter_type(matter_types),
                },
            }
        )

    return rows


def build(args: argparse.Namespace) -> None:
    data_dir = _resolve_data_dir(args.data_dir)
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = REPO_ROOT / output

    summary_output = Path(args.summary_output).expanduser()
    if not summary_output.is_absolute():
        summary_output = REPO_ROOT / summary_output

    all_rows = _load_rows(data_dir)
    missing_decision_date = [
        row for row in all_rows if not row.get("decision_date")
    ]
    rows = [row for row in all_rows if row.get("decision_date")]
    outcome_counts = Counter(row["outcome_normalized"] for row in rows)
    if args.allocation == "balanced_outcome":
        quotas = _allocate_balanced_quotas(outcome_counts, args.size)
    else:
        quotas = _allocate_quotas(outcome_counts, args.size)

    by_outcome: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_outcome[row["outcome_normalized"]].append(row)

    selected: list[dict[str, Any]] = []
    for outcome in sorted(quotas):
        selected.extend(
            _select_with_matter_diversity(
                by_outcome[outcome],
                quotas[outcome],
                seed=args.seed,
            )
        )

    selected.sort(
        key=lambda row: (
            row["outcome_normalized"],
            row["primary_matter_type"],
            row["decision_date"] or "",
            row["target_source_id"],
        )
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    for index, row in enumerate(selected, start=1):
        row["selection_index"] = index
        row["selection_seed"] = args.seed
        row["selection_method"] = f"{args.allocation}_matter_round_robin"
        row["generated_at"] = generated_at

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected),
        encoding="utf-8",
    )

    selected_outcomes = Counter(row["outcome_normalized"] for row in selected)
    selected_matters = Counter(row["primary_matter_type"] for row in selected)
    dates = sorted(row["decision_date"] for row in rows if row["decision_date"])
    summary = {
        "schema_version": SCHEMA_VERSION,
        "data_dir": str(data_dir),
        "source_master_index": str(
            data_dir / "raw" / "housing_ombudsman" / "master_index.json"
        ),
        "output": str(output),
        "generated_at": generated_at,
        "selection_seed": args.seed,
        "allocation_strategy": args.allocation,
        "sample_size": len(selected),
        "source_cases": len(all_rows),
        "eligible_cases": len(rows),
        "excluded_missing_decision_date": len(missing_decision_date),
        "decision_date_min": dates[0] if dates else None,
        "decision_date_max": dates[-1] if dates else None,
        "source_outcome_counts": dict(sorted(outcome_counts.items())),
        "allocated_outcome_quotas": dict(sorted(quotas.items())),
        "selected_outcome_counts": dict(sorted(selected_outcomes.items())),
        "selected_primary_matter_counts": dict(sorted(selected_matters.items())),
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a stratified Housing Ombudsman eval manifest."
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Base directory containing raw/housing_ombudsman. Defaults to DATA_DIR.",
    )
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--allocation",
        choices=("proportional_outcome", "balanced_outcome"),
        default="proportional_outcome",
        help=(
            "Outcome quota strategy. proportional_outcome mirrors corpus "
            "prevalence; balanced_outcome oversamples rare negative/edge "
            "outcomes for a harder eval set."
        ),
    )
    parser.add_argument(
        "--output",
        default="data/eval/housing_ombudsman_stratified_50.jsonl",
    )
    parser.add_argument(
        "--summary-output",
        default="data/eval/housing_ombudsman_stratified_50_summary.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build(_parser().parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
