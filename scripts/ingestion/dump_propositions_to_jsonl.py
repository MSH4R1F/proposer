"""Stream C — dump LLM-extracted propositions to JSONL.

Thin wrapper around ``scripts.ingestion.ingest_propositions`` that:

  1. Reads an eval-corpus JSONL (e.g. the strict-clean gold corpus or the
     stratified-50 manifest) — each row carries a ``case_id`` and a
     ``raw_text_path`` pointing at the full case text on disk.
  2. Synthesises the proposition-corpus manifest shape that
     ``ingest_propositions`` expects (``{"cases": [...]}`` with
     ``case_reference``, ``pdf_path`` etc.).
  3. Invokes ``ingest_propositions.main_async`` with ``--dry-run`` and the
     newly-added ``--output-jsonl`` flag, so propositions are captured
     to JSONL but never persisted to Postgres.

Why a wrapper, not a fork? The existing ``ingest_propositions.py``
already has the LLM extraction loop, the chunking logic, the per-case
metrics reporting, and the resume/retry semantics. Reusing it (via the
``--output-jsonl`` flag added on the same branch) keeps the surface area
minimal and means a future Postgres-backed run is the same code path.

Eval-corpus rows look like::

    {
      "case_id": "housing-ombudsman-202451564",
      "raw_text_path": "raw/housing_ombudsman/decisions/.../raw.txt",
      "decision_date": "2025-10-23",
      "domain_id": "housing.repairs_social.v1",
      ...
    }

After translation::

    {
      "case_reference": "housing-ombudsman-202451564",
      "year": 2025,
      "category": "housing.repairs_social.v1",
      "case_type_code": null,
      "region_code": null,
      "decision_date": "2025-10-23",
      "pdf_path": "<absolute path>/raw/.../raw.txt",
      "html_path": null
    }

CLI examples (engineering only — no actual LLM run yet)::

    # Preview the synthesised manifest (no LLM, no DB):
    python scripts/ingestion/dump_propositions_to_jsonl.py \\
        --eval-corpus data/eval/housing_ombudsman_stratified_50.jsonl \\
        --output data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.jsonl \\
        --print-manifest-only

    # Real run (requires LLM key OR --mock-response):
    python scripts/ingestion/dump_propositions_to_jsonl.py \\
        --eval-corpus data/eval/housing_ombudsman_stratified_50.jsonl \\
        --output data/eval_artifacts/propositions/housing_repairs_social_v1.propositions.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap so this module works under ``python -m`` and as a script.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "packages"))


def _read_eval_corpus(path: Path) -> List[Dict[str, Any]]:
    """Read an eval-manifest JSONL file. One row per line.

    Empty lines are skipped. Malformed JSON raises ValueError so corrupt
    inputs fail loudly.
    """
    if not path.exists():
        raise FileNotFoundError(f"eval-corpus JSONL not found: {path}")
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_no}: invalid JSON in eval corpus: {exc}"
                ) from exc
    return rows


def _resolve_text_path(row: Dict[str, Any], data_root: Path) -> Optional[Path]:
    """Resolve a row's ``raw_text_path`` relative to ``data_root``.

    Returns ``None`` if the field is missing or the file does not exist
    on disk — caller decides whether to skip or error.
    """
    raw = row.get("raw_text_path")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (data_root / p).resolve()
    return p if p.exists() else None


def _row_year(row: Dict[str, Any]) -> Optional[int]:
    decision_date = row.get("decision_date")
    if isinstance(decision_date, str) and len(decision_date) >= 4:
        try:
            return int(decision_date[:4])
        except ValueError:
            return None
    return row.get("year")


def build_manifest(
    eval_rows: List[Dict[str, Any]],
    *,
    data_root: Path,
    case_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Translate eval-corpus rows into the proposition-corpus manifest shape.

    Args:
        eval_rows: List of eval-manifest dicts (one per JSONL row).
        data_root: Root for resolving relative ``raw_text_path`` values.
        case_ids: Optional whitelist; rows whose ``case_id`` isn't in this
            set are dropped. ``None`` keeps every row.

    Returns:
        A dict ``{"manifest_version": "v1", "cases": [...]}`` ready to
        feed into ``scripts.ingestion.ingest_propositions``.
    """
    wanted = set(case_ids) if case_ids else None
    cases: List[Dict[str, Any]] = []
    for row in eval_rows:
        case_id = row.get("case_id")
        if not case_id:
            continue
        if wanted is not None and case_id not in wanted:
            continue
        text_path = _resolve_text_path(row, data_root)
        if text_path is None:
            continue
        cases.append(
            {
                "case_reference": case_id,
                "year": _row_year(row),
                "category": row.get("domain_id") or "unknown",
                "case_type_code": row.get("primary_matter_type"),
                "region_code": None,
                "decision_date": row.get("decision_date"),
                "pdf_path": str(text_path),
                "html_path": None,
                "source_url": row.get("source_url"),
            }
        )
    return {"manifest_version": "v1", "cases": cases}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dump_propositions_to_jsonl",
        description=(
            "Run the proposition extractor against an eval-corpus JSONL "
            "and dump the extracted Proposition records to a JSONL file. "
            "Wraps scripts.ingestion.ingest_propositions in --dry-run + "
            "--output-jsonl mode."
        ),
    )
    p.add_argument(
        "--eval-corpus",
        type=Path,
        required=True,
        help=(
            "Path to an eval-corpus JSONL "
            "(e.g. data/eval/housing_ombudsman_stratified_50.jsonl)."
        ),
    )
    p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSONL path; one Proposition per line.",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=_REPO_ROOT / "data",
        help=(
            "Root for resolving relative raw_text_path values. "
            "Defaults to <repo>/data."
        ),
    )
    p.add_argument(
        "--case-ids",
        type=str,
        default=None,
        help=(
            "Comma-separated whitelist of case_ids. When omitted, every "
            "row in the eval-corpus JSONL is processed."
        ),
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N matching cases.",
    )
    p.add_argument(
        "--mock-response",
        type=Path,
        default=None,
        help=(
            "Path to a mock LLM fixture (same format as "
            "ingest_propositions). Use for engineering smoke tests so no "
            "real LLM is invoked."
        ),
    )
    p.add_argument(
        "--print-manifest-only",
        action="store_true",
        help=(
            "Print the synthesised proposition-corpus manifest as JSON to "
            "stdout and exit without invoking the extractor. Useful for "
            "verifying corpus selection before paying for an LLM run."
        ),
    )
    p.add_argument(
        "--max-chars-per-chunk",
        type=int,
        default=12000,
        help="Forwarded to ingest_propositions.",
    )
    p.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Forwarded to ingest_propositions.",
    )
    p.add_argument(
        "--jsonl-report",
        type=Path,
        default=None,
        help="Forwarded to ingest_propositions for per-case metrics.",
    )
    p.add_argument(
        "--append",
        action="store_true",
        help=(
            "Do NOT delete the output file before running. Default is to "
            "wipe an existing output file so duplicates aren't appended "
            "across reruns."
        ),
    )
    return p


