"""SHA-126: idempotency tests for the SourceDocument adapter chain."""

from __future__ import annotations

from datetime import date

from rag_engine.chunking.legal_chunker import LegalChunker
from rag_engine.ingestion.adapters import chunk_source_document, deterministic_chunk_id

from scripts.scrapers.govuk_property_tribunal.config import NAMESPACE_ID
from scripts.scrapers.govuk_property_tribunal.config import ScraperConfig
from scripts.scrapers.govuk_property_tribunal.govuk_scraper import GovUKRROScraper
from scripts.scrapers.govuk_property_tribunal.models import (
    ArtefactKind,
    FilterDecision,
    GovUKPCMetadata,
    ScrapeRecord,
)
from scripts.scrapers.govuk_property_tribunal.to_source_document import (
    govuk_to_source_document,
)


def _meta() -> GovUKPCMetadata:
    body = (
        "BACKGROUND\n"
        "The applicant tenant rented the property from January 2022 to January 2023.\n"
        "FACTS\n"
        "The respondent committed an offence under section 72(1) of the Housing Act 2004.\n"
        "REASONING\n"
        "The tribunal accepts that the property was an HMO subject to mandatory licensing.\n"
        "DECISION\n"
        "We award a rent repayment order in the sum of £6,000 covering the relevant period.\n"
    )
    return GovUKPCMetadata(
        case_reference="LON/00AG/HMF/2023/0001",
        title="RRO decision: 1 Test Road",
        govuk_page_url="https://www.gov.uk/decisions/lon-00ag-hmf-2023-0001",
        base_path="/decisions/lon-00ag-hmf-2023-0001",
        decision_date=date(2023, 6, 15),
        raw_text=body,
        content_sha256="x" * 64,
        primary_asset_url="https://www.gov.uk/decisions/lon-00ag-hmf-2023-0001",
        primary_artefact_kind=ArtefactKind.HTML,
    )


def test_chunking_is_idempotent():
    meta = _meta()
    grounds = ["Housing Act 2004 s.72(1) (unlicensed HMO)"]
    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)

    sd1 = govuk_to_source_document(meta, kept_grounds=grounds)
    sd2 = govuk_to_source_document(meta, kept_grounds=grounds)
    chunks1 = chunk_source_document(sd1, namespace_id=NAMESPACE_ID, chunker=chunker)
    chunks2 = chunk_source_document(sd2, namespace_id=NAMESPACE_ID, chunker=chunker)

    assert len(chunks1) == len(chunks2)
    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]
    # Each chunk id is the deterministic format
    for idx, chunk in enumerate(chunks1):
        expected = deterministic_chunk_id(
            namespace_id=NAMESPACE_ID,
            corpus_version=sd1.metadata.corpus_version,
            source_id=sd1.metadata.source_id,
            chunk_index=idx,
            chunk_text=chunk.text,
        )
        assert chunk.chunk_id == expected


def test_scraper_resume_skips_unchanged_master_index_records(tmp_path):
    meta = _meta()
    scraper = GovUKRROScraper(ScraperConfig(output_base_dir=tmp_path))
    existing = ScrapeRecord(
        case_reference=meta.case_reference,
        govuk_page_url=meta.govuk_page_url,
        base_path=meta.base_path,
        decision_date=meta.decision_date,
        title=meta.title,
        filter_decision=FilterDecision.ACCEPT,
        statutory_grounds=["Housing Act 2004 s.72(1) (unlicensed HMO)"],
        primary_artefact_kind=meta.primary_artefact_kind,
        content_sha256=meta.content_sha256,
    )
    scraper._master_index.upsert(existing)

    assert scraper._existing_unchanged_record(meta, meta.raw_text or "") is existing

    changed = _meta()
    changed.content_sha256 = "y" * 64
    assert scraper._existing_unchanged_record(changed, changed.raw_text or "") is None
