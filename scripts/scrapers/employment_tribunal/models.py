"""Pydantic models for the GOV.UK Employment Tribunal scraper.

Kept separate from the cross-domain ``SourceDocument`` / ``SourceMetadata``
contract so the scraper can collect publisher-specific fields (jurisdiction
codes, country, attachments, hearing type, deciding judge) without polluting
the ingestion schema. The bridge to ``SourceDocument`` lives in
``to_source_document.py``.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Country(str, Enum):
    """ET jurisdiction country (decisions are E&W *or* Scotland)."""

    ENGLAND_AND_WALES = "england_and_wales"
    SCOTLAND = "scotland"
    UNKNOWN = "unknown"


# Fair-reason categories under Employment Rights Act 1996 s98(1)-(2). The
# scraper records the raw label from the decision; downstream normalisation
# (factor extraction) lives in SHA-149.
KNOWN_FAIR_REASON_CATEGORIES = {
    "conduct",
    "capability",
    "redundancy",
    "illegality",
    "some-other-substantial-reason",
    "sosr",
}


# Outcome flavour we track at the scraper layer (Stage 2 filter consumes this).
# Anything not recognised stays as ``outcome_raw`` and ``outcome_normalized=None``.
KNOWN_OUTCOMES = {
    "claim-succeeded",  # claimant won on the unfair-dismissal head
    "claim-dismissed",  # respondent won
    "partial-success",  # mixed result across heads
    "withdrawn",  # claimant withdrew before merits
    "struck-out",  # case struck out (procedural)
    "preliminary",  # preliminary issue / case-management only
    "default-judgment",  # respondent did not respond
    "remedy-only",  # remedy hearing with no liability reasoning
    "reconsideration",  # reconsideration of an earlier judgment
    "jurisdiction-only",  # jurisdiction decision only
}


class ETAttachment(BaseModel):
    """A single attachment URL on a GOV.UK decision page.

    GOV.UK decisions almost always carry one or more PDF attachments
    containing the full reserved judgment text. Listing metadata alone
    is not enough to do merits-quality filtering — Stage 2 needs the
    body text.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    title: Optional[str] = None
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None


class ListingEntry(BaseModel):
    """A single row pulled from the GOV.UK ET listing/search results."""

    model_config = ConfigDict(extra="forbid")

    case_reference: str = Field(
        ..., description="GOV.UK content_id or page-derived stable identifier."
    )
    detail_url: str = Field(..., description="Canonical /employment-tribunal-decisions/<slug> URL.")
    base_path: Optional[str] = Field(
        None, description="GOV.UK base path (without scheme/host) — stable id."
    )
    title: Optional[str] = None
    listed_date: Optional[date] = None
    listed_categories: List[str] = Field(
        default_factory=list,
        description="Raw jurisdiction/category labels surfaced on the listing.",
    )
    country_hint: Country = Country.UNKNOWN


class ETCaseMetadata(BaseModel):
    """Parsed metadata for one GOV.UK Employment Tribunal decision.

    Captures everything the scraper sees on the public page. Filter stages
    consume ``jurisdiction_codes`` (Stage 1) and ``raw_text`` plus
    ``outcome_raw`` (Stage 2). The downstream SourceDocument bridge in
    ``to_source_document.py`` projects a subset of these into the canonical
    ``SourceMetadata`` shape.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    case_reference: str = Field(..., description="Stable identifier per GOV.UK base path / content_id.")
    title: Optional[str] = None
    source_url: str
    base_path: Optional[str] = None

    # Case fields
    case_numbers: List[str] = Field(
        default_factory=list,
        description="ET-issued case numbers, e.g. '2200001/2024'.",
    )
    decision_date: Optional[date] = None
    country: Country = Country.UNKNOWN

    # Categorisation
    jurisdiction_codes: List[str] = Field(
        default_factory=list,
        description="Raw GOV.UK jurisdiction labels for the decision (e.g. 'Unfair Dismissal').",
    )

    # Outcome (raw as parsed; normalised when recognisable)
    outcome_raw: Optional[str] = None
    outcome_normalized: Optional[str] = None

    # Attachments (PDFs / supplementary text). The scraper does not download
    # them in SHA-65a; SHA-65b/c will. The metadata is captured here so a
    # later pass can stream attachments without re-parsing.
    attachments: List[ETAttachment] = Field(default_factory=list)

    # Observed licence — falls back to OGL-3.0 when page footer is silent.
    source_license_observed: str

    # Persistence
    raw_storage_path: Optional[str] = None

    # Parser diagnostics (never load-bearing — surfaced for QA only)
    parser_diagnostics: List[str] = Field(default_factory=list)

    # Stage-2 filter result hooks (set during ingestion, not by the page parser)
    stage2_keep: Optional[bool] = None
    stage2_reason: Optional[str] = None


__all__ = [
    "Country",
    "KNOWN_FAIR_REASON_CATEGORIES",
    "KNOWN_OUTCOMES",
    "ETAttachment",
    "ListingEntry",
    "ETCaseMetadata",
]
