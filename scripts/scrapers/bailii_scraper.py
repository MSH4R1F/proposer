"""
BAILII Scraper - Main orchestrator.

Coordinates scraping of UK First-tier Tribunal (Property Chamber) decisions
from BAILII, with focus on tenancy deposit dispute cases.

Usage:
    python -m scripts.scrapers.bailii_scraper --years 2020 2021 2022 2023 2024 2025
    python -m scripts.scrapers.bailii_scraper --resume
    python -m scripts.scrapers.bailii_scraper --dry-run --years 2024
    python -m scripts.scrapers.bailii_scraper --stats
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click
from tqdm import tqdm

from .config import ScraperConfig
from .downloader import AsyncDownloader
from .models import CaseCategory, CaseMetadata, ScrapeStatus, MasterIndex
from .parsers import YearIndexParser, CasePageParser
from .progress import ProgressTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class BAILIIScraper:
    """
    Main scraper class for BAILII tribunal decisions.

    Orchestrates:
    - Year index scraping
    - Individual case downloading (HTML + PDF)
    - Keyword-based categorization
    - Progress tracking with resume capability
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.year_parser = YearIndexParser(self.config)
        self.case_parser = CasePageParser(self.config)

    async def scrape_years(
        self,
        years: List[int],
        dry_run: bool = False,
        resume: bool = False,
    ) -> dict:
        """
        Scrape cases for specified years.

        Args:
            years: List of years to scrape
            dry_run: If True, only list cases without downloading
            resume: If True, skip already-completed cases

        Returns:
            Summary statistics
        """
        logger.info(f"Starting BAILII scraper for years: {years}")
        logger.info(f"Output directory: {self.config.output_base_dir}")
        logger.info(f"Dry run: {dry_run}, Resume: {resume}")

        # Create output directories
        self.config.output_base_dir.mkdir(parents=True, exist_ok=True)
        self.config.deposit_dir.mkdir(parents=True, exist_ok=True)
        self.config.adjacent_dir.mkdir(parents=True, exist_ok=True)
        self.config.other_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "started_at": datetime.utcnow().isoformat(),
            "years": years,
            "dry_run": dry_run,
            "total_cases_found": 0,
            "deposit_cases": 0,
            "adjacent_cases": 0,
            "other_cases": 0,
            "successful_downloads": 0,
            "failed_downloads": 0,
        }

        async with ProgressTracker(self.config) as progress:
            run_id = await progress.start_run(years)

            async with AsyncDownloader(self.config) as downloader:
                for year in years:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"Processing year: {year}")
                    logger.info(f"{'='*60}")

                    year_stats = await self._scrape_year(
                        year=year,
                        downloader=downloader,
                        progress=progress,
                        dry_run=dry_run,
                        resume=resume,
                    )

                    # Update summary
                    summary["total_cases_found"] += year_stats["cases_found"]
                    summary["deposit_cases"] += year_stats["deposit_cases"]
                    summary["adjacent_cases"] += year_stats["adjacent_cases"]
                    summary["other_cases"] += year_stats["other_cases"]
                    summary["successful_downloads"] += year_stats["successful"]
                    summary["failed_downloads"] += year_stats["failed"]

                    logger.info(f"Year {year} complete: {year_stats}")

            await progress.complete_run(run_id)

            # Export master index
            await progress.export_to_json(self.config.master_index_path)

        summary["completed_at"] = datetime.utcnow().isoformat()
        summary["download_stats"] = downloader.get_stats() if not dry_run else None

        # Save summary
        summary_path = self.config.output_base_dir / "scrape_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"\n{'='*60}")
        logger.info("SCRAPING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total cases found: {summary['total_cases_found']}")
        logger.info(f"  Deposit cases: {summary['deposit_cases']}")
        logger.info(f"  Adjacent cases: {summary['adjacent_cases']}")
        logger.info(f"  Other cases: {summary['other_cases']}")
        if not dry_run:
            logger.info(f"Successful downloads: {summary['successful_downloads']}")
            logger.info(f"Failed downloads: {summary['failed_downloads']}")

        return summary

    async def _scrape_year(
        self,
        year: int,
        downloader: AsyncDownloader,
        progress: ProgressTracker,
        dry_run: bool,
        resume: bool,
    ) -> dict:
        """Scrape all cases for a single year."""
        stats = {
            "year": year,
            "cases_found": 0,
            "deposit_cases": 0,
            "adjacent_cases": 0,
            "other_cases": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
        }

        # Fetch year index
        year_url = self.config.get_year_url(year)
        logger.info(f"Fetching year index: {year_url}")

        try:
            html = await downloader.fetch_html(year_url)
        except Exception as e:
            logger.error(f"Failed to fetch year index for {year}: {e}")
            return stats

        # Parse year index
        entries = self.year_parser.parse(html, year)
        stats["cases_found"] = len(entries)
        logger.info(f"Found {len(entries)} cases in {year}")

        if not entries:
            logger.warning(f"No cases found for year {year}")
            return stats

        # Process each case
        pbar = tqdm(entries, desc=f"Year {year}", unit="case")

        for entry in pbar:
            case_ref = entry.case_reference
            pbar.set_postfix({"case": case_ref[:20]})

            # Check if already processed
            if resume:
                status = await progress.get_case_status(case_ref)
                if status == "complete":
                    stats["skipped"] += 1
                    continue

            try:
                result = await self._process_case(
                    entry=entry,
                    year=year,
                    downloader=downloader,
                    progress=progress,
                    dry_run=dry_run,
                )

                if result["category"] == "deposit":
                    stats["deposit_cases"] += 1
                elif result["category"] == "adjacent":
                    stats["adjacent_cases"] += 1
                else:
                    stats["other_cases"] += 1

                if result["success"]:
                    stats["successful"] += 1
                elif not dry_run:
                    stats["failed"] += 1

            except Exception as e:
                logger.error(f"Error processing {case_ref}: {e}")
                stats["failed"] += 1
                await progress.log_error(case_ref, "processing_error", str(e))

        return stats

    async def _process_case(
        self,
        entry,
        year: int,
        downloader: AsyncDownloader,
        progress: ProgressTracker,
        dry_run: bool,
    ) -> dict:
        """Process a single case."""
        case_ref = entry.case_reference
        result = {"case_ref": case_ref, "category": "other", "success": False}

        # Download HTML content (needed for keyword matching)
        html_content: Optional[str] = None

        if not dry_run:
            try:
                html_content = await downloader.fetch_html(entry.html_url)
            except Exception as e:
                logger.warning(f"Failed to fetch HTML for {case_ref}: {e}")

        # Parse case page if we have content
        if html_content:
            metadata = self.case_parser.parse(html_content, case_ref, year)
        else:
            # Create minimal metadata without content analysis
            metadata = CaseMetadata(
                case_reference=case_ref,
                year=year,
                html_url=entry.html_url,
                pdf_url=entry.pdf_url,
                title=entry.title,
                category=CaseCategory.OTHER,
            )

        result["category"] = metadata.category.value if hasattr(metadata.category, 'value') else str(metadata.category)

        # Determine output directory
        output_dir = metadata.get_output_dir(self.config.output_base_dir)

        if dry_run:
            # Just log and save to database
            logger.debug(
                f"[DRY RUN] Would download {case_ref} to {output_dir} "
                f"(category: {metadata.category.value if hasattr(metadata.category, 'value') else metadata.category})"
            )
            metadata.status = ScrapeStatus.PENDING
            await progress.add_case(metadata)
            result["success"] = True
            return result

        # Download HTML and PDF
        output_dir.mkdir(parents=True, exist_ok=True)

        html_success, pdf_success, _ = await downloader.download_case(
            html_url=entry.html_url,
            pdf_url=entry.pdf_url,
            output_dir=output_dir,
        )

        # Update metadata with paths
        if html_success:
            metadata.html_path = str(output_dir / "decision.html")

        if pdf_success:
            metadata.pdf_path = str(output_dir / "decision.pdf")

        # Determine status
        if html_success and pdf_success:
            metadata.status = ScrapeStatus.COMPLETE
            result["success"] = True
        elif html_success or pdf_success:
            metadata.status = ScrapeStatus.HTML_DOWNLOADED if html_success else ScrapeStatus.PDF_DOWNLOADED
            result["success"] = True  # Partial success
        else:
            metadata.status = ScrapeStatus.FAILED
            metadata.error_message = "Failed to download both HTML and PDF"

        metadata.scraped_at = datetime.utcnow()

        # Save case metadata
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)

        # Update progress database
        await progress.add_case(metadata)

        return result

    async def get_statistics(self) -> dict:
        """Get current scraping statistics."""
        async with ProgressTracker(self.config) as progress:
            return await progress.get_statistics()

    async def resume_scraping(self) -> dict:
        """Resume scraping of pending cases."""
        async with ProgressTracker(self.config) as progress:
            pending = await progress.get_pending_cases()

        if not pending:
            logger.info("No pending cases to resume")
            return {"message": "No pending cases"}

        # Group by year
        years = sorted(set(c["year"] for c in pending), reverse=True)
        logger.info(f"Found {len(pending)} pending cases across years: {years}")

        return await self.scrape_years(years, resume=True)


