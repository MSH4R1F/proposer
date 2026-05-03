"""
BAILII Scraper Package

A production-ready async scraper for collecting UK First-tier Tribunal
(Property Chamber) decisions from BAILII, with focus on tenancy deposit disputes.
"""

__version__ = "0.1.0"
__author__ = "Mohamed Sharif"


__all__ = [
    "ScraperConfig",
    "CaseMetadata",
    "CaseCategory",
    "ScrapeProgress",
    "BAILIIScraper",
]


def __getattr__(name):  # PEP 562 lazy attribute resolution
    if name == "ScraperConfig":
        from .config import ScraperConfig as _ScraperConfig
        return _ScraperConfig
    if name in {"CaseMetadata", "CaseCategory", "ScrapeProgress"}:
        from . import models as _models
        return getattr(_models, name)
    if name == "BAILIIScraper":
        from .bailii_scraper import BAILIIScraper as _BAILIIScraper
        return _BAILIIScraper
    raise AttributeError(name)
