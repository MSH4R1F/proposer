"""SHA-138: GOV.UK FTT(PC) MNR rent-determination scraper data models.

Distinct from :class:`rag_engine.ingestion.contracts.SourceDocument` —
these are the *intermediate* publisher-side models used while
discovering, downloading, and filtering decisions. Conversion to
``SourceDocument`` happens in ``to_source_document.py``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FilterDecision(str, Enum):
    """Outcome of the MNR matter-code filter."""

    ACCEPT = "accept"
    REJECT = "reject"
    UNCERTAIN = "uncertain"


class RentPeriod(str, Enum):
    """Rent quoting period extracted from the decision."""

    PER_WEEK = "per_week"
    PER_FORTNIGHT = "per_fortnight"
    PER_CALENDAR_MONTH = "per_calendar_month"
    PER_LUNAR_MONTH = "per_lunar_month"
    PER_QUARTER = "per_quarter"
    PER_ANNUM = "per_annum"
    UNKNOWN = "unknown"


class ArtefactKind(str, Enum):
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    JSON = "json"


class GovUKAsset(BaseModel):
    """A downloadable attachment on a GOV.UK decision page."""

    model_config = ConfigDict(extra="forbid")

    url: str
    kind: ArtefactKind
    filename: Optional[str] = None
    content_type: Optional[str] = None
    title: Optional[str] = None


class GovUKSearchHit(BaseModel):
    """One row returned by ``/api/search.json``."""

    model_config = ConfigDict(extra="forbid")

    title: str
    link: str = Field(..., description="Path-only or absolute URL from GOV.UK.")
    description: Optional[str] = None
    public_timestamp: Optional[datetime] = None
    content_id: Optional[str] = None
    content_purpose_supergroup: Optional[str] = None
    document_type: Optional[str] = None
    sub_categories: List[str] = Field(default_factory=list)


class GovUKPCMetadata(BaseModel):
    """Parsed GOV.UK Property Chamber MNR decision metadata.

    The fields here mirror what ends up on
    :class:`~rag_engine.source_metadata.SourceMetadata.extra` plus the
    canonical fields the SourceMetadata itself owns. Keeping them on a
    typed model (rather than a dict) means the parser tests can assert
    the shape exactly.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity --------------------------------------------------------
    case_reference: str = Field(..., description="Tribunal case reference / GOV.UK base path slug.")
    title: str
    govuk_page_url: str = Field(..., description="Public GOV.UK URL of the decision.")
    base_path: str = Field(..., description="GOV.UK base_path (used for content-API).")
    content_id: Optional[str] = None

    # Temporal --------------------------------------------------------
    decision_date: Optional[date] = None
    public_timestamp: Optional[datetime] = None

    # Tribunal-specific ----------------------------------------------
    tribunal_region: Optional[str] = None
    landlord: Optional[str] = None
    tenant: Optional[str] = None
    address: Optional[str] = None

    # MNR substantive — the tribunal-set rent ------------------------
    decided_rent_amount: Optional[float] = Field(
        None,
        description=(
            "Tribunal-determined open-market rent in £ (no currency "
            "symbol). Period is recorded separately."
        ),
    )
    decided_rent_period: RentPeriod = Field(
        default=RentPeriod.UNKNOWN,
        description="Rent quoting period (per week / cm / annum / etc).",
    )
    landlord_proposed_rent_amount: Optional[float] = Field(
        None,
        description="Landlord's s.13 notice rent (the figure the tenant referred).",
    )
    existing_rent_amount: Optional[float] = Field(
        None,
        description="Pre-notice rent figure where the decision records it.",
    )
    statute_basis: Optional[str] = Field(
        None,
        description=(
            "Cited determining provision — typically 'Housing Act 1988 s.14' "
            "for periodic ASTs."
        ),
    )

    # Assets ---------------------------------------------------------
    assets: List[GovUKAsset] = Field(default_factory=list)
    primary_asset_url: Optional[str] = None
    primary_artefact_kind: Optional[ArtefactKind] = None

    # Filter -----------------------------------------------------
    filter_decision: FilterDecision = FilterDecision.UNCERTAIN
    filter_reasons: List[str] = Field(default_factory=list)

    # Body --------------------------------------------------------
    raw_text: Optional[str] = Field(
        None, description="Cleaned plain-text body of the decision (HTML or PDF)."
    )
    content_sha256: Optional[str] = None

    # Storage -----------------------------------------------------
    storage_path: Optional[str] = Field(
        None, description="On-disk POSIX path to the canonical artefact."
    )


class ScrapeRecord(BaseModel):
    """One row in master_index.json — the run-level outcome for a hit."""

    model_config = ConfigDict(extra="forbid")

    case_reference: str
    govuk_page_url: str
    base_path: str
    decision_date: Optional[date] = None
    title: str
    filter_decision: FilterDecision
    filter_reasons: List[str] = Field(default_factory=list)
    decided_rent_amount: Optional[float] = None
    decided_rent_period: RentPeriod = RentPeriod.UNKNOWN
    primary_artefact_kind: Optional[ArtefactKind] = None
    storage_path: Optional[str] = None
    content_sha256: Optional[str] = None
    scraped_at: Optional[datetime] = None
    notes: List[str] = Field(default_factory=list)


__all__ = [
    "ArtefactKind",
    "FilterDecision",
    "GovUKAsset",
    "GovUKPCMetadata",
    "GovUKSearchHit",
    "RentPeriod",
    "ScrapeRecord",
]
