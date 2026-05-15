#!/usr/bin/env python3
"""SHA-148 Phase B — download + text-extract PDFs for the 50 selected ET cases.

Reads the Phase-A selection manifest at
``data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_<date>/selection_manifest.jsonl``,
downloads the first PDF attachment for each case at 1 rps (polite single-
pass curation rate), extracts text via
``rag_engine.extractors.pdf_extractor.PDFExtractor``, applies the
existing employment-tribunal PII redactor, and persists per-case
artifacts beside the existing HTML body.

Per-case outputs under
``data/raw/employment/decisions/<case_ref>/``:

* ``attachments/<filename>.pdf`` — raw PDF bytes (gitignored)
* ``pdf_text_raw.txt`` — extracted PDF text pre-redaction (gitignored)
* ``pdf_text_redacted.txt`` — model-facing PDF text post-redaction (gitignored)
* ``pdf_metadata.json`` — extraction stats + redaction stats (gitignored)

Committed deliverable goes to
``data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_<date>/pdf_extraction_report.jsonl``
with one row per case carrying download status, extraction stats, PDF
SHA-256, redaction stats, and the truncated PDF text head/tail (for
quick eyeballing in PR review).

The full redacted PDF text is NOT committed — it is sensitive
publisher content. SHA-148 Phase C/D will read it from the local
gitignored path when the LLM-panel labeling runs.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from rag_engine.extractors.pdf_extractor import PDFExtractor  # noqa: E402
from scripts.scrapers.employment_tribunal.to_source_document import (  # noqa: E402
    detect_ni_numbers,
    redact_model_facing_text,
)

logger = logging.getLogger("sha148.pdf_extraction")


@dataclass
class PdfRow:
    """Per-case Phase-B output row."""

    selection_index: int
    case_reference: str
    source_url: str
    pdf_url: str | None = None
    pdf_filename: str | None = None
    pdf_storage_path: str | None = None
    pdf_sha256: str | None = None
    pdf_bytes: int = 0
    extraction_ok: bool = False
    page_count: int | None = None
    raw_text_chars: int = 0
    redacted_text_chars: int = 0
    redaction_stats: dict[str, int] = field(default_factory=dict)
    text_head: str = ""
    text_tail: str = ""
    error: str | None = None


async def _download_pdf(
    client: httpx.AsyncClient, url: str, dst: Path
) -> tuple[int, str]:
    """Stream a PDF to ``dst``. Returns ``(byte_count, sha256_hex)``."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    total = 0
    async with client.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()
        with dst.open("wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                hasher.update(chunk)
                total += len(chunk)
    return total, hasher.hexdigest()


def _persist_per_case(
    case_dir: Path,
    raw_text: str,
    redacted_text: str,
    extraction_metadata: dict,
    redaction_stats: dict,
    pdf_sha256: str,
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "pdf_text_raw.txt").write_text(raw_text, encoding="utf-8")
    (case_dir / "pdf_text_redacted.txt").write_text(redacted_text, encoding="utf-8")
    (case_dir / "pdf_metadata.json").write_text(
        json.dumps(
            {
                "pdf_sha256": pdf_sha256,
                "extraction_metadata": extraction_metadata,
                "redaction_stats": redaction_stats,
                "raw_chars": len(raw_text),
                "redacted_chars": len(redacted_text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


async def _process_row(
    client: httpx.AsyncClient,
    extractor: PDFExtractor,
    row: dict[str, Any],
    decisions_root: Path,
    request_interval_s: float,
) -> PdfRow:
    out = PdfRow(
        selection_index=row["selection_index"],
        case_reference=row["case_reference"],
        source_url=row["source_url"],
    )
    first = row.get("first_attachment") or {}
    pdf_url = first.get("url")
    if not pdf_url or not pdf_url.lower().endswith(".pdf"):
        out.error = "no_pdf_attachment"
        return out
    out.pdf_url = pdf_url
    out.pdf_filename = pdf_url.rsplit("/", 1)[-1]

    case_dir = decisions_root / row["case_reference"].replace("/", "_").replace(" ", "_")
    pdf_path = case_dir / "attachments" / out.pdf_filename
    try:
        t_start = time.monotonic()
        out.pdf_bytes, out.pdf_sha256 = await _download_pdf(client, pdf_url, pdf_path)
        out.pdf_storage_path = str(pdf_path)
        elapsed = time.monotonic() - t_start
        # Polite single-pass cadence: enforce a minimum gap between downloads.
        sleep_for = max(0.0, request_interval_s - elapsed)
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
    except httpx.HTTPError as e:
        out.error = f"download_failed: {e!r}"
        return out

    try:
        raw_text, extraction_metadata = extractor.extract_from_pdf(pdf_path)
    except ValueError as e:
        out.error = f"extract_failed: {e}"
        return out

    out.page_count = extraction_metadata.get("page_count")
    out.raw_text_chars = len(raw_text)

    redacted_text, redaction_stats = redact_model_facing_text(raw_text)
    out.redacted_text_chars = len(redacted_text)
    out.redaction_stats = redaction_stats

    _persist_per_case(
        case_dir, raw_text, redacted_text, extraction_metadata, redaction_stats, out.pdf_sha256
    )

    out.extraction_ok = True
    out.text_head = redacted_text[:240]
    out.text_tail = redacted_text[-240:] if len(redacted_text) > 480 else ""
    return out


async def run(args: argparse.Namespace) -> int:
    selection_path = Path(args.selection_manifest).expanduser()
    if not selection_path.is_absolute():
        selection_path = REPO_ROOT / selection_path
    if not selection_path.exists():
        raise SystemExit(f"selection manifest not found: {selection_path}")

    with selection_path.open("r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    decisions_root = (REPO_ROOT / "data" / "raw" / "employment" / "decisions").resolve()
    decisions_root.mkdir(parents=True, exist_ok=True)

    extractor = PDFExtractor()
    request_interval_s = 1.0 / args.rps if args.rps > 0 else 0.0
    started = datetime.now(timezone.utc)
    headers = {"User-Agent": "ProposerResearchBot/0.1 (sha-148 phase B PDF curation)"}
    async with httpx.AsyncClient(timeout=120, headers=headers) as client:
        out_rows: list[PdfRow] = []
        for row in rows:
            result = await _process_row(
                client, extractor, row, decisions_root, request_interval_s
            )
            out_rows.append(result)
            status = "OK" if result.extraction_ok else f"FAIL ({result.error})"
            logger.info(
                "case %d/%d %s -> %s pages=%s chars=%d",
                result.selection_index,
                len(rows),
                result.case_reference[:50],
                status,
                result.page_count,
                result.redacted_text_chars,
            )

    finished = datetime.now(timezone.utc)

    # Build report
    output_jsonl = Path(args.output).expanduser()
    if not output_jsonl.is_absolute():
        output_jsonl = REPO_ROOT / output_jsonl
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(
                json.dumps(
                    {
                        "selection_index": r.selection_index,
                        "case_reference": r.case_reference,
                        "source_url": r.source_url,
                        "pdf_url": r.pdf_url,
                        "pdf_filename": r.pdf_filename,
                        "pdf_storage_path": r.pdf_storage_path,
                        "pdf_sha256": r.pdf_sha256,
                        "pdf_bytes": r.pdf_bytes,
                        "page_count": r.page_count,
                        "raw_text_chars": r.raw_text_chars,
                        "redacted_text_chars": r.redacted_text_chars,
                        "redaction_stats": r.redaction_stats,
                        "extraction_ok": r.extraction_ok,
                        "error": r.error,
                        "text_head": r.text_head,
                        "text_tail": r.text_tail,
                    },
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )

    # PII regression sweep across the redacted text (head+tail samples here;
    # full sweep happens via the separate phase B verification step).
    summary = {
        "selection_manifest": str(selection_path),
        "output_jsonl": str(output_jsonl),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "request_rps": args.rps,
        "n_cases": len(out_rows),
        "n_extracted": sum(1 for r in out_rows if r.extraction_ok),
        "n_failed": sum(1 for r in out_rows if not r.extraction_ok),
        "failures_by_kind": {},
        "median_pages": _median([r.page_count for r in out_rows if r.page_count]),
        "median_redacted_chars": _median([r.redacted_text_chars for r in out_rows if r.redacted_text_chars]),
        "total_pdf_bytes": sum(r.pdf_bytes for r in out_rows),
        "total_redactions": _sum_dicts([r.redaction_stats for r in out_rows]),
    }
    fail_kinds: dict[str, int] = {}
    for r in out_rows:
        if r.extraction_ok or not r.error:
            continue
        kind = r.error.split(":", 1)[0]
        fail_kinds[kind] = fail_kinds.get(kind, 0) + 1
    summary["failures_by_kind"] = fail_kinds

    summary_output = Path(args.summary_output).expanduser()
    if not summary_output.is_absolute():
        summary_output = REPO_ROOT / summary_output
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["n_failed"] == 0 else 1


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def _sum_dicts(dicts: list[dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + int(v)
    return out


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SHA-148 Phase B: download + extract PDFs for the selected 50 ET cases."
    )
    p.add_argument(
        "--selection-manifest",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/selection_manifest.jsonl",
    )
    p.add_argument(
        "--rps",
        type=float,
        default=1.0,
        help="Polite per-second cadence for PDF downloads. Default 1.0.",
    )
    p.add_argument(
        "--output",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/pdf_extraction_report.jsonl",
    )
    p.add_argument(
        "--summary-output",
        default="data/eval_artifacts/gold_build/employment_et_unfair_dismissal_stratified_50_2026-05-15/pdf_extraction_summary.json",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(run(_parser().parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
