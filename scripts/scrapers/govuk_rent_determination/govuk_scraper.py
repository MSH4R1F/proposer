"""SHA-138: GOV.UK FTT(PC) MNR rent-determination scraper entrypoint.

Orchestrates downloader + parsers + filter + progress.

Usage:
    python -m scripts.scrapers.govuk_rent_determination.govuk_scraper --max-keep 50

The pilot is intentionally bounded — we want a polite, idempotent run
that can be paused mid-stream and resumed via the master_index.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from .config import CORPUS_VERSION, PARSER_VERSION, ScraperConfig
from .downloader import GovUKDownloader
from .filter import classify_mnr
from .models import (
    ArtefactKind,
    FilterDecision,
    GovUKPCMetadata,
    GovUKSearchHit,
    RentPeriod,
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
    rent_extracted_count: int = 0
    rent_period_counts: Dict[str, int] = field(default_factory=dict)
    statute_basis_counts: Dict[str, int] = field(default_factory=dict)
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
            "rent_extracted_count": self.rent_extracted_count,
            "rent_period_counts": self.rent_period_counts,
            "statute_basis_counts": self.statute_basis_counts,
            "api_query": self.api_query,
            "parser_version": PARSER_VERSION,
            "corpus_version": CORPUS_VERSION,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class GovUKMNRScraper:
    """Top-level scraper orchestrator. Single ``run()`` entrypoint."""

    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._config.output_base_dir.mkdir(parents=True, exist_ok=True)
        self._config.decisions_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = RunLog(self._config.progress_log_path)
        self._master_index = MasterIndex.load(self._config.master_index_path)

    # ------------------------------------------------------------------
    async def run(self) -> ScrapeReport:
        report = ScrapeReport(started_at=datetime.utcnow())
        report.api_query = {
            "filter_format": self._config.decision_format,
            "matter_code": self._config.matter_code,
            "search_api_url": self._config.search_api_url,
        }

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

                # MNR matter-code is in the case reference embedded in the
                # title or link, so we can pre-filter before fetching the
                # content API. This dramatically cuts wasted requests.
                pre_filtered = [
                    h for h in hits
                    if classify_mnr(h, body_text=None)[0] == FilterDecision.ACCEPT
                ]
                report.total_hits_seen += len(hits)

                for hit in pre_filtered:
                    if report.kept_count >= self._config.max_keep:
                        break
                    try:
                        await self._process_hit(dl, hit, report)
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
        self._master_index.save()
        self._write_summary(report)
        return report

    # ------------------------------------------------------------------
    async def _process_hit(
        self,
        dl: GovUKDownloader,
        hit: GovUKSearchHit,
        report: ScrapeReport,
    ) -> None:
        """Fetch + filter + persist one search hit."""
        base_path = hit.link if hit.link.startswith("/") else "/" + hit.link.split("://", 1)[-1]
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
                    if meta.decided_rent_amount is None and meta_html.decided_rent_amount is not None:
                        meta.decided_rent_amount = meta_html.decided_rent_amount
                        meta.decided_rent_period = meta_html.decided_rent_period
                    meta.landlord_proposed_rent_amount = (
                        meta.landlord_proposed_rent_amount
                        or meta_html.landlord_proposed_rent_amount
                    )
                    meta.existing_rent_amount = (
                        meta.existing_rent_amount or meta_html.existing_rent_amount
                    )
                    meta.statute_basis = meta.statute_basis or meta_html.statute_basis
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

        # GOV.UK FTT(PC) decisions return a stub like
        # "Read the full decision in <REF>" from /api/content/. The real
        # text is always in a PDF attachment, so prefer the PDF when
        # primary_artefact_kind == PDF, regardless of stub-body presence.
        body_is_stub = bool(body_text) and len(body_text.strip()) < 200
        if (
            (not body_text or body_is_stub)
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
                        # Re-run extraction now that body text is available.
                        from .parsers import extract_rent_determination
                        rent = extract_rent_determination(body_text)
                        meta.decided_rent_amount = (
                            meta.decided_rent_amount or rent.decided_rent_amount
                        )
                        if meta.decided_rent_period == RentPeriod.UNKNOWN:
                            meta.decided_rent_period = rent.decided_rent_period
                        meta.landlord_proposed_rent_amount = (
                            meta.landlord_proposed_rent_amount
                            or rent.landlord_proposed_rent_amount
                        )
                        meta.existing_rent_amount = (
                            meta.existing_rent_amount or rent.existing_rent_amount
                        )
                        meta.statute_basis = meta.statute_basis or rent.statute_basis
            except Exception as exc:
                self._run_log.record(
                    "pdf_extract_failed",
                    {"link": hit.link, "error": str(exc)},
                )

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

        # Final filter check (body text may have given us a stronger signal).
        decision, reasons = classify_mnr(hit, body_text, meta.case_reference)
        meta.filter_decision = decision
        meta.filter_reasons = reasons

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

        record = ScrapeRecord(
            case_reference=meta.case_reference,
            govuk_page_url=meta.govuk_page_url,
            base_path=meta.base_path,
            decision_date=meta.decision_date,
            title=meta.title,
            filter_decision=decision,
            filter_reasons=reasons,
            decided_rent_amount=meta.decided_rent_amount,
            decided_rent_period=meta.decided_rent_period,
            primary_artefact_kind=meta.primary_artefact_kind,
            storage_path=meta.storage_path,
            content_sha256=meta.content_sha256,
            scraped_at=datetime.utcnow(),
        )
        self._master_index.upsert(record)
        report.kept_count += 1
        if meta.decided_rent_amount is not None:
            report.rent_extracted_count += 1
            period_key = meta.decided_rent_period.value
            report.rent_period_counts[period_key] = (
                report.rent_period_counts.get(period_key, 0) + 1
            )
        if meta.statute_basis:
            report.statute_basis_counts[meta.statute_basis] = (
                report.statute_basis_counts.get(meta.statute_basis, 0) + 1
            )
        self._run_log.record(
            "kept",
            {
                "case_reference": record.case_reference,
                "decided_rent_amount": meta.decided_rent_amount,
                "decided_rent_period": meta.decided_rent_period.value,
                "statute_basis": meta.statute_basis,
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
@click.option("--max-keep", type=int, default=50, help="Stop after N accepted MNR decisions.")
@click.option("--max-pages", type=int, default=20, help="Stop after N search pages.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default="data/raw/govuk_rent_determination",
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
    scraper = GovUKMNRScraper(config)
    report = asyncio.run(scraper.run())
    click.echo(json.dumps(report.as_dict(), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["GovUKMNRScraper", "ScrapeReport"]
