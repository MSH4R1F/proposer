"""Idempotency: chunking the same SourceDocument twice yields identical chunk_ids.

The Phase-0 :func:`deterministic_chunk_id` is the seam that guarantees
re-ingestion is a no-op. We just verify two passes through
:func:`chunk_source_document` produce the same id list.
"""

from __future__ import annotations

from datetime import date

from rag_engine.chunking.legal_chunker import LegalChunker
from rag_engine.ingestion.adapters import chunk_source_document

from scripts.scrapers.housing_ombudsman.config import ScraperConfig
from scripts.scrapers.housing_ombudsman.models import OmbudsmanCaseMetadata
from scripts.scrapers.housing_ombudsman.to_source_document import (
    ombudsman_to_source_document,
)


_RAW = (
    "BACKGROUND\n\n"
    "The resident reported damp and mould in the bedroom on 1 June 2024.\n"
    "The landlord did not inspect for 14 weeks despite repeated requests.\n\n"
    "REASONS\n\n"
    "There was maladministration in the landlord's handling of the repair.\n"
    "The Ombudsman finds that the failure to inspect within a reasonable\n"
    "time amounts to a breach of the repairing obligation.\n\n"
    "DECISION\n\n"
    "The complaint is upheld; the landlord must apologise and pay £500.\n"
)


def _build_doc():
    meta = OmbudsmanCaseMetadata(
        case_reference="202300042",
        decision_date=date(2024, 6, 1),
        landlord_name="Acme Housing",
        complaint_categories=["Property condition"],
        outcome_raw="Maladministration",
        outcome_normalized="maladministration",
        orders=["Apologise"],
        recommendations=[],
        source_url="https://x/decisions/202300042/",
    )
    return ombudsman_to_source_document(
        meta,
        _RAW,
        kept_matter_types=["repairs_damp_mould"],
        config=ScraperConfig(),
    )


def test_chunk_ids_stable_across_runs():
    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)

    sd1 = _build_doc()
    sd2 = _build_doc()
    chunks_1 = chunk_source_document(
        sd1, namespace_id="housing_repairs_social_v1", chunker=chunker
    )
    chunks_2 = chunk_source_document(
        sd2, namespace_id="housing_repairs_social_v1", chunker=chunker
    )

    ids_1 = [c.chunk_id for c in chunks_1]
    ids_2 = [c.chunk_id for c in chunks_2]
    assert ids_1 == ids_2
    # Spot-check the deterministic id shape.
    assert all(c.startswith("housing_repairs_social_v1::") for c in ids_1)
    assert any("research_seed_2026_05" in c for c in ids_1)


def test_chunks_carry_phase4_metadata():
    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)
    sd = _build_doc()
    chunks = chunk_source_document(
        sd, namespace_id="housing_repairs_social_v1", chunker=chunker
    )
    assert chunks, "expected at least one chunk"
    for c in chunks:
        assert c.source_metadata is not None
        assert c.source_metadata.domain_id == "housing.repairs_social.v1"
        assert c.source_metadata.source_id == "202300042"
        assert c.source_metadata.corpus_version == "research_seed_2026_05"
        assert c.source_metadata.parser_version == "ombudsman-0.1.0"
