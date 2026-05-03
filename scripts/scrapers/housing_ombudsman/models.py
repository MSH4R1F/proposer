"""Pydantic models for the Housing Ombudsman scraper.

We keep these models intentionally separate from the SourceDocument /
SourceMetadata contract so the scraper can collect publisher-specific
fields (outcome label, complaint categories, orders, recommendations)
without polluting the cross-domain ingestion schema. The bridge to
``SourceDocument`` lives in ``to_source_document.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# Outcomes we currently know how to normalize. Anything else stays as
# ``outcome_raw`` and ``outcome_normalized=None``; we never fail the scrape.
KNOWN_OUTCOMES = {
    "severe-maladministration",
    "maladministration",
    "partial-maladministration",
    "no-maladministration",
}


class ListingEntry(BaseModel):
    """A single row pulled from the listing page (pre-detail)."""

    model_config = ConfigDict(extra="forbid")

    case_reference: str
    detail_url: str
    listed_date: Optional[date] = None
    listed_title: Optional[str] = None
    listed_landlord: Optional[str] = None
    listed_outcome_raw: Optional[str] = None
    listed_categories: List[str] = Field(default_factory=list)


class OmbudsmanCaseMetadata(BaseModel):
    """Parsed metadata for one Housing Ombudsman determination."""

    model_config = ConfigDict(extra="forbid")

    case_reference: str
    decision_date: Optional[date] = None
    landlord_name: Optional[str] = None
    complaint_categories: List[str] = Field(default_factory=list)
    outcome_raw: Optional[str] = None
    outcome_normalized: Optional[str] = None
    orders: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    source_url: str
    raw_storage_path: Optional[str] = None
    title: Optional[str] = None

    # Heuristic markers we pick up without making them load-bearing.
    temporal_markers: Dict[str, Any] = Field(default_factory=dict)

    # Diagnostics from the parser (e.g. unrecognised outcome label).
    parser_diagnostics: List[str] = Field(default_factory=list)


__all__ = ["ListingEntry", "OmbudsmanCaseMetadata", "KNOWN_OUTCOMES"]
