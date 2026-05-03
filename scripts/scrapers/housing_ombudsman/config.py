"""Config for the Housing Ombudsman scraper (SHA-125).

This is a *pilot* scraper, capped by ``max_keep`` (default 30) so we never
hammer the site. All request settings are conservative: 1 rps, 2 concurrent
connections, exponential back-off on 429/503.

Output paths are relative to the project root; the scraper resolves them via
``project_root`` so this works the same in the worktree (where data/raw is a
symlink) and in CI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Default repo root: walk up from this file (scripts/scrapers/housing_ombudsman/config.py).
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ScraperConfig:
    """Polite, bounded config for the Housing Ombudsman scraper."""

    # Source URL
    base_url: str = "https://www.housing-ombudsman.org.uk"
    decisions_path: str = "/decisions/"

    # Throttle / concurrency (be polite to the Ombudsman site)
    requests_per_second: float = 1.0
    max_concurrent_requests: int = 2
    request_timeout_s: float = 30.0

    # Pilot bound — never fetch more than this many *kept* decisions.
    # We may visit more listings to find them, but we stop once kept = max_keep.
    max_keep: int = 30
    # Listing pages to crawl at most (defensive upper bound).
    max_listing_pages: int = 20

    # Retry settings
    max_retries: int = 4
    retry_min_wait_s: float = 1.0
    retry_max_wait_s: float = 30.0

    # Identity / compliance
    user_agent: str = (
        "ProposerResearchBot/0.1 (+https://github.com/MSH4R1F/proposer; "
        "academic research on UK housing ombudsman decisions; "
        "contact via repo issues)"
    )
    respect_robots: bool = True

    # Output
    project_root: Path = field(default_factory=lambda: _DEFAULT_PROJECT_ROOT)
    output_subdir: str = "data/raw/housing_ombudsman"

    # Pre-ingest licence gate. Until external redistribution permission is
    # confirmed, this is the value emitted onto every SourceMetadata so
    # downstream code can refuse to publish snippets externally.
    source_license: str = "unknown_housing_ombudsman_decisions_permission_pending"

    # Corpus version — must match the YAML
    # (housing_repairs_social_v1.retrieval_namespaces[0].corpus_version).
    corpus_version: str = "research_seed_2026_05"

    def __post_init__(self) -> None:
        # Allow env overrides for the most common knobs.
        if env := os.getenv("OMBUDSMAN_RATE_LIMIT"):
            try:
                self.requests_per_second = float(env)
            except ValueError:
                pass
        if env := os.getenv("OMBUDSMAN_MAX_KEEP"):
            try:
                self.max_keep = int(env)
            except ValueError:
                pass
        if env := os.getenv("OMBUDSMAN_PROJECT_ROOT"):
            self.project_root = Path(env)

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
        return self.output_dir / "SOURCE_RIGHTS.md"

    @property
    def listing_url(self) -> str:
        return f"{self.base_url}{self.decisions_path}"

    @property
    def robots_url(self) -> str:
        return f"{self.base_url}/robots.txt"


__all__ = ["ScraperConfig"]
