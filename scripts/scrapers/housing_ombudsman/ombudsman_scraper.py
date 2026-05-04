"""SHA-125: Housing Ombudsman scraper orchestrator.

Composes :class:`OmbudsmanDownloader`, the parsers, the repairs filter,
and :class:`RunLog` into a polite, bounded pilot crawl.

Outputs (under ``data/raw/housing_ombudsman/``):

* ``decisions/<case_ref>/decision.html`` — the raw HTML page
* ``decisions/<case_ref>/raw.txt`` — the visible text used for filtering
* ``decisions/<case_ref>/parsed.json`` — :class:`OmbudsmanCaseMetadata`
  serialised to JSON
* ``excluded.jsonl`` — append-only rows for rejected cases
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
from .downloader import OmbudsmanDownloader, OmbudsmanFetchError
from .filter import keep_repairs_social_only
from .models import OmbudsmanCaseMetadata
from .parsers import parse_detail_html, parse_listing_html
from .progress import RunLog

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
    earliest_decision_date: Optional[str] = None
    latest_decision_date: Optional[str] = None
    fixture_only: bool = False
    notes: List[str] = field(default_factory=list)


class OmbudsmanScraper:
    """Polite pilot scraper for Housing Ombudsman determinations."""

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

        async with OmbudsmanDownloader(self.config) as downloader:
            try:
                async for html in downloader.fetch_listing_pages():
                    self.report.listings_visited += 1
                    if not await self._process_listing_page(html, downloader):
                        break
            except OmbudsmanFetchError as e:
                self.report.notes.append(f"fetch_error: {e}")
                self.runlog.record("fetch_error", {"error": str(e)})

        self.runlog.save_master_index()
        self.report.finished_at = _now_iso()
        self._write_summary()
        self.runlog.record("run_finish", {"report": asdict(self.report)})
        return self.report

    # ------------------------------------------------------------------
    # Listing / detail handling
    # ------------------------------------------------------------------

    async def _process_listing_page(
        self, html: str, downloader: OmbudsmanDownloader
    ) -> bool:
        """Process one listing page. Returns ``False`` to stop crawling."""
        rows = parse_listing_html(html, base_url=self.config.base_url)
        for row in rows:
            if self.report.cases_kept >= self.config.max_keep:
                self.runlog.record("max_keep_hit", {"max_keep": self.config.max_keep})
                return False
            self.report.cases_seen += 1
            try:
                detail_html = await downloader.get_html(row.detail_url)
            except OmbudsmanFetchError as e:
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
            metadata, raw_text = parse_detail_html(html, source_url=source_url)
        except Exception as e:
            self.runlog.record(
                "parse_error",
                {"case_ref": case_ref_hint, "error": repr(e)},
            )
            return

        # Prefer parser-extracted reference; fall back to listing hint.
        # ``parse_detail_html`` returns the literal sentinel "unknown" when
        # both the labelled-field and URL-pattern paths fail, so treat
        # that as absent — otherwise every unparseable page collides into
        # ``decisions/unknown/`` and overwrites prior siblings.
        parsed_ref = metadata.case_reference
        case_ref = (
            parsed_ref
            if parsed_ref and parsed_ref != "unknown"
            else case_ref_hint
        )
        content_hash = self.runlog.content_hash(raw_text)
        if self.runlog.dedup_key(case_ref, source_url, content_hash):
            self.runlog.record(
                "dedup_skip", {"case_ref": case_ref, "source_url": source_url}
            )
            return

        decision = keep_repairs_social_only(metadata, raw_text)

        if decision.keep:
            storage_path = self._write_kept(case_ref, html, raw_text, metadata)
            self.runlog.upsert(
                case_ref,
                source_url=source_url,
                content_sha256=content_hash,
                decision_date=(
                    metadata.decision_date.isoformat()
                    if metadata.decision_date
                    else None
                ),
                kept=True,
                raw_storage_path=str(storage_path),
                matter_types=decision.matter_types,
            )
            self.report.cases_kept += 1
            for mt in decision.matter_types:
                self.report.matter_type_counts[mt] = (
                    self.report.matter_type_counts.get(mt, 0) + 1
                )
            if metadata.outcome_normalized:
                key = metadata.outcome_normalized
            else:
                key = metadata.outcome_raw or "unknown"
            self.report.outcome_counts[key] = (
                self.report.outcome_counts.get(key, 0) + 1
            )
            if metadata.decision_date:
                iso = metadata.decision_date.isoformat()
                if (
                    self.report.earliest_decision_date is None
                    or iso < self.report.earliest_decision_date
                ):
                    self.report.earliest_decision_date = iso
                if (
                    self.report.latest_decision_date is None
                    or iso > self.report.latest_decision_date
                ):
                    self.report.latest_decision_date = iso
            self.runlog.record(
                "case_kept",
                {
                    "case_ref": case_ref,
                    "source_url": source_url,
                    "matter_types": decision.matter_types,
                },
            )
        else:
            self._write_excluded(case_ref, source_url, metadata, decision)
            self.runlog.upsert(
                case_ref,
                source_url=source_url,
                content_sha256=content_hash,
                decision_date=(
                    metadata.decision_date.isoformat()
                    if metadata.decision_date
                    else None
                ),
                kept=False,
                raw_storage_path=None,
                matter_types=[],
            )
            self.report.cases_excluded += 1
            reason = decision.reject_reason or "unknown"
            self.report.excluded_reasons[reason] = (
                self.report.excluded_reasons.get(reason, 0) + 1
            )
            self.runlog.record(
                "case_excluded",
                {
                    "case_ref": case_ref,
                    "source_url": source_url,
                    "reject_reason": decision.reject_reason,
                    "matched_keywords": decision.matched_keywords,
                },
            )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)

    def _write_kept(
        self,
        case_ref: str,
        html: str,
        raw_text: str,
        metadata: OmbudsmanCaseMetadata,
    ) -> Path:
        case_dir = self.config.decisions_dir / case_ref
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "decision.html").write_text(html, encoding="utf-8")
        (case_dir / "raw.txt").write_text(raw_text, encoding="utf-8")
        parsed = metadata.model_dump(mode="json")
        (case_dir / "parsed.json").write_text(
            json.dumps(parsed, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return case_dir

    def _write_excluded(
        self,
        case_ref: str,
        source_url: str,
        metadata: OmbudsmanCaseMetadata,
        decision,
    ) -> None:
        row = {
            "case_ref": case_ref,
            "source_url": source_url,
            "categories": list(metadata.complaint_categories or []),
            "reject_reason": decision.reject_reason,
            "excerpt": decision.excerpt,
            "matched_keywords": decision.matched_keywords,
        }
        with self.config.excluded_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_summary(self) -> None:
        payload = asdict(self.report)
        self.config.scrape_summary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    def _config_for_log(self) -> dict:
        return {
            "base_url": self.config.base_url,
            "max_keep": self.config.max_keep,
            "max_listing_pages": self.config.max_listing_pages,
            "requests_per_second": self.config.requests_per_second,
            "respect_robots": self.config.respect_robots,
            "corpus_version": self.config.corpus_version,
            "user_agent": self.config.user_agent,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--max-keep", type=int, default=None, help="Cap kept decisions.")
@click.option(
    "--max-listing-pages", type=int, default=None, help="Cap listing pages crawled."
)
@click.option(
    "--data-dir",
    type=click.Path(),
    default=None,
    help=(
        "Override base data dir. Raw output is written to "
        "<data-dir>/raw/housing_ombudsman, matching the ingest script."
    ),
)
@click.option(
    "--rate", type=float, default=None, help="Requests per second (token bucket)."
)
@click.option(
    "--no-robots",
    is_flag=True,
    default=False,
    help="Skip robots.txt check (use only with explicit permission).",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(
    max_keep: Optional[int],
    max_listing_pages: Optional[int],
    data_dir: Optional[str],
    rate: Optional[float],
    no_robots: bool,
    verbose: bool,
) -> None:
    """Run the SHA-125 Housing Ombudsman pilot scraper."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    config = ScraperConfig()
    if data_dir is not None:
        data_root = Path(data_dir).expanduser().resolve()
        config.output_subdir = str(data_root / "raw" / "housing_ombudsman")
    if max_keep is not None:
        config.max_keep = max_keep
    if max_listing_pages is not None:
        config.max_listing_pages = max_listing_pages
    if rate is not None:
        config.requests_per_second = rate
    if no_robots:
        config.respect_robots = False

    scraper = OmbudsmanScraper(config)
    report = asyncio.run(scraper.run())

    print("\n=== Ombudsman scrape complete ===")
    print(json.dumps(asdict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = ["OmbudsmanScraper", "ScrapeReport"]
