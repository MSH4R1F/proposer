"""SHA-126: GOV.UK Property Tribunal RRO scraper configuration.

A small, immutable Pydantic config that the scraper, downloader, and
filter all read from. Defaults are tuned for a pilot run (≤30 kept
docs) at ≤1 rps.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


GOVUK_BASE = "https://www.gov.uk"
GOVUK_SEARCH_API = f"{GOVUK_BASE}/api/search.json"
GOVUK_CONTENT_API = f"{GOVUK_BASE}/api/content"

#: Live sub-category slug for RRO decisions (audit D4).
RRO_SUB_CATEGORY = (
    "housing-act-2004-and-housing-and-planning-act-2016---rent-repayment-orders"
)

#: GOV.UK content format we filter on for FTT Property Chamber decisions.
RPT_DECISION_FORMAT = "residential_property_tribunal_decision"

#: Parser/version markers persisted to SourceMetadata. Bump on shape change.
PARSER_VERSION = "govuk-rro-0.1.0"
CORPUS_VERSION = "research_seed_2026_05"
DOMAIN_ID = "housing.property_chamber.rro.v1"
NAMESPACE_ID = "housing_property_chamber_rro_v1"

DEFAULT_USER_AGENT = (
    "ProposerResearchBot/0.1 (legal-mediation-system; +https://github.com/MSH4R1F/proposer)"
)


class ScraperConfig(BaseModel):
    """Configuration knobs for the GOV.UK RRO pilot scraper."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    # Output ----------------------------------------------------------------
    output_base_dir: Path = Field(
        default_factory=lambda: Path("data/raw/govuk_property_tribunal"),
        description="Root for decisions/, master_index.json, scrape_summary.json.",
    )

    # Pilot bounds ----------------------------------------------------------
    max_keep: int = Field(
        default=30,
        ge=1,
        description="Stop after this many RRO decisions are accepted by the filter.",
    )
    max_pages: int = Field(
        default=20,
        ge=1,
        description="Hard cap on GOV.UK search pages walked.",
    )
    page_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="GOV.UK search ``count`` per page.",
    )

    # HTTP / politeness -----------------------------------------------------
    requests_per_second: float = Field(
        default=1.0,
        gt=0,
        description="Polite throttle ceiling (per host).",
    )
    max_concurrent_requests: int = Field(default=2, ge=1, le=8)
    request_timeout_s: float = Field(default=30.0, gt=0)
    user_agent: str = Field(default=DEFAULT_USER_AGENT)

    # API endpoints --------------------------------------------------------
    search_api_url: str = Field(default=GOVUK_SEARCH_API)
    content_api_url: str = Field(default=GOVUK_CONTENT_API)
    sub_category: str = Field(default=RRO_SUB_CATEGORY)
    decision_format: str = Field(default=RPT_DECISION_FORMAT)

    # Robots.txt -----------------------------------------------------------
    respect_robots_txt: bool = Field(default=True)

    # Run-level metadata ---------------------------------------------------
    run_started_at: datetime = Field(default_factory=datetime.utcnow)
    fixture_mode: bool = Field(
        default=False,
        description=(
            "When True the scraper does no live HTTP and reads decisions "
            "from a fixture directory (used in tests / for the rate-"
            "limited fallback path documented in SOURCE_RIGHTS.md)."
        ),
    )
    fixture_dir: Optional[Path] = Field(
        default=None,
        description="Directory holding fixture *.html / *.json / *.pdf for fixture_mode.",
    )

    # Derived paths --------------------------------------------------------
    @property
    def decisions_dir(self) -> Path:
        return self.output_base_dir / "decisions"

    @property
    def master_index_path(self) -> Path:
        return self.output_base_dir / "master_index.json"

    @property
    def scrape_summary_path(self) -> Path:
        return self.output_base_dir / "scrape_summary.json"

    @property
    def excluded_path(self) -> Path:
        return self.output_base_dir / "excluded.jsonl"

    @property
    def unsupported_path(self) -> Path:
        return self.output_base_dir / "unsupported.jsonl"

    @property
    def progress_log_path(self) -> Path:
        return self.output_base_dir / "run_log.jsonl"


__all__ = [
    "ScraperConfig",
    "PARSER_VERSION",
    "CORPUS_VERSION",
    "DOMAIN_ID",
    "NAMESPACE_ID",
    "GOVUK_BASE",
    "GOVUK_SEARCH_API",
    "GOVUK_CONTENT_API",
    "RRO_SUB_CATEGORY",
    "RPT_DECISION_FORMAT",
]
