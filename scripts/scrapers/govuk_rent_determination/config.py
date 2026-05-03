"""SHA-138: GOV.UK FTT(PC) MNR rent-determination scraper configuration.

Forked from the SHA-126 RRO scraper. The RRO sub-category gate and
statutory-grounds allowlist are gone; matter-type inclusion happens via
case-reference parsing (``/MNR/`` segment).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


GOVUK_BASE = "https://www.gov.uk"
GOVUK_SEARCH_API = f"{GOVUK_BASE}/api/search.json"
GOVUK_CONTENT_API = f"{GOVUK_BASE}/api/content"

#: GOV.UK content format we filter on for FTT Property Chamber decisions.
RPT_DECISION_FORMAT = "residential_property_tribunal_decision"

#: Matter-type code embedded in FTT(PC) case references (e.g.
#: ``MAN/00BY/MNR/2024/0123``). Used by ``filter.classify_mnr`` to gate
#: inclusion at the case-reference level.
MNR_MATTER_CODE = "MNR"

#: Parser/version markers persisted to SourceMetadata. Bump on shape change.
PARSER_VERSION = "govuk-mnr-0.1.0"
CORPUS_VERSION = "research_seed_2026_05"
DOMAIN_ID = "housing.rent_determination.v1"
NAMESPACE_ID = "housing_rent_determination_v1"

DEFAULT_USER_AGENT = (
    "ProposerResearchBot/0.1 (legal-mediation-system; +https://github.com/MSH4R1F/proposer)"
)


class ScraperConfig(BaseModel):
    """Configuration knobs for the GOV.UK MNR rent-determination scraper."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    # Output ----------------------------------------------------------------
    output_base_dir: Path = Field(
        default_factory=lambda: Path("data/raw/govuk_rent_determination"),
        description="Root for decisions/, master_index.json, scrape_summary.json.",
    )

    # Pilot bounds ----------------------------------------------------------
    max_keep: int = Field(
        default=50,
        ge=1,
        description="Stop after this many MNR decisions are accepted by the filter.",
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
    matter_code: str = Field(default=MNR_MATTER_CODE)
    decision_format: str = Field(default=RPT_DECISION_FORMAT)

    # Robots.txt -----------------------------------------------------------
    respect_robots_txt: bool = Field(default=True)

    # Run-level metadata ---------------------------------------------------
    run_started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fixture_mode: bool = Field(
        default=False,
        description=(
            "When True the scraper does no live HTTP and reads decisions "
            "from a fixture directory (used in tests)."
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
    "MNR_MATTER_CODE",
    "RPT_DECISION_FORMAT",
]
