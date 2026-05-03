"""Tests for GOV.UK downloader request construction."""

from __future__ import annotations

import asyncio

from scripts.scrapers.govuk_property_tribunal.config import ScraperConfig
from scripts.scrapers.govuk_property_tribunal.downloader import GovUKDownloader


def test_search_does_not_send_unsupported_subcategory_filter():
    config = ScraperConfig()
    downloader = GovUKDownloader(config)
    captured = {}

    class Response:
        def json(self):
            return {"results": [], "total": 0}

    async def fake_request(method, url, *, params=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = dict(params or {})
        return Response()

    downloader._request = fake_request  # type: ignore[method-assign]

    payload = asyncio.run(downloader.search(start=0, count=10))

    assert payload == {"results": [], "total": 0}
    assert captured["method"] == "GET"
    assert captured["url"] == config.search_api_url
    assert captured["params"]["filter_format"] == config.decision_format
    assert "filter_sub_categories" not in captured["params"]
