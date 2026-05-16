#!/usr/bin/env python3
"""SHA-148 Phase A — stratified selection of ~50 ET unfair-dismissal cases.

Reads the SHA-147 corpus manifest at
``data/eval_artifacts/corpus/employment_et_unfair_dismissal_v1_<date>.jsonl``
and emits a deterministic selection manifest covering:

* country: proportional to corpus (90/10 E&W/Scotland -> 45/5 in n=50)
* decision-date quartile: proportional to the corpus's empirical
  decision-date distribution (corpus is 2023-03 to 2026-04, heavily
  skewed to 2025-2026 — see SHA-147 report §"Recommendation for SHA-148")
* jurisdiction-code breadth: prefer single ``Unfair Dismissal`` cases
  over combined-claims pages so the gold set is mostly "clean" UD
  judgments, with a minority of combined cases for coverage

Output goes to
``data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_<date>/selection_manifest.jsonl``
plus a summary ``.json``.

This script does NOT download PDFs — that's Phase B
(``build_employment_et_unfair_dismissal_pdf_extraction.py``). The
selection manifest is the input to Phase B + Phase C.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

DOMAIN_ID = "employment.et.unfair_dismissal.v1"
COMPAT_DOMAIN_ID = "employment.unfair_dismissal.v1"
FORUM = "employment_tribunal"
SOURCE_PUBLISHER = "govuk"
SOURCE_KIND = "case_decision"
SOURCE_LICENSE_DEFAULT = "OGL-3.0"
RETRIEVAL_NAMESPACE_ID = "employment_unfair_dismissal_v1"
CORPUS_VERSION = "research_seed_2026_05"
MATTER_TYPE = "unfair_dismissal"
SCHEMA_VERSION = "employment_et_unfair_dismissal_eval_manifest_v1"

DEFAULT_SIZE = 50
DEFAULT_SEED = 42

# Country tiers per SHA-147 corpus distribution (897 E&W / 103 Scotland).
COUNTRIES = ("england_and_wales", "scotland")


def _stable_score(seed: int, case_ref: str) -> str:
    """Deterministic per-case sort key for reproducible sampling."""
    return hashlib.sha256(f"{seed}:{case_ref}".encode("utf-8")).hexdigest()


def _is_single_unfair_dismissal(jurisdiction_codes: list[str]) -> bool:
    """True iff the only jurisdiction code is exactly 'Unfair Dismissal'."""
    if not jurisdiction_codes:
        return False
    codes = {c.strip().lower() for c in jurisdiction_codes}
    return codes == {"unfair dismissal"}


def _decision_quartile(d: str | None, edges: list[date]) -> int | None:
    """Return 1-4 for the quartile containing ``d`` (ISO ``YYYY-MM-DD``)."""
    if not d:
        return None
    try:
        dt = date.fromisoformat(d)
    except ValueError:
        return None
    for i, edge in enumerate(edges, start=1):
        if dt <= edge:
            return i
    return len(edges) + 1


def _allocate_proportional(
    counts: Counter[Any], total: int, *, min_per_label: int = 1
) -> dict[Any, int]:
    """Largest-remainder allocation with a floor of ``min_per_label``.

    Labels with zero observations get zero. Total returned equals ``total``.
    """
    labels = [label for label, count in counts.items() if count > 0]
    if total < len(labels) * min_per_label:
        raise ValueError(
            f"sample size {total} too small for {len(labels)} strata "
            f"with floor {min_per_label} each"
        )

    quotas = {label: min_per_label for label in labels}
    remaining = total - sum(quotas.values())
    corpus_total = sum(counts[label] for label in labels)

    exact: dict[Any, float] = {
        label: (remaining * counts[label] / corpus_total) for label in labels
    }
    for label, value in exact.items():
        quotas[label] += int(value)

    allocated = sum(quotas.values())
    leftovers = total - allocated
    ranked = sorted(
        labels,
        key=lambda label: (
            exact[label] - int(exact[label]),
            counts[label],
            str(label),
        ),
        reverse=True,
    )
    for label in ranked[:leftovers]:
        quotas[label] += 1
    return quotas


def _load_corpus_rows(corpus_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with corpus_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _compute_quartile_edges(rows: list[dict[str, Any]]) -> list[date]:
    """Three edges that split the corpus's decision dates into 4 buckets.

    Computed from the empirical sorted-date distribution (each quartile
    holds ~25% of the corpus). Uses date strings as comparable.
    """
    dates = sorted(
        date.fromisoformat(r["decision_date"])
        for r in rows
        if r.get("decision_date")
    )
    n = len(dates)
    if n < 4:
        return []
    q1 = dates[n // 4 - 1]
    q2 = dates[n // 2 - 1]
    q3 = dates[3 * n // 4 - 1]
    return [q1, q2, q3]


def _select_with_jurisdiction_preference(
    rows: list[dict[str, Any]],
    quota: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Pick ``quota`` rows from ``rows`` preferring single-UD cases.

    Sorted by ``(combined_claim_flag, stable_score)`` so single-UD cases
    come first in deterministic order. The seed drives the deterministic
    score so the same input always yields the same output.
    """

    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        is_single = _is_single_unfair_dismissal(row.get("jurisdiction_codes") or [])
        combined_flag = 0 if is_single else 1
        return (combined_flag, _stable_score(seed, row["case_reference"]))

    sorted_rows = sorted(rows, key=sort_key)
    return sorted_rows[:quota]


