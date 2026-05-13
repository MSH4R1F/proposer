"""Config for the GOV.UK Employment Tribunal scraper (SHA-145 / SHA-65a).

Polite, bounded pilot config. Defaults stay conservative — 0.5 rps, 2 concurrent
connections — so that an accidental run in CI does not hammer GOV.UK. Live
scrapes set ``EMPLOYMENT_MAX_KEEP`` and ``EMPLOYMENT_RATE_LIMIT`` via env per
the spec.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import OGL_V3_LICENCE_ID

# Walk up from this file: scripts/scrapers/employment_tribunal/config.py
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ScraperConfig:
    """Polite, bounded config for the GOV.UK ET scraper."""

    # Source URLs ---------------------------------------------------------
    base_url: str = "https://www.gov.uk"
    decisions_path: str = "/employment-tribunal-decisions"

    # GOV.UK exposes a category filter via a query parameter on the listing
    # page. Stage 1 of the two-stage filter uses this slug to pre-narrow.
    jurisdiction_category_slug: str = "unfair-dismissal"
    jurisdiction_category_qs_key: str = "tribunal_decision_categories"

    # Date window for the corpus (spec §5.1 / §6.1): 2019-2024 inclusive.
    years_from: int = 2019
    years_to: int = 2024

    # Throttle / concurrency (spec §8.6) ---------------------------------
    requests_per_second: float = 0.5
    max_concurrent_requests: int = 2
    request_timeout_s: float = 30.0

    # Pilot bounds -------------------------------------------------------
    # Capped at 30 by default — matches SHA-146 pilot. SHA-147 overrides via
    # env or CLI to ~1000.
    max_keep: int = 30
    max_listing_pages: int = 50

    # Retry settings (tenacity) ------------------------------------------
    max_retries: int = 4
    retry_min_wait_s: float = 1.0
    retry_max_wait_s: float = 30.0

    # Identity / compliance ---------------------------------------------
    user_agent: str = (
        "ProposerResearchBot/0.1 (+https://github.com/MSH4R1F/proposer; "
        "academic research on UK Employment Tribunal decisions; "
        "contact via repo issues)"
    )
    respect_robots: bool = True

    # Output -------------------------------------------------------------
    project_root: Path = field(default_factory=lambda: _DEFAULT_PROJECT_ROOT)
    output_subdir: str = "data/raw/employment"

    # Default observed licence. The scraper must replace this with what a
    # page footer says when a page departs from OGL v3.0 — but the GOV.UK
    # Employment Tribunal corpus is uniformly OGL v3.0 today.
    source_license: str = OGL_V3_LICENCE_ID

    # Corpus version — must match the YAML
    # (employment.unfair_dismissal.v1.retrieval_namespaces[0].corpus_version).
    corpus_version: str = "research_seed_2026_05"

    def __post_init__(self) -> None:
        if env := os.getenv("EMPLOYMENT_RATE_LIMIT"):
            try:
                self.requests_per_second = float(env)
            except ValueError:
                pass
        if env := os.getenv("EMPLOYMENT_MAX_KEEP"):
            try:
                self.max_keep = int(env)
            except ValueError:
                pass
        if env := os.getenv("EMPLOYMENT_PROJECT_ROOT"):
            self.project_root = Path(env)
        if env := os.getenv("EMPLOYMENT_YEARS_FROM"):
            try:
                self.years_from = int(env)
            except ValueError:
                pass
        if env := os.getenv("EMPLOYMENT_YEARS_TO"):
            try:
                self.years_to = int(env)
            except ValueError:
                pass

    # ---- Resolved paths -------------------------------------------------

    @property
    def output_dir(self) -> Path:
        return self.project_root / self.output_subdir

    @property
    def decisions_dir(self) -> Path:
        return self.output_dir / "decisions"

    @property
    def runs_dir(self) -> Path:
        return self.output_dir / "_runs"

    @property
    def master_index_path(self) -> Path:
        return self.output_dir / "master_index.json"

    @property
    def excluded_path(self) -> Path:
        return self.output_dir / "excluded.jsonl"

    @property
    def scrape_summary_path(self) -> Path:
        return self.output_dir / "scrape_summary.json"

    @property
    def source_rights_path(self) -> Path:
        # Matches `housing_ombudsman.config.ScraperConfig.source_rights_path`
        # and the existing project gitignore allowlist for
        # data/raw/**/SOURCE_RIGHTS.md.
        return self.output_dir / "SOURCE_RIGHTS.md"

    @property
    def listing_url(self) -> str:
        return f"{self.base_url}{self.decisions_path}"

    @property
    def robots_url(self) -> str:
        return f"{self.base_url}/robots.txt"


__all__ = ["ScraperConfig"]
