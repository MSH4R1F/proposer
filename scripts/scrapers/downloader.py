"""
Async download manager for BAILII scraper.

Handles rate-limited, resilient downloads of HTML and PDF content.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
import aiofiles
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .config import ScraperConfig

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Custom exception for download failures."""

    def __init__(self, url: str, message: str, status_code: Optional[int] = None):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Download failed for {url}: {message}")


class AsyncDownloader:
    """
    Async download manager with rate limiting and retries.

    Features:
    - Rate limiting (configurable requests per second)
    - Exponential backoff retries
    - Concurrent download limiting
    - Progress tracking
    """

    def __init__(self, config: ScraperConfig):
        self.config = config

        # Rate limiter: requests per second
        self.rate_limiter = AsyncLimiter(
            max_rate=config.requests_per_second,
            time_period=1.0,
        )

        # Semaphore for concurrent request limiting
        self.semaphore = asyncio.Semaphore(config.max_concurrent_requests)

        # Session will be created in context manager
        self._session: Optional[aiohttp.ClientSession] = None

        # Stats
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.bytes_downloaded = 0

    async def __aenter__(self):
        """Create aiohttp session."""
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get the aiohttp session."""
        if not self._session:
            raise RuntimeError(
                "Downloader not initialized. Use 'async with' context manager."
            )
        return self._session

    async def fetch_html(self, url: str) -> str:
        """
        Fetch HTML content from URL.

        Args:
            url: URL to fetch

        Returns:
            HTML content as string

        Raises:
            DownloadError: If download fails after retries
        """
        return await self._fetch_with_retry(url, binary=False)

    async def fetch_pdf(self, url: str) -> bytes:
        """
        Fetch PDF content from URL.

        Args:
            url: URL to fetch

        Returns:
            PDF content as bytes

        Raises:
            DownloadError: If download fails after retries
        """
        return await self._fetch_with_retry(url, binary=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _fetch_with_retry(self, url: str, binary: bool = False):
        """
        Fetch URL with rate limiting, retries, and concurrency control.

        Args:
            url: URL to fetch
            binary: If True, return bytes; otherwise return text

        Returns:
            Content as string or bytes
        """
        async with self.semaphore:
            await self.rate_limiter.acquire()

            self.total_requests += 1
            logger.debug(f"Fetching: {url}")

            try:
                async with self.session.get(url) as response:
                    if response.status == 404:
                        raise DownloadError(url, "Not found", 404)

                    if response.status != 200:
                        raise DownloadError(
                            url,
                            f"HTTP {response.status}",
                            response.status,
                        )

                    if binary:
                        content = await response.read()
                        self.bytes_downloaded += len(content)
                    else:
                        # Read as bytes first, then decode with fallback
                        raw_bytes = await response.read()
                        self.bytes_downloaded += len(raw_bytes)

                        # Try detected encoding, fall back to latin-1 (never fails)
                        encoding = response.charset or 'utf-8'
                        try:
                            content = raw_bytes.decode(encoding)
                        except (UnicodeDecodeError, LookupError):
                            try:
                                content = raw_bytes.decode('utf-8', errors='replace')
                            except UnicodeDecodeError:
                                content = raw_bytes.decode('latin-1')

                    self.successful_requests += 1
                    return content

            except aiohttp.ClientError as e:
                self.failed_requests += 1
                logger.warning(f"Request failed for {url}: {e}")
                raise

            except asyncio.TimeoutError:
                self.failed_requests += 1
                logger.warning(f"Request timeout for {url}")
                raise

    async def download_file(
        self,
        url: str,
        output_path: Path,
        binary: bool = True,
    ) -> bool:
        """
        Download a file and save to disk.

        Args:
            url: URL to download
            output_path: Path to save file
            binary: Whether to treat as binary file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if binary:
                content = await self.fetch_pdf(url)
                async with aiofiles.open(output_path, "wb") as f:
                    await f.write(content)
            else:
                content = await self.fetch_html(url)
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write(content)

            logger.debug(f"Saved: {output_path}")
            return True

        except DownloadError as e:
            logger.error(f"Download failed: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            return False

    async def download_case(
        self,
        html_url: str,
        pdf_url: str,
        output_dir: Path,
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        Download both HTML and PDF for a case.

        Args:
            html_url: URL to HTML version
            pdf_url: URL to PDF version
            output_dir: Directory to save files

        Returns:
            Tuple of (html_success, pdf_success, html_content)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        html_path = output_dir / "decision.html"
        pdf_path = output_dir / "decision.pdf"

        html_content: Optional[str] = None
        html_success = False
        pdf_success = False

        # Download HTML
        try:
            html_content = await self.fetch_html(html_url)
            async with aiofiles.open(html_path, "w", encoding="utf-8") as f:
                await f.write(html_content)
            html_success = True
            logger.debug(f"Downloaded HTML: {html_path}")
        except Exception as e:
            logger.warning(f"Failed to download HTML {html_url}: {e}")

        # Download PDF
        try:
            pdf_content = await self.fetch_pdf(pdf_url)
            async with aiofiles.open(pdf_path, "wb") as f:
                await f.write(pdf_content)
            pdf_success = True
            logger.debug(f"Downloaded PDF: {pdf_path}")
        except Exception as e:
            logger.warning(f"Failed to download PDF {pdf_url}: {e}")

        return html_success, pdf_success, html_content

    def get_stats(self) -> dict:
        """Get download statistics."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "bytes_downloaded": self.bytes_downloaded,
            "success_rate": (
                self.successful_requests / self.total_requests * 100
                if self.total_requests > 0
                else 0
            ),
        }


async def check_robots_txt(config: ScraperConfig) -> bool:
    """
    Check if scraping is allowed by robots.txt.

    Args:
        config: Scraper configuration

    Returns:
        True if scraping is allowed
    """
    try:
        from robotexclusionrulesparser import RobotExclusionRulesParser

        async with aiohttp.ClientSession() as session:
            robots_url = f"{config.base_url}/robots.txt"
            async with session.get(robots_url) as response:
                if response.status != 200:
                    logger.warning(f"Could not fetch robots.txt: {response.status}")
                    return True  # Assume allowed if not found

                content = await response.text()

        parser = RobotExclusionRulesParser()
        parser.parse(content)

        # Check if our user agent is allowed to access the path
        allowed = parser.is_allowed(
            config.user_agent.split("/")[0],  # Use bot name
            config.ukftt_pc_path,
        )

        if not allowed:
            logger.warning("Scraping not allowed by robots.txt")
        else:
            logger.info("Scraping allowed by robots.txt")

        return allowed

    except ImportError:
        logger.warning("robotexclusionrulesparser not installed, skipping check")
        return True

    except Exception as e:
        logger.warning(f"Error checking robots.txt: {e}")
        return True  # Proceed with caution
