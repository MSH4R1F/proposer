"""SHA-138: GOV.UK MNR metadata -> rag_engine SourceDocument.

This is the seam between the publisher-side scraper (GOV.UK shapes) and
the SHA-20 Phase 4 ingestion contract. After the filter accepts a
record, the scraper calls :func:`govuk_to_source_document` to produce a
:class:`rag_engine.ingestion.contracts.SourceDocument` ready for
``chunk_source_document(...)``.
"""

from __future__ import annotations

import hashlib

from domain_core.spec import Forum, SourceKind, SourcePublisher
from rag_engine.ingestion.contracts import SourceDocument
from rag_engine.source_metadata import SourceMetadata

from .config import CORPUS_VERSION, DOMAIN_ID, PARSER_VERSION
from .models import GovUKPCMetadata


def govuk_to_source_document(meta: GovUKPCMetadata) -> SourceDocument:
    """Build a :class:`SourceDocument` from accepted GOV.UK MNR metadata."""
    raw_text = meta.raw_text or meta.title or ""
    if not raw_text.strip():
        raw_text = (meta.title or meta.case_reference or "rent determination")

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
        matter_types=["rent_determination"],
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
        "decided_rent_amount": meta.decided_rent_amount,
        "decided_rent_period": meta.decided_rent_period.value,
        "landlord_proposed_rent_amount": meta.landlord_proposed_rent_amount,
        "existing_rent_amount": meta.existing_rent_amount,
        "statute_basis": meta.statute_basis,
        "primary_asset_url": meta.primary_asset_url,
        "primary_artefact_kind": (
            meta.primary_artefact_kind.value if meta.primary_artefact_kind else None
        ),
        "filter_reasons": list(meta.filter_reasons),
    }
    extra = {k: v for k, v in extra.items() if v is not None}

    return SourceDocument(
        metadata=metadata,
        raw_text=raw_text,
        title=meta.title,
        storage_path=meta.storage_path,
        extra=extra,
    )


__all__ = ["govuk_to_source_document"]
