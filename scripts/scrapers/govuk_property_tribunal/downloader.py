"""SHA-126: async, polite GOV.UK downloader for the RRO scraper.

Three responsibilities:

* Throttle outbound requests to ``config.requests_per_second`` (token
  bucket via :class:`asyncio.Semaphore` plus a per-second sleep).
* Honour ``robots.txt`` when ``config.respect_robots_txt`` is True.
* Retry transient failures (5xx and 429) with exponential backoff via
  :mod:`tenacity`.

The downloader is *thin*: it returns raw bytes / text / parsed JSON so
the parsers stay decoupled from the I/O layer. All HTTP I/O goes through
a single :class:`httpx.AsyncClient` so connection pooling kicks in and
we do not stampede GOV.UK on resume runs.
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.robotparser
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import GOVUK_BASE, ScraperConfig
from .models import ArtefactKind

logger = logging.getLogger(__name__)


_RETRY_STATUS = {429, 500, 502, 503, 504}


class _RetryableHTTPError(Exception):
    """Raised when we should retry after a 429/5xx response."""


class GovUKDownloader:
    """Polite async downloader for GOV.UK search/content/asset URLs."""

    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._min_interval = 1.0 / max(config.requests_per_second, 1e-3)
        self._last_request_at = 0.0
        self._rate_lock = asyncio.Lock()
        self._robots_cache: Dict[str, urllib.robotparser.RobotFileParser] = {}

    # ------------------------------------------------------------------
    async def __aenter__(self) -> "GovUKDownloader":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._config.request_timeout_s,
                headers={"User-Agent": self._config.user_agent},
                follow_redirects=True,
            )

    # ------------------------------------------------------------------
    async def _rate_gate(self) -> None:
        async with self._rate_lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    # ------------------------------------------------------------------
    async def _allowed_by_robots(self, url: str) -> bool:
        if not self._config.respect_robots_txt:
            return True
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._robots_cache.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(urljoin(host, "/robots.txt"))
            try:
                # ``read()`` is sync but small — run in the default executor.
                await asyncio.to_thread(rp.read)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("robots_fetch_failed", extra={"host": host, "error": str(exc)})
                rp = urllib.robotparser.RobotFileParser()  # empty -> allow all
            self._robots_cache[host] = rp
        return rp.can_fetch(self._config.user_agent, url)

    # ------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        await self._ensure_client()
        if not await self._allowed_by_robots(url):
            raise PermissionError(f"robots.txt disallows {url}")

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=1.0, min=1, max=20),
            retry=retry_if_exception_type((_RetryableHTTPError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with self._semaphore:
                    await self._rate_gate()
                    assert self._client is not None
                    resp = await self._client.request(method, url, params=params)
                    if resp.status_code in _RETRY_STATUS:
                        raise _RetryableHTTPError(
                            f"{resp.status_code} for {url}: {resp.text[:200]}"
                        )
                    resp.raise_for_status()
                    return resp
        raise RuntimeError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------
    async def search(self, *, start: int, count: int) -> Dict[str, Any]:
        """Page through GOV.UK ``/api/search.json``.

        Returns the raw JSON payload; :func:`parse_search_response`
        flattens it.
        """
        params = {
            "filter_format": self._config.decision_format,
            "count": count,
            "start": start,
            "order": "-public_timestamp",
        }
        resp = await self._request("GET", self._config.search_api_url, params=params)
        return resp.json()

    # ------------------------------------------------------------------
    async def fetch_content(self, base_path: str) -> Dict[str, Any]:
        """Fetch ``/api/content/<base_path>`` JSON for one decision."""
        path = base_path.lstrip("/")
        url = f"{self._config.content_api_url}/{path}"
        resp = await self._request("GET", url)
        return resp.json()

    # ------------------------------------------------------------------
    async def fetch_html(self, url: str) -> str:
        """Fetch a stand-alone HTML decision page (fallback)."""
        if not url.startswith("http"):
            url = urljoin(GOVUK_BASE + "/", url.lstrip("/"))
        resp = await self._request("GET", url)
        return resp.text

    # ------------------------------------------------------------------
    async def download_asset(self, url: str, dest: Path) -> ArtefactKind:
        """Download an asset (PDF / DOCX / HTML) to disk.

        Returns the inferred :class:`ArtefactKind` based on filename and
        content-type. Caller is responsible for placing ``dest`` in the
        correct decision directory.
        """
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        resp = await self._request("GET", url)
        content_type = (resp.headers.get("content-type") or "").lower()
        # Re-use the same heuristic from parsers, but inline to avoid
        # circular imports.
        kind = ArtefactKind.HTML
        name_lc = url.lower()
        if name_lc.endswith(".pdf") or "pdf" in content_type:
            kind = ArtefactKind.PDF
        elif name_lc.endswith(".docx") or name_lc.endswith(".doc") or "word" in content_type:
            kind = ArtefactKind.DOCX
        elif name_lc.endswith(".html") or name_lc.endswith(".htm") or "html" in content_type:
            kind = ArtefactKind.HTML
        elif "json" in content_type:
            kind = ArtefactKind.JSON

        if kind in (ArtefactKind.PDF, ArtefactKind.DOCX):
            dest.write_bytes(resp.content)
        else:
            dest.write_text(resp.text, encoding="utf-8")
        return kind


__all__ = ["GovUKDownloader"]
