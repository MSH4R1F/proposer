"""Tests for citation source-URL resolver (SHA-55)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_orchestrator.data import citation_urls
from llm_orchestrator.data.citation_urls import (
    BAILII_BASE,
    reset_corpus_index_cache,
    resolve_source_url,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_corpus_index_cache()
    yield
    reset_corpus_index_cache()


def test_resolve_returns_none_for_empty_reference():
    assert resolve_source_url("") is None
    assert resolve_source_url(None) is None
    assert resolve_source_url("Unknown") is None
    assert resolve_source_url("  unknown  ") is None


def test_fallback_uses_deterministic_bailii_pattern_when_year_present(monkeypatch):
    monkeypatch.setattr(citation_urls, "_corpus_index", lambda: {})
    url = resolve_source_url("LON_00AU_HMF_2022_0046", 2022)
    assert url == f"{BAILII_BASE}/2022/LON_00AU_HMF_2022_0046.html"


def test_fallback_returns_none_when_year_missing(monkeypatch):
    monkeypatch.setattr(citation_urls, "_corpus_index", lambda: {})
    assert resolve_source_url("LON_00AU_HMF_2022_0046", None) is None


def test_corpus_index_lookup_takes_precedence(monkeypatch):
    authoritative = "https://example.bailii.test/canonical.html"
    monkeypatch.setattr(
        citation_urls,
        "_corpus_index",
        lambda: {"LON_00AU_HMF_2022_0046": authoritative},
    )
    assert resolve_source_url("LON_00AU_HMF_2022_0046", 2099) == authoritative


def test_corpus_index_built_from_metadata_files(tmp_path, monkeypatch):
    # Build a fake corpus tree and point the resolver at it.
    bailii = tmp_path / "data" / "raw" / "bailii" / "deposit-cases" / "2022" / "LON_X"
    bailii.mkdir(parents=True)
    meta = {
        "case_reference": "LON_X_2022",
        "html_url": "https://www.bailii.org/uk/cases/UKFTT/PC/2022/LON_X_2022.html",
    }
    (bailii / "metadata.json").write_text(json.dumps(meta))

    # Garbage metadata should be skipped, not crash the index.
    junk = tmp_path / "data" / "raw" / "bailii" / "junk"
    junk.mkdir(parents=True)
    (junk / "metadata.json").write_text("not json")

    monkeypatch.setattr(citation_urls, "_project_root", lambda: tmp_path)
    reset_corpus_index_cache()

    assert resolve_source_url("LON_X_2022") == meta["html_url"]


def test_missing_corpus_dir_falls_back_to_pattern(tmp_path, monkeypatch):
    monkeypatch.setattr(citation_urls, "_project_root", lambda: tmp_path)
    reset_corpus_index_cache()
    # No data/raw/bailii dir exists; index is empty, fallback applies.
    assert (
        resolve_source_url("CHI_00ML_LBC_2022_0009", 2022)
        == f"{BAILII_BASE}/2022/CHI_00ML_LBC_2022_0009.html"
    )


# ---------------------------------------------------------------------------
# SHA-20 Phase 4: resolve_citation_url delegates to per-publisher mapper.
# ---------------------------------------------------------------------------


from datetime import date  # noqa: E402

from domain_core.spec import SourceKind, SourcePublisher  # noqa: E402

from llm_orchestrator.data.citation_urls import resolve_citation_url  # noqa: E402


def test_resolve_citation_url_handles_govuk_decision():
    url = resolve_citation_url(
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        source_id="lon-00xy-2024-001",
    )
    assert url == "https://www.gov.uk/residential-property-tribunal-decisions/lon-00xy-2024-001"


def test_resolve_citation_url_handles_legislation_with_as_of():
    url = resolve_citation_url(
        source_publisher=SourcePublisher.LEGISLATION_GOV_UK,
        source_kind=SourceKind.STATUTE,
        source_id="ukpga/2004/34/section/213",
        as_of=date(2012, 4, 6),
    )
    assert url == "https://www.legislation.gov.uk/ukpga/2004/34/section/213/2012-04-06"


def test_resolve_citation_url_handles_internal_uri():
    url = resolve_citation_url(
        source_publisher=SourcePublisher.INTERNAL,
        source_kind=SourceKind.USER_EVIDENCE,
        source_id="upload-1",
    )
    assert url == "proposer://internal/upload-1"


def test_resolve_citation_url_bailii_path_uses_legacy_resolver(monkeypatch):
    monkeypatch.setattr(citation_urls, "_corpus_index", lambda: {})
    url = resolve_citation_url(
        source_publisher=SourcePublisher.BAILII,
        source_kind=SourceKind.CASE_DECISION,
        source_id="LON_00AU_HMF_2022_0046",
        year=2022,
    )
    assert url == f"{BAILII_BASE}/2022/LON_00AU_HMF_2022_0046.html"
