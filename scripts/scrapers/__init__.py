"""
BAILII Scraper Package

A production-ready async scraper for collecting UK First-tier Tribunal
(Property Chamber) decisions from BAILII, with focus on tenancy deposit disputes.
"""

__version__ = "0.1.0"
__author__ = "Mohamed Sharif"

from .config import ScraperConfig
from .models import CaseMetadata, CaseCategory, ScrapeProgress
from .bailii_scraper import BAILIIScraper

__all__ = [
    "ScraperConfig",
    "CaseMetadata",
    "CaseCategory",
    "ScrapeProgress",
    "BAILIIScraper",
]
