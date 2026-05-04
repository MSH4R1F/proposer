"""Bridge from :class:`OmbudsmanCaseMetadata` -> :class:`SourceDocument`.

This is the seam every Housing Ombudsman ingestion run goes through.
Phase-4 :class:`SourceMetadata` fields are filled exactly per the
SHA-125 plan §5: ``domain_id="housing.repairs_social.v1"``,
``domain_family="housing"``, ``forum=Forum.HOUSING_OMBUDSMAN``,
``source_publisher=SourcePublisher.HOUSING_OMBUDSMAN``,
``source_kind=SourceKind.OMBUDSMAN_DETERMINATION``.

Publisher-specific fields (orders, recommendations, complaint
categories, parser diagnostics) ride on
``SourceDocument.extra`` so they survive into the manifest without
polluting the cross-domain :class:`SourceMetadata`.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from rag_engine.ingestion.contracts import SourceDocument
from rag_engine.source_metadata import SourceMetadata
from domain_core.spec import ChunkKind, Forum, SourceKind, SourcePublisher

from . import PARSER_VERSION
from .config import ScraperConfig
from .models import OmbudsmanCaseMetadata


def _content_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def ombudsman_to_source_document(
    meta: OmbudsmanCaseMetadata,
    raw_text: str,
    *,
    kept_matter_types: List[str],
    config: ScraperConfig,
) -> SourceDocument:
    """Build a :class:`SourceDocument` from an Ombudsman case.

    ``kept_matter_types`` is the list returned by
    :func:`scripts.scrapers.housing_ombudsman.filter.keep_repairs_social_only`
    (e.g. ``["repairs_damp_mould", "complaint_handling_failure"]``).
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text must be non-empty for SourceDocument creation")

    metadata = SourceMetadata(
        domain_id="housing.repairs_social.v1",
        domain_family="housing",
        forum=Forum.HOUSING_OMBUDSMAN,
        source_id=meta.case_reference,
        source_publisher=SourcePublisher.HOUSING_OMBUDSMAN,
        source_kind=SourceKind.OMBUDSMAN_DETERMINATION,
        matter_types=list(kept_matter_types or []),
        decision_date=meta.decision_date,
        outcome_raw=meta.outcome_raw,
        outcome_normalized=meta.outcome_normalized,
        source_url=meta.source_url,
        source_license=config.source_license,
        corpus_version=config.corpus_version,
        parser_version=PARSER_VERSION,
        content_sha256=_content_sha256(raw_text),
        case_reference=meta.case_reference,
        chunk_kind=ChunkKind.DOCUMENT_CHUNK,
    )

    extra: Dict[str, Any] = {
        "complaint_categories": list(meta.complaint_categories or []),
        "outcome_raw": meta.outcome_raw,
        "outcome_normalized": meta.outcome_normalized,
        "orders": list(meta.orders or []),
        "recommendations": list(meta.recommendations or []),
        "landlord_name": meta.landlord_name,
        "temporal_markers": dict(meta.temporal_markers or {}),
        "parser_diagnostics": list(meta.parser_diagnostics or []),
    }

    return SourceDocument(
        metadata=metadata,
        raw_text=raw_text,
        title=meta.title,
        storage_path=meta.raw_storage_path,
        extra=extra,
    )


__all__ = ["ombudsman_to_source_document"]
