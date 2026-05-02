"""SHA-20 Phase 4: Citation URL mapping per (publisher, kind, source_id).

The legal contract is: every cited claim must point to a publisher-canonical
URL (or a documented internal URI). This module resolves those URLs with no
LLM in the loop. The mapping is *not* a content-fetch — it only constructs
URLs whose authority comes from the publisher.

Why a separate module from ``llm_orchestrator.data.citation_urls``?

* ``citation_urls.py`` is the legacy BAILII-only resolver tied to the
  deposit pipeline (and to the ``data/raw/bailii`` corpus index). It is
  preserved unchanged and called as a fallback for the BAILII case.
* This module covers the multi-domain set: GOV.UK Residential Property
  Tribunal pages, GOV.UK PDFs, Housing Ombudsman, legislation.gov.uk
  (with point-in-time deep links), ACAS, and INTERNAL ``proposer://`` URIs.

``source_publisher`` and ``source_kind`` are SEPARATE: GOV.UK is a
publisher; ``tribunal_decision_pdf`` / ``tribunal_decision_html`` /
``ombudsman_decision`` are kinds. The mapper key is a 3-tuple, not a
flat string.
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from urllib.parse import quote

from domain_core.spec import SourceKind, SourcePublisher

# --------------------------------------------------------------------------
# Per-publisher URL builders
# --------------------------------------------------------------------------

# GOV.UK page for a specific Residential Property Tribunal decision.
# Real GOV.UK URLs use "residential-property-tribunal-decisions/{slug}";
# we accept slugs as-is in source_id.
_GOVUK_RPT_BASE = "https://www.gov.uk/residential-property-tribunal-decisions"

# Housing Ombudsman publishes decisions under this path.
_OMBUDSMAN_BASE = "https://www.housing-ombudsman.org.uk/decisions"

# legislation.gov.uk supports point-in-time deep links via
# "/{type}/{year}/{number}/section/{section}/{date}".
_LEGISLATION_BASE = "https://www.legislation.gov.uk"

# ACAS publishes guidance pages under acas.org.uk.
_ACAS_BASE = "https://www.acas.org.uk"

# Internal scheme for proposer-internal sources (uploaded user evidence,
# calculator traces). The format is documented in the prompt pack.
_INTERNAL_SCHEME = "proposer://internal"


def _bailii_pc(source_id: str, year: Optional[int]) -> Optional[str]:
    """Defer to the legacy BAILII resolver, then fall back to the pattern.

    Imported lazily to avoid a circular import at module load.
    """
    from llm_orchestrator.data.citation_urls import resolve_source_url

    return resolve_source_url(source_id, year)


def _govuk_url(source_id: str, kind: SourceKind) -> str:
    sid = quote(source_id, safe="-_/")
    if kind == SourceKind.CASE_DECISION:
        # GOV.UK Residential Property Tribunal decision page (HTML by default).
        return f"{_GOVUK_RPT_BASE}/{sid}"
    if kind == SourceKind.GUIDANCE:
        return f"https://www.gov.uk/{sid}"
    # Default: treat as a GOV.UK PDF / generic page; assume slug includes path.
    return f"https://www.gov.uk/{sid}"


def _ombudsman_url(source_id: str) -> str:
    sid = quote(source_id, safe="-_/")
    return f"{_OMBUDSMAN_BASE}/{sid}"


def _legislation_url(source_id: str, as_of: Optional[date]) -> str:
    """Build a legislation.gov.uk URL.

    ``source_id`` is expected to be a path fragment that already encodes
    type/year/number/section, e.g. ``"ukpga/2004/34/section/213"`` for the
    Housing Act 2004 s.213. If ``as_of`` is supplied we append the
    point-in-time date segment which legislation.gov.uk respects.
    """
    sid = source_id.strip("/")
    base = f"{_LEGISLATION_BASE}/{sid}"
    if as_of is not None:
        return f"{base}/{as_of.isoformat()}"
    return base


def _acas_url(source_id: str) -> str:
    sid = quote(source_id, safe="-_/")
    return f"{_ACAS_BASE}/{sid}"


def _internal_uri(source_id: str) -> str:
    return f"{_INTERNAL_SCHEME}/{source_id}"


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def map_citation_to_url(
    *,
    source_publisher: SourcePublisher,
    source_kind: SourceKind,
    source_id: str,
    year: Optional[int] = None,
    as_of: Optional[date] = None,
) -> Optional[str]:
    """Resolve a canonical URL for a citation.

    Args:
        source_publisher: Publisher enum (BAILII, GOVUK, ...).
        source_kind: Kind enum (CASE_DECISION, STATUTE, ...).
        source_id: Stable id within the publisher.
        year: Optional year (used by BAILII fallback).
        as_of: Optional effective-date for legislation.gov.uk deep links.

    Returns:
        The canonical URL, or ``None`` for empty/unknown inputs.
    """
    if not source_id or not source_id.strip():
        return None
    if source_id.strip().lower() in {"unknown", "none"}:
        return None

    if source_publisher == SourcePublisher.BAILII:
        return _bailii_pc(source_id, year)
    if source_publisher == SourcePublisher.GOVUK:
        return _govuk_url(source_id, source_kind)
    if source_publisher == SourcePublisher.HOUSING_OMBUDSMAN:
        return _ombudsman_url(source_id)
    if source_publisher == SourcePublisher.LEGISLATION_GOV_UK:
        return _legislation_url(source_id, as_of)
    if source_publisher == SourcePublisher.ACAS:
        return _acas_url(source_id)
    if source_publisher in {SourcePublisher.INTERNAL, SourcePublisher.MANUAL}:
        return _internal_uri(source_id)
    return None


__all__ = ["map_citation_to_url"]
