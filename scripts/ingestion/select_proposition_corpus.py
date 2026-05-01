"""Select a small, diverse corpus of BAILII tribunal decisions for the
proposition KG ingestion pipeline (SHA-36, Task 8).

Reads a BAILII data root (typically ``data/raw/bailii``), validates each
candidate by attempting to load decision text via
:func:`kg_builder.propositions.text_loader.load_decision_text`, applies
char-count filters, then picks ``n`` cases optimizing for year and
case-type diversity. Writes a JSON manifest describing the selection.

CI-safe: when the BAILII root or its case files are missing, the script
exits with code 2 and prints a friendly hint pointing at the scraper.

Usage::

    python -m scripts.ingestion.select_proposition_corpus \\
        --bailii-root data/raw/bailii \\
        --output data/proposition_corpus_v1.json \\
        [--n 5] [--min-chars 1000] [--max-chars 30000]

Exit codes:
  0 — success, manifest written
  1 — unexpected error (uncaught exception)
  2 — bad inputs (missing root, no cases found, no candidates after filter)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Path setup so this module works under ``python -m`` from the repo root.
# Mirrors scripts/migrations/audit_json_stores.py.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "packages"))

# These imports MUST come after sys.path manipulation above.
from kg_builder.propositions.text_loader import (  # noqa: E402
    DecisionTextExtractionError,
    LoadedDecisionText,
    load_decision_text,
)


SCRAPER_HELP_HINT = (
    "Run the BAILII scraper first to populate the data directory:\n"
    "  python -m scripts.scrapers.bailii_scraper --help"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CaseRecord:
    """Normalized representation of a candidate case from any source."""

    case_reference: str
    year: int
    category: str
    case_type_code: Optional[str]
    region_code: Optional[str]
    decision_date: Optional[str]
    pdf_path: Optional[Path]
    html_path: Optional[Path]


@dataclass
class FilteredCase:
    """A candidate that passed the extraction + char-count filter."""

    record: CaseRecord
    used_path: Path
    char_count: int
    extraction_method: str
    skip_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading candidates
# ---------------------------------------------------------------------------


def _resolve_path(raw: object, bailii_root: Path) -> Optional[Path]:
    """Resolve a path string from the source data, returning an absolute Path
    or ``None`` if not provided.

    master_index.json may store paths relative to the repo root, the bailii
    root, or as absolute paths. Try each and fall back to absolute.
    """
    if not raw:
        return None
    if not isinstance(raw, (str, Path)):
        return None
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    # Try bailii_root-relative
    rel = (bailii_root / p).resolve()
    if rel.exists():
        return rel
    # Try repo-root-relative (matches "data/raw/bailii/..." strings)
    repo = (_REPO_ROOT / p).resolve()
    if repo.exists():
        return repo
    # Last resort: return the absolute interpretation; the caller will check
    # .exists() and skip if missing.
    return p if p.is_absolute() else rel


def _record_from_dict(data: dict, bailii_root: Path) -> Optional[CaseRecord]:
    """Build a CaseRecord from a master_index entry or per-case metadata.json.

    Returns ``None`` if essential fields are missing (case_reference, year).
    """
    case_ref = data.get("case_reference")
    year = data.get("year")
    if not case_ref or year is None:
        return None
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        return None

    category_raw = data.get("category", "other")
    if isinstance(category_raw, str):
        category = category_raw.lower()
    else:
        category = str(category_raw).lower()

    return CaseRecord(
        case_reference=str(case_ref),
        year=year_int,
        category=category,
        case_type_code=data.get("case_type_code"),
        region_code=data.get("region_code"),
        decision_date=data.get("decision_date"),
        pdf_path=_resolve_path(data.get("pdf_path"), bailii_root),
        html_path=_resolve_path(data.get("html_path"), bailii_root),
    )


def _load_master_index(bailii_root: Path) -> Optional[list[CaseRecord]]:
    """Try to load <bailii_root>/master_index.json. Returns None if absent."""
    index_path = bailii_root / "master_index.json"
    if not index_path.exists():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"warning: failed to parse {index_path}: {exc}", file=sys.stderr
        )
        return None
    raw_cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(raw_cases, list):
        return None
    out: list[CaseRecord] = []
    for entry in raw_cases:
        if not isinstance(entry, dict):
            continue
        rec = _record_from_dict(entry, bailii_root)
        if rec is not None:
            out.append(rec)
    return out


def _scan_metadata_dirs(bailii_root: Path) -> list[CaseRecord]:
    """Fallback: scan <bailii_root>/{adjacent,other,deposit}-cases/<year>/<ref>/metadata.json."""
    out: list[CaseRecord] = []
    for cat_dir in ("adjacent-cases", "other-cases", "deposit-cases"):
        sub = bailii_root / cat_dir
        if not sub.is_dir():
            continue
        # Pattern: <cat_dir>/<year>/<case_reference>/metadata.json
        for metadata_path in sub.glob("*/*/metadata.json"):
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(
                    f"warning: failed to parse {metadata_path}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(data, dict):
                continue
            # Infer category from the directory name if missing
            data.setdefault(
                "category",
                {
                    "adjacent-cases": "adjacent",
                    "other-cases": "other",
                    "deposit-cases": "deposit",
                }[cat_dir],
            )
            # Infer pdf/html paths from sibling files when not in metadata
            case_dir = metadata_path.parent
            if not data.get("pdf_path"):
                for cand in ("decision.pdf", "decision.txt"):
                    candidate = case_dir / cand
                    if candidate.exists():
                        data["pdf_path"] = str(candidate)
                        break
            if not data.get("html_path"):
                for cand in ("decision.html", "decision.htm"):
                    candidate = case_dir / cand
                    if candidate.exists():
                        data["html_path"] = str(candidate)
                        break
            rec = _record_from_dict(data, bailii_root)
            if rec is not None:
                out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Filtering candidates by extractable text
# ---------------------------------------------------------------------------


def _try_load(path: Optional[Path]) -> Optional[LoadedDecisionText]:
    if path is None:
        return None
    if not path.exists():
        return None
    try:
        return load_decision_text(path)
    except DecisionTextExtractionError:
        return None


def _filter_candidates(
    records: Iterable[CaseRecord],
    *,
    min_chars: int,
    max_chars: int,
    log_skip: list[str],
) -> list[FilteredCase]:
    out: list[FilteredCase] = []
    for rec in records:
        # Prefer PDF; fall back to HTML.
        loaded: Optional[LoadedDecisionText] = None
        used_path: Optional[Path] = None

        # NOTE: also accept .txt fixtures masquerading as pdf_path — the
        # text_loader dispatches by extension, so it will pick the right
        # extractor regardless of which slot the file sits in.
        candidate_paths: list[Path] = []
        for slot in (rec.pdf_path, rec.html_path):
            if slot is not None and slot not in candidate_paths:
                candidate_paths.append(slot)

        for cand in candidate_paths:
            loaded = _try_load(cand)
            if loaded is not None:
                used_path = cand
                break

        if loaded is None or used_path is None:
            log_skip.append(
                f"skip {rec.case_reference}: no extractable file "
                f"(pdf={rec.pdf_path}, html={rec.html_path})"
            )
            continue

        char_count = len(loaded.full_text)
        if char_count < min_chars:
            log_skip.append(
                f"skip {rec.case_reference}: {char_count} chars < min_chars={min_chars}"
            )
            continue
        if char_count > max_chars:
            log_skip.append(
                f"skip {rec.case_reference}: {char_count} chars > max_chars={max_chars}"
            )
            continue

        out.append(
            FilteredCase(
                record=rec,
                used_path=used_path,
                char_count=char_count,
                extraction_method=loaded.extraction_method,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Diversity selection
# ---------------------------------------------------------------------------


_CATEGORY_PRIORITY = {"adjacent": 0, "deposit": 1, "other": 2}


def _category_rank(category: str) -> int:
    return _CATEGORY_PRIORITY.get(category, 99)


def _pick_diverse(
    candidates: list[FilteredCase],
    *,
    n: int,
    target_years: int = 2,
    target_types: int = 3,
) -> tuple[list[FilteredCase], list[str]]:
    """Greedy round-robin pick across years and case_type_code buckets.

    Returns ``(selected, warnings)``. Warnings list is non-empty when the
    diversity targets cannot be met from the available candidates.
    """
    warnings: list[str] = []
    if n <= 0 or not candidates:
        return [], warnings

    # Sort first so the iteration order is deterministic AND prefers the
    # higher-priority category (adjacent before deposit/other) within ties.
    sorted_cands = sorted(
        candidates,
        key=lambda c: (
            _category_rank(c.record.category),
            c.record.case_reference,
        ),
    )

    # Bucket by year, and within each year keep input order so the round
    # robin pulls one from each year before doubling up.
    by_year: "OrderedDict[int, list[FilteredCase]]" = OrderedDict()
    for c in sorted_cands:
        by_year.setdefault(c.record.year, []).append(c)

    # Within each year-bucket, group by case_type_code so we can rotate
    # types as we drain the bucket. Treat missing as "unknown".
    def _split_by_type(items: list[FilteredCase]) -> "OrderedDict[str, list[FilteredCase]]":
        groups: "OrderedDict[str, list[FilteredCase]]" = OrderedDict()
        for it in items:
            key = it.record.case_type_code or "unknown"
            groups.setdefault(key, []).append(it)
        return groups

    year_iters = {
        year: _split_by_type(items) for year, items in by_year.items()
    }

    selected: list[FilteredCase] = []
    seen_refs: set[str] = set()

    # Phase 1: round-robin across years, and within each year rotate types.
    while len(selected) < n:
        progressed = False
        for year, type_groups in year_iters.items():
            if len(selected) >= n:
                break
            # Pick a non-empty type group with the smallest current count of
            # selections from that type (to encourage type diversity).
            type_counts: dict[str, int] = defaultdict(int)
            for s in selected:
                type_counts[s.record.case_type_code or "unknown"] += 1

            chosen_type: Optional[str] = None
            best_count = None
            for type_code, items in type_groups.items():
                if not items:
                    continue
                cnt = type_counts.get(type_code, 0)
                if best_count is None or cnt < best_count:
                    best_count = cnt
                    chosen_type = type_code
            if chosen_type is None:
                continue
            item = type_groups[chosen_type].pop(0)
            if item.record.case_reference in seen_refs:
                continue
            seen_refs.add(item.record.case_reference)
            selected.append(item)
            progressed = True
        if not progressed:
            break

    # Diversity warnings
    distinct_years = {s.record.year for s in selected}
    distinct_types = {s.record.case_type_code or "unknown" for s in selected}
    if len(distinct_years) < target_years and len(by_year) < target_years:
        warnings.append(
            f"diversity: only {len(distinct_years)} distinct year(s) selected "
            f"(target={target_years})"
        )
    elif len(distinct_years) < target_years:
        warnings.append(
            f"diversity: selected {len(distinct_years)} year(s); "
            f"corpus has more but they didn't fit n={n}"
        )

    all_types_in_input = {
        (c.record.case_type_code or "unknown") for c in candidates
    }
    if len(distinct_types) < target_types and len(all_types_in_input) < target_types:
        warnings.append(
            f"diversity: only {len(distinct_types)} distinct case_type_code(s) "
            f"selected (target={target_types})"
        )

    return selected, warnings


# ---------------------------------------------------------------------------
# Manifest emission
# ---------------------------------------------------------------------------


def _emit_manifest(
    selected: list[FilteredCase],
    *,
    bailii_root: Path,
    n: int,
    min_chars: int,
    max_chars: int,
) -> dict:
    cases_out = []
    for s in selected:
        rec = s.record
        cases_out.append(
            OrderedDict(
                [
                    ("case_reference", rec.case_reference),
                    ("year", rec.year),
                    ("category", rec.category),
                    ("case_type_code", rec.case_type_code),
                    ("region_code", rec.region_code),
                    ("decision_date", rec.decision_date),
                    (
                        "pdf_path",
                        str(rec.pdf_path) if rec.pdf_path else None,
                    ),
                    (
                        "html_path",
                        str(rec.html_path) if rec.html_path else None,
                    ),
                    ("char_count", s.char_count),
                    ("extraction_method", s.extraction_method),
                ]
            )
        )

    return OrderedDict(
        [
            ("manifest_version", "v1"),
            ("selected_at", datetime.now(timezone.utc).isoformat()),
            ("bailii_root", str(bailii_root)),
            (
                "criteria",
                OrderedDict(
                    [
                        ("n", n),
                        ("min_chars", min_chars),
                        ("max_chars", max_chars),
                    ]
                ),
            ),
            ("cases", cases_out),
        ]
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _print_missing_root_help(path: Path) -> None:
    print(
        f"error: BAILII root not found: {path}\n\n{SCRAPER_HELP_HINT}",
        file=sys.stderr,
    )


def _print_no_cases_help(path: Path) -> None:
    print(
        f"error: no cases found under {path} (no master_index.json and no "
        f"per-case metadata.json files).\n\n{SCRAPER_HELP_HINT}",
        file=sys.stderr,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="select_proposition_corpus",
        description="Pick a small diverse corpus of BAILII decisions for the "
        "proposition KG ingestion pipeline.",
    )
    parser.add_argument(
        "--bailii-root",
        type=Path,
        default=Path("data/raw/bailii"),
        help="Path to the BAILII data directory (default: data/raw/bailii).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to write the manifest JSON.",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of cases to select (default: 5).",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=1000,
        help="Minimum extracted character count (default: 1000).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=30000,
        help="Maximum extracted character count (default: 30000).",
    )

    args = parser.parse_args(argv)
    bailii_root: Path = args.bailii_root

    # 1. Validate bailii root exists.
    if not bailii_root.exists() or not bailii_root.is_dir():
        _print_missing_root_help(bailii_root)
        return 2

    # 2. Load case records: master_index first, then fallback scan.
    records = _load_master_index(bailii_root)
    if records is None:
        records = _scan_metadata_dirs(bailii_root)

    if not records:
        _print_no_cases_help(bailii_root)
        return 2

    # 3. Filter candidates by extractable text + char-count window.
    skip_log: list[str] = []
    candidates = _filter_candidates(
        records,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        log_skip=skip_log,
    )
    for line in skip_log:
        print(line, file=sys.stderr)

    if not candidates:
        print(
            f"error: no candidates survived filtering "
            f"(min_chars={args.min_chars}, max_chars={args.max_chars}). "
            f"Inspect the skip log above.",
            file=sys.stderr,
        )
        return 2

    # 4. Pick diverse subset.
    selected, warnings = _pick_diverse(candidates, n=args.n)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    if not selected:
        print(
            "error: diversity selection returned no cases.", file=sys.stderr
        )
        return 2

    # 5. Emit manifest.
    manifest = _emit_manifest(
        selected,
        bailii_root=bailii_root,
        n=args.n,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote manifest with {len(selected)} cases to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover — defensive top-level guard
        print(f"unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