async def _run_ingest(
    *,
    manifest_path: Path,
    output_jsonl: Path,
    mock_response: Optional[Path],
    limit: Optional[int],
    max_chars_per_chunk: int,
    min_confidence: float,
    jsonl_report: Optional[Path],
) -> int:
    """Invoke ingest_propositions.main_async in --dry-run + --output-jsonl mode."""
    from scripts.ingestion.ingest_propositions import main_async  # noqa: PLC0415

    argv: List[str] = [
        "--manifest",
        str(manifest_path),
        "--dry-run",
        "--output-jsonl",
        str(output_jsonl),
        "--max-chars-per-chunk",
        str(max_chars_per_chunk),
        "--min-confidence",
        str(min_confidence),
    ]
    if mock_response is not None:
        argv.extend(["--mock-response", str(mock_response)])
    if limit is not None:
        argv.extend(["--decisions", str(limit)])
    if jsonl_report is not None:
        argv.extend(["--jsonl-report", str(jsonl_report)])

    return await main_async(argv)


async def main_async(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        eval_rows = _read_eval_corpus(args.eval_corpus.resolve())
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    case_ids = (
        [s.strip() for s in args.case_ids.split(",") if s.strip()]
        if args.case_ids
        else None
    )

    manifest = build_manifest(
        eval_rows,
        data_root=args.data_root.resolve(),
        case_ids=case_ids,
    )
    if args.limit is not None:
        manifest["cases"] = manifest["cases"][: args.limit]

    if args.print_manifest_only:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if not manifest["cases"]:
        print(
            "error: no eligible cases — check --eval-corpus, --case-ids, "
            "and that raw_text_path values exist on disk under --data-root",
            file=sys.stderr,
        )
        return 2

    # Reset the output file unless --append was requested. _emit_propositions_jsonl
    # in ingest_propositions APPENDS, so re-running on the same path would
    # otherwise duplicate every line.
    output_path = args.output.resolve()
    if output_path.exists() and not args.append:
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Synthesise a manifest tmp file next to the output JSONL so the path
    # is stable across reruns (good for debugging) without polluting the
    # repo tree.
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8"
    )

    return await _run_ingest(
        manifest_path=manifest_path,
        output_jsonl=output_path,
        mock_response=args.mock_response,
        limit=args.limit,
        max_chars_per_chunk=args.max_chars_per_chunk,
        min_confidence=args.min_confidence,
        jsonl_report=args.jsonl_report,
    )


def main(argv: Optional[List[str]] = None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
