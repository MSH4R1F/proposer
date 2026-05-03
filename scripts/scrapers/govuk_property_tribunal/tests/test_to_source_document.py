"""Tests for SHA-126 GovUK -> SourceDocument adapter."""

from __future__ import annotations

from datetime import date

from domain_core.spec import Forum, SourceKind, SourcePublisher

from scripts.scrapers.govuk_property_tribunal.config import (
    CORPUS_VERSION,
    DOMAIN_ID,
    PARSER_VERSION,
)
from scripts.scrapers.govuk_property_tribunal.models import (
    ArtefactKind,
    GovUKAsset,
    GovUKPCMetadata,
)
from scripts.scrapers.govuk_property_tribunal.to_source_document import (
    govuk_to_source_document,
)


def _meta() -> GovUKPCMetadata:
    return GovUKPCMetadata(
        case_reference="LON/00AG/HMF/2023/0001",
        title="RRO decision: 1 Test Road, London",
        govuk_page_url="https://www.gov.uk/residential-property-tribunal-decisions/lon-00ag-hmf-2023-0001",
        base_path="/residential-property-tribunal-decisions/lon-00ag-hmf-2023-0001",
        decision_date=date(2023, 6, 15),
        tribunal_region="London",
        landlord="Acme Lettings Ltd",
        tenant="Jane Doe",
        address="1 Test Road, London E1 7AB",
        relevant_period_months=12,
        award_amount=6000.0,
        award_pct_rent_paid=0.55,
        licensing_offence_section="Housing Act 2004 s.72(1)",
        statutory_grounds=["Housing Act 2004 s.72(1) (unlicensed HMO)"],
        primary_asset_url="https://www.gov.uk/government/uploads/decision-1.pdf",
        primary_artefact_kind=ArtefactKind.PDF,
        raw_text="The respondent committed an offence under section 72(1) of the Housing Act 2004.",
        content_sha256="0" * 64,
        assets=[
            GovUKAsset(
                url="https://www.gov.uk/government/uploads/decision-1.pdf",
                kind=ArtefactKind.PDF,
                filename="decision-1.pdf",
                content_type="application/pdf",
            )
        ],
    )


def test_govuk_to_source_document_phase4_metadata():
    meta = _meta()
    sd = govuk_to_source_document(
        meta,
        kept_grounds=["Housing Act 2004 s.72(1) (unlicensed HMO)"],
    )
    md = sd.metadata
    assert md.domain_id == DOMAIN_ID
    assert md.domain_family == "housing"
    assert md.forum == Forum.FIRST_TIER_PROPERTY_CHAMBER
    assert md.source_publisher == SourcePublisher.GOVUK
    assert md.source_kind == SourceKind.CASE_DECISION
    assert md.matter_types == ["rent_repayment_order"]
    assert md.source_id == meta.case_reference
    assert md.case_reference == meta.case_reference
    assert md.corpus_version == CORPUS_VERSION
    assert md.parser_version == PARSER_VERSION
    assert md.decision_date == meta.decision_date
    assert md.source_url == meta.govuk_page_url
    assert md.source_license == "OGL-3.0"
    assert sd.raw_text == meta.raw_text
    assert sd.title == meta.title
    # extra fields
    assert sd.extra["tribunal_region"] == "London"
    assert sd.extra["statutory_grounds"] == ["Housing Act 2004 s.72(1) (unlicensed HMO)"]
    assert sd.extra["primary_asset_url"].endswith("decision-1.pdf")
    assert sd.extra["primary_artefact_kind"] == "pdf"
    assert sd.extra["award_amount"] == 6000.0


def test_govuk_to_source_document_carries_bailii_duplicate_marker():
    meta = _meta()
    sd = govuk_to_source_document(
        meta,
        kept_grounds=["Housing Act 2004 s.72(1) (unlicensed HMO)"],
        bailii_duplicate_of="BAILII_REF_123",
    )
    assert sd.extra["bailii_duplicate_of"] == "BAILII_REF_123"