def parse_years(years_str: str, year_range: str) -> List[int]:
    """Parse years from string arguments."""
    years_list = []

    # Parse year range (e.g., "2020-2025")
    if year_range:
        if "-" in year_range:
            start, end = year_range.split("-", 1)
            years_list.extend(range(int(start), int(end) + 1))
        else:
            years_list.append(int(year_range))

    # Parse years string (e.g., "2023 2022 2021" or "2023,2022,2021")
    if years_str:
        # Handle both space and comma separated
        for part in years_str.replace(",", " ").split():
            part = part.strip()
            if part:
                years_list.append(int(part))

    return sorted(set(years_list), reverse=True)


@click.command()
@click.option(
    "--years",
    "-y",
    type=str,
    default="",
    help="Years to scrape, space or comma separated (e.g., '2023 2022 2021' or '2020,2021,2022')",
)
@click.option(
    "--year-range",
    "-r",
    type=str,
    default="",
    help="Year range to scrape (e.g., '2020-2025')",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List cases without downloading",
)
@click.option(
    "--resume",
    is_flag=True,
    help="Resume from last checkpoint",
)
@click.option(
    "--stats",
    is_flag=True,
    help="Show statistics and exit",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    help="Output directory (overrides default)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
def main(
    years: str,
    year_range: str,
    dry_run: bool,
    resume: bool,
    stats: bool,
    output_dir: Optional[str],
    verbose: bool,
):
    """
    BAILII Scraper for UK Tribunal Decisions.

    Scrapes First-tier Tribunal (Property Chamber) decisions from BAILII,
    focusing on tenancy deposit dispute cases.

    Examples:
        python -m scripts.scrapers.bailii_scraper --years "2023 2022 2021"
        python -m scripts.scrapers.bailii_scraper --year-range 2020-2025
        python -m scripts.scrapers.bailii_scraper -y "2023,2022" --dry-run
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Configure
    config = ScraperConfig()
    if output_dir:
        config.output_base_dir = Path(output_dir)

    scraper = BAILIIScraper(config)

    # Run appropriate command
    if stats:
        result = asyncio.run(scraper.get_statistics())
        print("\n=== BAILII Scraper Statistics ===\n")
        print(json.dumps(result, indent=2))
        return

    if resume:
        result = asyncio.run(scraper.resume_scraping())
        return

    # Parse years from arguments
    years_list = parse_years(years, year_range)
    if not years_list:
        years_list = config.default_years
        logger.info(f"No years specified, using defaults: {years_list}")

    result = asyncio.run(scraper.scrape_years(
        years=years_list,
        dry_run=dry_run,
        resume=False,
    ))


if __name__ == "__main__":
    main()
