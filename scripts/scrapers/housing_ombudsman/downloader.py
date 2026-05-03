"""Async HTTP downloader for the Housing Ombudsman scraper.

Polite by construction:

* ``httpx.AsyncClient`` with a custom User-Agent.
* Token-bucket rate limit (``requests_per_second``).
* Bounded concurrency via :class:`asyncio.Semaphore`.
* :mod:`tenacity` retry with exponential backoff on 429/503/network errors.
* Optional ``robots.txt`` honoring (default on).

The site is read-only HTML; we never POST anywhere.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Optional
from urllib import robotparser

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import ScraperConfig
from .parsers import find_next_listing_page

logger = logging.getLogger(__name__)


class OmbudsmanFetchError(Exception):
    """Raised when a fetch fails after retries or is blocked by robots."""


class _TokenBucket:
    """Simple token bucket so we can pace at fractional rates (e.g. 0.5 rps)."""

    def __init__(self, rate_per_second: float, capacity: Optional[float] = None) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be > 0")
        self._rate = float(rate_per_second)
        self._capacity = float(capacity if capacity is not None else max(1.0, rate_per_second))
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, n: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._last = now
                if self._tokens >= n:
                    self._tokens -= n
                    return
                # Need (n - tokens) / rate seconds.
                deficit = n - self._tokens
                await asyncio.sleep(deficit / self._rate)


class OmbudsmanDownloader:
    """Polite async downloader for the Housing Ombudsman public site."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._sem = asyncio.Semaphore(config.max_concurrent_requests)
        self._bucket = _TokenBucket(config.requests_per_second)
        self._robots: Optional[robotparser.RobotFileParser] = None
        self._robots_checked = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "OmbudsmanDownloader":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.request_timeout_s,
                headers={"User-Agent": self.config.user_agent},
                follow_redirects=True,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    async def _ensure_robots(self) -> None:
        if self._robots_checked or not self.config.respect_robots:
            self._robots_checked = True
            return
        await self._ensure_client()
        assert self._client is not None
        rp = robotparser.RobotFileParser()
        rp.set_url(self.config.robots_url)
        try:
            resp = await self._client.get(self.config.robots_url)
            if resp.status_code < 400 and resp.text:
                rp.parse(resp.text.splitlines())
                self._robots = rp
            else:
                logger.warning(
                    "robots.txt fetch returned status=%s; proceeding without restrictions",
                    resp.status_code,
                )
        except Exception as e:  # network blip — fail-open is acceptable
            logger.warning("robots.txt fetch failed: %s; proceeding without restrictions", e)
        finally:
            self._robots_checked = True

    def _allowed(self, url: str) -> bool:
        if not self.config.respect_robots or self._robots is None:
            return True
        return self._robots.can_fetch(self.config.user_agent, url)

    # ------------------------------------------------------------------
    # HTML fetch
    # ------------------------------------------------------------------

    async def get_html(self, url: str) -> str:
        """Fetch a URL and return decoded HTML, with polite pacing+retry."""
        await self._ensure_client()
        await self._ensure_robots()
        if not self._allowed(url):
            raise OmbudsmanFetchError(f"robots.txt disallows {url}")
        assert self._client is not None

        async with self._sem:
            await self._bucket.acquire()
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(self.config.max_retries),
                    wait=wait_exponential(
                        multiplier=self.config.retry_min_wait_s,
                        max=self.config.retry_max_wait_s,
                    ),
                    retry=retry_if_exception_type(
                        (httpx.HTTPError, OmbudsmanFetchError)
                    ),
                    reraise=True,
                ):
                    with attempt:
                        resp = await self._client.get(url)
                        if resp.status_code in (429, 503):
                            raise OmbudsmanFetchError(
                                f"rate-limited {resp.status_code} on {url}"
                            )
                        resp.raise_for_status()
                        return resp.text
            except RetryError as e:
                raise OmbudsmanFetchError(f"giving up on {url}: {e}") from e
        # Should not reach here.
        raise OmbudsmanFetchError(f"no response for {url}")

    # ------------------------------------------------------------------
    # Listing pagination
    # ------------------------------------------------------------------

    async def fetch_listing_pages(self) -> AsyncIterator[str]:
        """Yield raw HTML for each listing page until no next-link is found."""
        url: Optional[str] = self.config.listing_url
        pages_visited = 0
        while url and pages_visited < self.config.max_listing_pages:
            html = await self.get_html(url)
            yield html
            pages_visited += 1
            url = find_next_listing_page(html, base_url=self.config.base_url)


__all__ = ["OmbudsmanDownloader", "OmbudsmanFetchError"]
