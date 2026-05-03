"""SHA-126: GOV.UK Property Chamber metadata -> rag_engine SourceDocument.

This is the seam between the publisher-side scraper (GOV.UK shapes) and
the SHA-20 Phase 4 ingestion contract. After the filter accepts a
record, the scraper calls :func:`govuk_to_source_document` to produce a
:class:`rag_engine.ingestion.contracts.SourceDocument` ready for
``chunk_source_document(...)``.

All Phase-4 metadata (``domain_id``, ``forum``, ``source_publisher``,
``matter_types``, ``corpus_version``, ``parser_version``, ...) is set
here so that downstream chunking/embedding sees a consistent shape
identical to what the BAILII pipeline produces. ``extra`` carries the
publisher-specific fields that don't belong on the canonical
:class:`SourceMetadata`.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from domain_core.spec import Forum, SourceKind, SourcePublisher
from rag_engine.ingestion.contracts import SourceDocument
from rag_engine.source_metadata import SourceMetadata

from .config import (
    CORPUS_VERSION,
    DOMAIN_ID,
    PARSER_VERSION,
    ScraperConfig,
)
from .models import GovUKPCMetadata


def govuk_to_source_document(
    meta: GovUKPCMetadata,
    *,
    kept_grounds: List[str],
    config: Optional[ScraperConfig] = None,
    bailii_duplicate_of: Optional[str] = None,
) -> SourceDocument:
    """Build a :class:`SourceDocument` from accepted GOV.UK metadata.

    Args:
        meta: Parsed GOV.UK Property Chamber metadata.
        kept_grounds: The statutory grounds returned by
            :func:`scripts.scrapers.govuk_property_tribunal.filter.classify_rro`.
        config: ScraperConfig (optional — defaults to a fresh
            :class:`ScraperConfig`). Used for ``parser_version`` /
            ``corpus_version`` overrides in tests.
        bailii_duplicate_of: BAILII source id when this GOV.UK record
            duplicates an already-indexed BAILII decision. Persisted to
            ``extra`` so the ingestion script can skip it.
    """
    cfg = config or ScraperConfig()  # type: ignore[call-arg]
    raw_text = meta.raw_text or meta.title or ""
    if not raw_text.strip():
        # Defensive: keep the document non-empty per SourceDocument's
        # validator. Use the title plus statutory grounds as a stub —
        # in practice the filter will already have rejected this.
        raw_text = (meta.title or meta.case_reference or "rent repayment order") + "\n" + ", ".join(kept_grounds)

    content_sha = (
        meta.content_sha256
        or hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    )

    metadata = SourceMetadata(
        domain_id=DOMAIN_ID,
        domain_family="housing",
        forum=Forum.FIRST_TIER_PROPERTY_CHAMBER,
        source_id=meta.case_reference,
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["rent_repayment_order"],
        decision_date=meta.decision_date,
        source_url=meta.govuk_page_url,
        source_license="OGL-3.0",
        corpus_version=CORPUS_VERSION,
        parser_version=PARSER_VERSION,
        content_sha256=content_sha,
        case_reference=meta.case_reference,
    )

    extra = {
        "tribunal_region": meta.tribunal_region,
        "landlord": meta.landlord,
        "tenant": meta.tenant,
        "address": meta.address,
        "relevant_period_months": meta.relevant_period_months,
        "award_amount": meta.award_amount,
        "award_pct_rent_paid": meta.award_pct_rent_paid,
        "licensing_offence_section": meta.licensing_offence_section,
        "statutory_grounds": list(kept_grounds),
        "primary_asset_url": meta.primary_asset_url,
        "primary_artefact_kind": (
            meta.primary_artefact_kind.value if meta.primary_artefact_kind else None
        ),
        "filter_reasons": list(meta.filter_reasons),
    }
    if bailii_duplicate_of:
        extra["bailii_duplicate_of"] = bailii_duplicate_of
    # Strip None values so the dict round-trips cleanly through ChromaDB
    # via the legacy CaseDocument metadata dict.
    extra = {k: v for k, v in extra.items() if v is not None}

    return SourceDocument(
        metadata=metadata,
        raw_text=raw_text,
        title=meta.title,
        storage_path=meta.storage_path,
        extra=extra,
    )


__all__ = ["govuk_to_source_document"]
