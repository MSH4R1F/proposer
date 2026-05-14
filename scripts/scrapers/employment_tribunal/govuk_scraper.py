"""SHA-145 / SHA-65a: GOV.UK Employment Tribunal scraper orchestrator.

Composes :class:`ETDownloader`, the parsers, the merits-quality filter,
:func:`et_to_source_document`, and :class:`RunLog` into a polite, bounded
pilot crawl. SHA-145 ships the orchestrator with a ``--dry-run`` mode that
exercises the full pipeline against fixture HTML without touching the
network. Live runs land in SHA-65b (SHA-146).

Outputs (under ``data/raw/employment/``):

* ``decisions/<case_ref>/decision.html`` — raw HTML page (pre-redaction)
* ``decisions/<case_ref>/raw.txt`` — visible text used for filtering
* ``decisions/<case_ref>/parsed.json`` — :class:`ETCaseMetadata` JSON
* ``decisions/<case_ref>/source_document.json`` — model-facing redacted doc
* ``excluded.jsonl`` — append-only rows for rejected cases (with reason codes)
* ``master_index.json`` — durable resume key
* ``_runs/<run_id>.jsonl`` — per-run audit log
* ``scrape_summary.json`` — totals + breakdowns
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import click

from .config import ScraperConfig
from .downloader import ETDownloader, ETFetchError
from .filter import FilterResult, keep_unfair_dismissal_merits_only
from .models import ETCaseMetadata
from .parsers import parse_detail_html, parse_listing_html
from .progress import RunLog
from .to_source_document import et_to_source_document

logger = logging.getLogger(__name__)


@dataclass
class ScrapeReport:
    started_at: str
    finished_at: Optional[str] = None
    listings_visited: int = 0
    cases_seen: int = 0
    cases_kept: int = 0
    cases_excluded: int = 0
    excluded_reasons: dict = field(default_factory=dict)
    matter_type_counts: dict = field(default_factory=dict)
    outcome_counts: dict = field(default_factory=dict)
    country_counts: dict = field(default_factory=dict)
    earliest_decision_date: Optional[str] = None
    latest_decision_date: Optional[str] = None
    fixture_only: bool = False
    notes: List[str] = field(default_factory=list)


class EmploymentTribunalScraper:
    """Polite pilot scraper for GOV.UK Employment Tribunal decisions."""

    def __init__(self, config: Optional[ScraperConfig] = None) -> None:
        self.config = config or ScraperConfig()
        self.runlog = RunLog(
            runs_dir=self.config.runs_dir,
            master_index_path=self.config.master_index_path,
        )
        self.report = ScrapeReport(started_at=_now_iso())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> ScrapeReport:
        self._ensure_dirs()
        self.runlog.record("run_start", {"config": self._config_for_log()})

        async with ETDownloader(self.config) as downloader:
            try:
                async for html in downloader.fetch_listing_pages():
                    self.report.listings_visited += 1
                    if not await self._process_listing_page(html, downloader):
                        break
            except ETFetchError as e:
                self.report.notes.append(f"fetch_error: {e}")
                self.runlog.record("fetch_error", {"error": str(e)})

        self.runlog.save_master_index()
        self.report.finished_at = _now_iso()
        self._write_summary()
        self.runlog.record("run_finish", {"report": asdict(self.report)})
        return self.report

    def run_dry(self, listing_html: str, detail_pairs: List[tuple]) -> ScrapeReport:
        """Run the pipeline against in-memory fixtures (no network).

        ``listing_html`` is the listing-page HTML; ``detail_pairs`` is a list
        of ``(detail_url, detail_html)`` for each linked decision. Used by
        :func:`cli`'s ``--dry-run`` mode and by tests.
        """
        self._ensure_dirs()
        self.report.fixture_only = True
        self.runlog.record(
            "dry_run_start",
            {"detail_count": len(detail_pairs)},
        )
        self.report.listings_visited = 1
        listings = parse_listing_html(
            listing_html, base_url=self.config.base_url
        )
        detail_lookup = {url: html for url, html in detail_pairs}
        for row in listings:
            if self.report.cases_kept >= self.config.max_keep:
                break
            self.report.cases_seen += 1
            detail_html = detail_lookup.get(row.detail_url)
            if not detail_html:
                self.runlog.record(
                    "dry_run_missing_detail",
                    {"case_ref": row.case_reference, "url": row.detail_url},
                )
                continue
            self._handle_detail(row.case_reference, row.detail_url, detail_html)
        self.runlog.save_master_index()
        self.report.finished_at = _now_iso()
        self._write_summary()
        self.runlog.record("dry_run_finish", {"report": asdict(self.report)})
        return self.report

    # ------------------------------------------------------------------
    # Listing / detail handling
    # ------------------------------------------------------------------

    async def _process_listing_page(
        self, html: str, downloader: ETDownloader
    ) -> bool:
        """Process one listing page. Returns ``False`` to stop crawling."""
        rows = parse_listing_html(html, base_url=self.config.base_url)
        for row in rows:
            if self.report.cases_kept >= self.config.max_keep:
                self.runlog.record(
                    "max_keep_hit", {"max_keep": self.config.max_keep}
                )
                return False
            self.report.cases_seen += 1
            try:
                detail_html = await downloader.get_html(row.detail_url)
            except ETFetchError as e:
                self.runlog.record(
                    "detail_fetch_error",
                    {"case_ref": row.case_reference, "error": str(e)},
                )
                continue
            self._handle_detail(row.case_reference, row.detail_url, detail_html)
        return True

    def _handle_detail(
        self, case_ref_hint: str, source_url: str, html: str
    ) -> None:
        try:
            metadata, body_text = parse_detail_html(html, source_url)
        except Exception as e:
            self.runlog.record(
                "parse_error",
                {"case_ref": case_ref_hint, "url": source_url, "error": str(e)},
            )
            return

        content_hash = RunLog.content_hash(body_text)
        case_ref = metadata.case_reference or case_ref_hint
        if self.runlog.dedup_key(case_ref, source_url, content_hash):
            self.runlog.record(
                "dedup_skip",
                {
                    "case_ref": case_ref,
                    "source_url": source_url,
                    "content_sha256": content_hash,
                },
            )
            return

        # SHA-146 pilot finding #2: GOV.UK's URL-level date filter is
        # best-effort and may silently drop the params on a schema change.
        # Belt-and-braces: enforce the year window in code too. The
        # decision is rejected with reason `out_of_year_window` so
        # `excluded.jsonl` still records it, rather than disappearing
        # silently like a dedup hit would.
        if metadata.decision_date is not None:
            dy = metadata.decision_date.year
            if dy < self.config.years_from or dy > self.config.years_to:
                filter_result_out_of_window = FilterResult(
                    keep=False,
                    reject_reason="out_of_year_window",
                    matched_signals=[
                        f"decision_year={dy}",
                        f"window={self.config.years_from}-{self.config.years_to}",
                    ],
                    excerpt=None,
                )
                metadata.stage2_keep = False
                metadata.stage2_reason = "out_of_year_window"
                self._record_exclusion(
                    case_ref,
                    source_url,
                    metadata,
                    filter_result_out_of_window,
                    content_hash,
                )
                return

        filter_result = keep_unfair_dismissal_merits_only(metadata, body_text)
        metadata.stage2_keep = filter_result.keep
        metadata.stage2_reason = filter_result.reject_reason

        if not filter_result.keep:
            self._record_exclusion(case_ref, source_url, metadata, filter_result, content_hash)
            return

        try:
            source_document = et_to_source_document(
                metadata,
                body_text,
                kept_matter_types=filter_result.matter_types,
                config=self.config,
            )
        except ValueError as e:
            # Redaction emptied the body, or contract was violated. Quarantine.
            self.runlog.record(
                "source_document_error",
                {"case_ref": case_ref, "url": source_url, "error": str(e)},
            )
            self.report.cases_excluded += 1
            self.report.excluded_reasons["source_document_error"] = (
                self.report.excluded_reasons.get("source_document_error", 0) + 1
            )
            return

        self._persist_kept(case_ref, html, body_text, metadata, source_document)
        self.runlog.upsert(
            case_ref,
            source_url=source_url,
            content_sha256=content_hash,
            decision_date=metadata.decision_date.isoformat() if metadata.decision_date else None,
            kept=True,
            raw_storage_path=str(self._case_dir(case_ref)),
            matter_types=filter_result.matter_types,
        )
        self.report.cases_kept += 1
        for mt in filter_result.matter_types:
            self.report.matter_type_counts[mt] = (
                self.report.matter_type_counts.get(mt, 0) + 1
            )
        if metadata.outcome_normalized:
            self.report.outcome_counts[metadata.outcome_normalized] = (
                self.report.outcome_counts.get(metadata.outcome_normalized, 0) + 1
            )
        if metadata.country:
            self.report.country_counts[metadata.country.value] = (
                self.report.country_counts.get(metadata.country.value, 0) + 1
            )
        if metadata.decision_date:
            iso = metadata.decision_date.isoformat()
            if not self.report.earliest_decision_date or iso < self.report.earliest_decision_date:
                self.report.earliest_decision_date = iso
            if not self.report.latest_decision_date or iso > self.report.latest_decision_date:
                self.report.latest_decision_date = iso
        self.runlog.record(
            "kept",
            {
                "case_ref": case_ref,
                "outcome": metadata.outcome_normalized,
                "country": metadata.country.value if metadata.country else None,
                "matter_types": filter_result.matter_types,
            },
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _record_exclusion(
        self,
        case_ref: str,
        source_url: str,
        metadata: ETCaseMetadata,
        filter_result: FilterResult,
        content_hash: str,
    ) -> None:
        self.report.cases_excluded += 1
        reason = filter_result.reject_reason or "unknown"
        self.report.excluded_reasons[reason] = (
            self.report.excluded_reasons.get(reason, 0) + 1
        )
        line = {
            "case_ref": case_ref,
            "source_url": source_url,
            "content_sha256": content_hash,
            "reject_reason": reason,
            "matched_signals": filter_result.matched_signals,
            "excerpt": filter_result.excerpt,
            "outcome_raw": metadata.outcome_raw,
            "outcome_normalized": metadata.outcome_normalized,
            "country": metadata.country.value if metadata.country else None,
        }
        with self.config.excluded_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
        self.runlog.upsert(
            case_ref,
            source_url=source_url,
            content_sha256=content_hash,
            kept=False,
            matter_types=[],
            reject_reason=reason,
        )
        self.runlog.record("excluded", line)

    def _persist_kept(
        self,
        case_ref: str,
        html: str,
        body_text: str,
        metadata: ETCaseMetadata,
        source_document,
    ) -> None:
        case_dir = self._case_dir(case_ref)
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "decision.html").write_text(html, encoding="utf-8")
        (case_dir / "raw.txt").write_text(body_text, encoding="utf-8")
        (case_dir / "parsed.json").write_text(
            json.dumps(_safe_jsonable(metadata.model_dump(mode="json")), indent=2, default=str),
            encoding="utf-8",
        )
        (case_dir / "source_document.json").write_text(
            json.dumps(_safe_jsonable(source_document.model_dump(mode="json")), indent=2, default=str),
            encoding="utf-8",
        )

    def _case_dir(self, case_ref: str) -> Path:
        safe = case_ref.replace("/", "_").replace(" ", "_")
        return self.config.decisions_dir / safe

    def _ensure_dirs(self) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)
        # Touch excluded.jsonl so append-mode never fails.
        if not self.config.excluded_path.exists():
            self.config.excluded_path.touch()

    def _write_summary(self) -> None:
        payload = asdict(self.report)
        self.config.scrape_summary_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )

    def _config_for_log(self) -> dict:
        return {
            "base_url": self.config.base_url,
            "decisions_path": self.config.decisions_path,
            "jurisdiction_category_slug": self.config.jurisdiction_category_slug,
            "max_keep": self.config.max_keep,
            "rps": self.config.requests_per_second,
            "years_from": self.config.years_from,
            "years_to": self.config.years_to,
            "corpus_version": self.config.corpus_version,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_jsonable(payload):
    """Strip Pydantic-injected types that json.dumps can't natively handle.

    ``model_dump(mode="json")`` already produces JSON-compatible scalars
    for our models, but ``Counter`` / dataclass nested values still need
    a default. We let ``json.dumps(..., default=str)`` handle the long tail.
    """
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--max-keep", type=int, default=None, help="Stop after this many kept cases.")
@click.option(
    "--jurisdiction-code",
    default="unfair-dismissal",
    show_default=True,
    help="GOV.UK tribunal_decision_categories slug used for Stage 1 filtering.",
)
@click.option(
    "--rps",
    type=float,
    default=None,
    help="Requests per second (default 0.5).",
)
@click.option(
    "--years",
    default=None,
    help="Inclusive year range, e.g. 2019-2024.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Skip network. Requires --fixture-dir.",
)
@click.option(
    "--fixture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory containing listing.html + detail/*.html for --dry-run.",
)
def cli(
    max_keep: Optional[int],
    jurisdiction_code: str,
    rps: Optional[float],
    years: Optional[str],
    dry_run: bool,
    fixture_dir: Optional[Path],
) -> None:
    """Run the GOV.UK Employment Tribunal scraper (SHA-145)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = ScraperConfig()
    if max_keep is not None:
        config.max_keep = max_keep
    if rps is not None:
        config.requests_per_second = rps
    if jurisdiction_code:
        config.jurisdiction_category_slug = jurisdiction_code
    if years:
        try:
            lo, hi = years.split("-", 1)
            config.years_from = int(lo)
            config.years_to = int(hi)
        except ValueError:
            raise click.UsageError(f"--years must be YYYY-YYYY, got {years!r}")

    scraper = EmploymentTribunalScraper(config)

    if dry_run:
        if not fixture_dir:
            raise click.UsageError("--dry-run requires --fixture-dir pointing at fixture HTML")
        listing_path = fixture_dir / "listing.html"
        if not listing_path.exists():
            raise click.UsageError(f"missing {listing_path}")
        listing_html = listing_path.read_text(encoding="utf-8")
        detail_pairs: List[tuple] = []
        for path in sorted((fixture_dir / "detail").glob("*.html")):
            url = path.read_text(encoding="utf-8").splitlines()[0]
            # First line of each fixture detail file is the canonical URL.
            html_body = "\n".join(path.read_text(encoding="utf-8").splitlines()[1:])
            detail_pairs.append((url.strip(), html_body))
        report = scraper.run_dry(listing_html, detail_pairs)
        click.echo(json.dumps(asdict(report), indent=2, default=str))
        return

    report = asyncio.run(scraper.run())
    click.echo(json.dumps(asdict(report), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    cli()
