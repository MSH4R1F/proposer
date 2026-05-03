"""SHA-125 Housing Ombudsman scraper package.

Scrapes a polite, bounded sample of Housing Ombudsman determinations
from https://www.housing-ombudsman.org.uk/decisions/, filters to
repairs/damp/mould/disrepair matters, and emits ``SourceDocument`` records
keyed to the ``housing_repairs_social_v1`` retrieval namespace.
"""

PARSER_VERSION = "ombudsman-0.1.0"

__all__ = ["PARSER_VERSION"]