def build(args: argparse.Namespace) -> None:
    corpus_path = Path(args.corpus_manifest).expanduser()
    if not corpus_path.is_absolute():
        corpus_path = REPO_ROOT / corpus_path
    if not corpus_path.exists():
        raise SystemExit(f"corpus manifest not found: {corpus_path}")

    all_rows = _load_corpus_rows(corpus_path)
    rows = [r for r in all_rows if r.get("decision_date") and r.get("country")]
    missing_meta = len(all_rows) - len(rows)

    # Step 1: country quotas, proportional to corpus.
    country_counts: Counter[str] = Counter(r["country"] for r in rows)
    country_quotas = _allocate_proportional(
        country_counts, args.size, min_per_label=1
    )

    # Step 2: within each country, allocate across decision quartiles.
    quartile_edges = _compute_quartile_edges(rows)
    for r in rows:
        r["_quartile"] = _decision_quartile(r["decision_date"], quartile_edges)
    by_country_quartile: dict[tuple[str, int | None], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_country_quartile[(r["country"], r["_quartile"])].append(r)

    selected: list[dict[str, Any]] = []
    for country in COUNTRIES:
        country_quota = country_quotas.get(country, 0)
        if country_quota == 0:
            continue
        country_rows = [r for r in rows if r["country"] == country]
        quartile_counts: Counter[int | None] = Counter(r["_quartile"] for r in country_rows)
        try:
            quartile_quotas = _allocate_proportional(
                quartile_counts, country_quota, min_per_label=1
            )
        except ValueError:
            # Fall back: too few quartile strata represented; just one bucket.
            quartile_quotas = {None: country_quota}
        for quartile, q_quota in quartile_quotas.items():
            picked = _select_with_jurisdiction_preference(
                by_country_quartile.get((country, quartile), []),
                quota=q_quota,
                seed=args.seed,
            )
            selected.extend(picked)

    # Annotate selected rows with selection context.
    selected.sort(
        key=lambda r: (
            r["country"],
            r["_quartile"] or 0,
            r["decision_date"] or "",
            r["case_reference"],
        )
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        first_pdf = next(
            (
                att for att in (row.get("attachments") or [])
                if (att.get("content_type") or "").startswith("application/pdf")
            ),
            None,
        )
        if first_pdf is None and row.get("attachments"):
            first_pdf = row["attachments"][0]
        is_single_ud = _is_single_unfair_dismissal(row.get("jurisdiction_codes") or [])
        enriched.append(
            {
                "selection_index": index,
                "case_reference": row["case_reference"],
                "target_source_id": row["case_reference"],
                "title": row.get("title"),
                "source_url": row["source_url"],
                "base_path": row.get("base_path"),
                "decision_date": row["decision_date"],
                "country": row["country"],
                "case_numbers": row.get("case_numbers"),
                "jurisdiction_codes": row.get("jurisdiction_codes"),
                "is_single_unfair_dismissal": is_single_ud,
                "first_attachment": first_pdf,
                "strata": {
                    "country": row["country"],
                    "decision_quartile": row["_quartile"],
                    "is_single_unfair_dismissal": is_single_ud,
                },
                # Phase 7 SHA-20 fields for the eventual gold row.
                "domain_id": DOMAIN_ID,
                "compat_domain_id": COMPAT_DOMAIN_ID,
                "forum": FORUM,
                "source_publisher": SOURCE_PUBLISHER,
                "source_kind": SOURCE_KIND,
                "source_license": row.get("source_license_observed") or SOURCE_LICENSE_DEFAULT,
                "retrieval_namespace_id": RETRIEVAL_NAMESPACE_ID,
                "corpus_version": CORPUS_VERSION,
                "matter_type": MATTER_TYPE,
                "annotation_status": "needs_pdf_extraction",
                "selection_seed": args.seed,
                "selection_method": "country_quartile_jurisdiction_round_robin",
                "generated_at": generated_at,
            }
        )

    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = REPO_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in enriched),
        encoding="utf-8",
    )

    summary_output = Path(args.summary_output).expanduser()
    if not summary_output.is_absolute():
        summary_output = REPO_ROOT / summary_output

    selected_country = Counter(r["country"] for r in enriched)
    selected_quartile = Counter(r["strata"]["decision_quartile"] for r in enriched)
    selected_single = Counter(r["strata"]["is_single_unfair_dismissal"] for r in enriched)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "corpus_manifest": str(corpus_path),
        "output": str(output),
        "generated_at": generated_at,
        "selection_seed": args.seed,
        "sample_size": len(enriched),
        "source_cases": len(all_rows),
        "eligible_cases": len(rows),
        "excluded_missing_metadata": missing_meta,
        "country_corpus_counts": dict(sorted(country_counts.items())),
        "country_quotas": dict(sorted(country_quotas.items())),
        "country_selected": dict(sorted(selected_country.items())),
        "quartile_edges": [e.isoformat() for e in quartile_edges],
        "quartile_selected": {
            str(k): v for k, v in sorted(selected_quartile.items(), key=lambda kv: kv[0] or 0)
        },
        "single_unfair_dismissal_selected": {
            str(k): v for k, v in sorted(selected_single.items())
        },
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build the SHA-148 stratified-50 selection manifest for ET unfair-dismissal.",
    )
    p.add_argument(
        "--corpus-manifest",
        default="data/eval_artifacts/corpus/employment_et_unfair_dismissal_v1_2026-05-15.jsonl",
        help="Path to the SHA-147 corpus manifest.",
    )
    p.add_argument("--size", type=int, default=DEFAULT_SIZE)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument(
        "--output",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_manifest.jsonl",
    )
    p.add_argument(
        "--summary-output",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_summary.json",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    build(_parser().parse_args(argv))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
