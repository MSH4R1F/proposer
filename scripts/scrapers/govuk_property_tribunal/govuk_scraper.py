"""SHA-126: GOV.UK Property Tribunal RRO scraper entrypoint.

Orchestrates downloader + parsers + filter + bailii_overlap + progress.

Usage:
    python -m scripts.scrapers.govuk_property_tribunal.govuk_scraper --max-keep 30

The pilot is intentionally small (default ``max_keep=30``) — we want a
bounded, polite, idempotent run that can be paused mid-stream and
resumed via the master_index.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from .bailii_overlap import (
    BUCKET_BAILII_ONLY,
    BUCKET_DUPLICATE,
    BUCKET_GOVUK_ONLY,
    load_bailii_index,
    overlap_bucket,
    overlap_report,
)
from .config import CORPUS_VERSION, PARSER_VERSION, ScraperConfig
from .downloader import GovUKDownloader
from .filter import classify_rro
from .models import (
    ArtefactKind,
    FilterDecision,
    GovUKPCMetadata,
    GovUKSearchHit,
    ScrapeRecord,
)
from .parsers import (
    extract_pdf_text,
    parse_content_api,
    parse_decision_html,
    parse_search_response,
)
from .progress import MasterIndex, RunLog, append_jsonl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class ScrapeReport:
    started_at: datetime
    finished_at: Optional[datetime] = None
    pages_visited: int = 0
    total_hits_seen: int = 0
    kept_count: int = 0
    excluded_count: int = 0
    unsupported_count: int = 0
    statutory_ground_counts: Dict[str, int] = field(default_factory=dict)
    bailii_buckets: Dict[str, int] = field(default_factory=dict)
    api_query: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "pages_visited": self.pages_visited,
            "total_hits_seen": self.total_hits_seen,
            "kept_count": self.kept_count,
            "excluded_count": self.excluded_count,
            "unsupported_count": self.unsupported_count,
            "statutory_ground_counts": self.statutory_ground_counts,
            "bailii_overlap": self.bailii_buckets,
            "api_query": self.api_query,
            "parser_version": PARSER_VERSION,
            "corpus_version": CORPUS_VERSION,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class GovUKRROScraper:
    """Top-level scraper orchestrator. Single ``run()`` entrypoint."""

    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._config.output_base_dir.mkdir(parents=True, exist_ok=True)
        self._config.decisions_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = RunLog(self._config.progress_log_path)
        self._master_index = MasterIndex.load(self._config.master_index_path)
        self._bailii_index_path = (
            self._config.output_base_dir.parent / "bailii" / "master_index.json"
        )

    # ------------------------------------------------------------------
    async def run(self) -> ScrapeReport:
        report = ScrapeReport(started_at=datetime.utcnow())
        report.api_query = {
            "filter_format": self._config.decision_format,
            "sub_category_guard": self._config.sub_category,
            "sub_category_search_filter_sent": False,
            "search_api_url": self._config.search_api_url,
        }
        bailii_index = load_bailii_index(self._bailii_index_path)

        async with GovUKDownloader(self._config) as dl:
            start = 0
            while (
                report.kept_count < self._config.max_keep
                and report.pages_visited < self._config.max_pages
            ):
                try:
                    payload = await dl.search(start=start, count=self._config.page_size)
                except Exception as exc:
                    report.notes.append(f"search_failed_at_start_{start}: {exc!s}")
                    self._run_log.record(
                        "search_failed",
                        {"start": start, "error": str(exc)},
                    )
                    break

                report.pages_visited += 1
                hits = parse_search_response(payload)
                if not hits:
                    break
                total = payload.get("total")
                if total is not None and report.total_hits_seen == 0:
                    self._run_log.record("search_total", {"total": total})

                for hit in hits:
                    report.total_hits_seen += 1
                    if report.kept_count >= self._config.max_keep:
                        break
                    try:
                        await self._process_hit(dl, hit, bailii_index, report)
                    except Exception as exc:
                        report.notes.append(
                            f"hit_failed:{hit.link}: {exc!s}"
                        )
                        self._run_log.record(
                            "hit_failed",
                            {"link": hit.link, "error": str(exc)},
                        )

                start += self._config.page_size

        report.finished_at = datetime.utcnow()
        report.bailii_buckets = overlap_report(self._master_index.records())
        self._master_index.save()
        self._write_summary(report)
        return report

    # ------------------------------------------------------------------
    async def _process_hit(
        self,
        dl: GovUKDownloader,
        hit: GovUKSearchHit,
        bailii_index: Dict[str, Any],
        report: ScrapeReport,
    ) -> None:
        """Fetch + filter + persist one search hit."""
        base_path = hit.link if hit.link.startswith("/") else "/" + hit.link.split("://", 1)[-1]
        # Fetch content API; fall back to HTML scrape if content is empty.
        meta: Optional[GovUKPCMetadata] = None
        try:
            content = await dl.fetch_content(base_path)
            meta = parse_content_api(content)
        except Exception as exc:
            self._run_log.record(
                "content_api_failed",
                {"link": hit.link, "error": str(exc)},
            )

        body_text: str = (meta.raw_text if meta and meta.raw_text else "") or ""
        if not body_text:
            try:
                html = await dl.fetch_html(hit.link)
                meta_html, body_text = parse_decision_html(html, hit.link)
                if meta is None:
                    meta = meta_html
                else:
                    meta.raw_text = body_text
                    meta.address = meta.address or meta_html.address
                    meta.landlord = meta.landlord or meta_html.landlord
                    meta.tenant = meta.tenant or meta_html.tenant
            except Exception as exc:
                self._run_log.record(
                    "html_fallback_failed",
                    {"link": hit.link, "error": str(exc)},
                )

        if meta is None:
            append_jsonl(
                self._config.excluded_path,
                {"link": hit.link, "reason": "metadata_unavailable"},
            )
            report.excluded_count += 1
            return

        _ensure_content_hash(meta, body_text)
        existing = self._existing_unchanged_record(meta, body_text)
        if existing is not None:
            self._run_log.record(
                "dedup_skip",
                {
                    "case_reference": meta.case_reference,
                    "govuk_page_url": meta.govuk_page_url,
                    "content_sha256": existing.content_sha256,
                },
            )
            return

        # If the primary asset is a PDF and we still have no body, download
        # and extract.
        if (
            (not body_text)
            and meta.primary_artefact_kind == ArtefactKind.PDF
            and meta.primary_asset_url
        ):
            try:
                with tempfile.TemporaryDirectory() as td:
                    tmp = Path(td) / "decision.pdf"
                    kind = await dl.download_asset(meta.primary_asset_url, tmp)
                    if kind == ArtefactKind.PDF:
                        text, _pdf_meta = extract_pdf_text(tmp)
                        body_text = text
                        meta.raw_text = body_text
                        _ensure_content_hash(meta, body_text)
            except Exception as exc:
                self._run_log.record(
                    "pdf_extract_failed",
                    {"link": hit.link, "error": str(exc)},
                )

        # DOCX-only -> unsupported
        if (
            meta.primary_artefact_kind == ArtefactKind.DOCX
            and not body_text
        ):
            append_jsonl(
                self._config.unsupported_path,
                {
                    "case_reference": meta.case_reference,
                    "govuk_page_url": meta.govuk_page_url,
                    "reason": "docx_only_no_html_body",
                },
            )
            report.unsupported_count += 1
            return

        decision, grounds, reasons = classify_rro(hit, body_text)
        meta.filter_decision = decision
        meta.filter_reasons = reasons
        meta.statutory_grounds = grounds

        if decision != FilterDecision.ACCEPT:
            append_jsonl(
                self._config.excluded_path,
                {
                    "case_reference": meta.case_reference,
                    "govuk_page_url": meta.govuk_page_url,
                    "title": meta.title,
                    "decision": decision.value,
                    "reject_reasons": reasons,
                },
            )
            report.excluded_count += 1
            return

        # ---- ACCEPT: persist artefacts and master index entry ------------
        decision_dir = self._config.decisions_dir / _slug(meta.case_reference)
        decision_dir.mkdir(parents=True, exist_ok=True)
        (decision_dir / "raw.txt").write_text(body_text, encoding="utf-8")
        (decision_dir / "parsed.json").write_text(
            json.dumps(meta.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        # Persist primary asset if PDF (best effort)
        primary_kind = meta.primary_artefact_kind
        if (
            meta.primary_asset_url
            and primary_kind == ArtefactKind.PDF
            and meta.primary_asset_url.startswith("http")
        ):
            try:
                pdf_dest = decision_dir / "decision.pdf"
                if not pdf_dest.exists():
                    await dl.download_asset(meta.primary_asset_url, pdf_dest)
                meta.storage_path = str(pdf_dest)
            except Exception as exc:
                self._run_log.record(
                    "pdf_save_failed",
                    {"link": hit.link, "error": str(exc)},
                )
        else:
            html_dest = decision_dir / "decision.html"
            try:
                html_dest.write_text(body_text, encoding="utf-8")
            except OSError:
                pass
            meta.storage_path = str(html_dest)

        dup_of, bucket = overlap_bucket(meta, bailii_index)
        record = ScrapeRecord(
            case_reference=meta.case_reference,
            govuk_page_url=meta.govuk_page_url,
            base_path=meta.base_path,
            decision_date=meta.decision_date,
            title=meta.title,
            filter_decision=decision,
            filter_reasons=reasons,
            statutory_grounds=grounds,
            primary_artefact_kind=meta.primary_artefact_kind,
            storage_path=meta.storage_path,
            content_sha256=meta.content_sha256,
            bailii_duplicate_of=dup_of,
            bailii_overlap_bucket=bucket,
            scraped_at=datetime.utcnow(),
        )
        self._master_index.upsert(record)
        report.kept_count += 1
        for g in grounds:
            report.statutory_ground_counts[g] = report.statutory_ground_counts.get(g, 0) + 1
        self._run_log.record(
            "kept",
            {
                "case_reference": record.case_reference,
                "bailii_overlap_bucket": bucket,
                "duplicate_of": dup_of,
                "statutory_grounds": grounds,
            },
        )

    # ------------------------------------------------------------------
    def _existing_unchanged_record(
        self, meta: GovUKPCMetadata, body_text: str
    ) -> Optional[ScrapeRecord]:
        """Return existing record when a resumed run can safely skip it."""
        existing = self._master_index.get(meta.case_reference)
        if existing is None:
            return None
        if not body_text or not meta.content_sha256:
            return existing
        if existing.content_sha256 == meta.content_sha256:
            return existing
        return None

    # ------------------------------------------------------------------
    def _write_summary(self, report: ScrapeReport) -> None:
        path = self._config.scrape_summary_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


def _slug(case_reference: str) -> str:
    """Filesystem-safe slug for a case reference."""
    safe = []
    for ch in case_reference:
        if ch.isalnum():
            safe.append(ch)
        elif ch in ("/", "\\", " "):
            safe.append("_")
        elif ch in (".", "-", "_"):
            safe.append(ch)
    s = "".join(safe).strip("_")
    return s or "decision"


def _ensure_content_hash(meta: GovUKPCMetadata, body_text: str) -> None:
    if body_text and not meta.content_sha256:
        meta.content_sha256 = hashlib.sha256(body_text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--max-keep", type=int, default=30, help="Stop after N accepted decisions.")
@click.option("--max-pages", type=int, default=20, help="Stop after N search pages.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default="data/raw/govuk_property_tribunal",
)
@click.option("--rps", type=float, default=1.0, help="Requests per second cap.")
@click.option("--no-robots", is_flag=True, default=False)
def main(max_keep: int, max_pages: int, output_dir: str, rps: float, no_robots: bool) -> None:
    """CLI entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = ScraperConfig(
        max_keep=max_keep,
        max_pages=max_pages,
        output_base_dir=Path(output_dir),
        requests_per_second=rps,
        respect_robots_txt=not no_robots,
    )
    scraper = GovUKRROScraper(config)
    report = asyncio.run(scraper.run())
    click.echo(json.dumps(report.as_dict(), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["GovUKRROScraper", "ScrapeReport"]
