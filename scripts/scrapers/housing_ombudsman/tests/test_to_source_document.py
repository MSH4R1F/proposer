"""Verify the SourceDocument adapter wires every Phase-4 field correctly."""

from __future__ import annotations

from datetime import date

from domain_core.spec import Forum, SourceKind, SourcePublisher

from scripts.scrapers.housing_ombudsman.config import ScraperConfig
from scripts.scrapers.housing_ombudsman.models import OmbudsmanCaseMetadata
from scripts.scrapers.housing_ombudsman.to_source_document import (
    ombudsman_to_source_document,
)


def _meta() -> OmbudsmanCaseMetadata:
    return OmbudsmanCaseMetadata(
        case_reference="202300042",
        decision_date=date(2024, 6, 1),
        landlord_name="Acme Housing",
        complaint_categories=["Property condition", "Complaint handling"],
        outcome_raw="Maladministration",
        outcome_normalized="maladministration",
        orders=["Apologise", "Pay £500"],
        recommendations=["Review policy"],
        source_url="https://www.housing-ombudsman.org.uk/decisions/202300042/",
        title="Resident vs Acme Housing",
        temporal_markers={"awaabs_law_referenced": True},
        parser_diagnostics=[],
    )


def test_source_document_full_phase4_metadata():
    sd = ombudsman_to_source_document(
        _meta(),
        "Damp and mould reported in the bedroom; section 11 cited.",
        kept_matter_types=["repairs_damp_mould", "complaint_handling_failure"],
        config=ScraperConfig(),
    )
    md = sd.metadata
    assert md.domain_id == "housing.repairs_social.v1"
    assert md.domain_family == "housing"
    assert md.forum == Forum.HOUSING_OMBUDSMAN
    assert md.source_publisher == SourcePublisher.HOUSING_OMBUDSMAN
    assert md.source_kind == SourceKind.OMBUDSMAN_DETERMINATION
    assert md.source_id == "202300042"
    assert md.case_reference == "202300042"
    assert md.matter_types == ["repairs_damp_mould", "complaint_handling_failure"]
    assert md.decision_date == date(2024, 6, 1)
    assert md.source_url.endswith("/decisions/202300042/")
    assert md.corpus_version == "research_seed_2026_05"
    assert md.parser_version == "ombudsman-0.1.0"
    assert md.content_sha256 and len(md.content_sha256) == 64
    # License is the unverified pilot string.
    assert md.source_license and "permission_pending" in md.source_license


def test_source_document_extra_carries_publisher_fields():
    sd = ombudsman_to_source_document(
        _meta(),
        "Damp and mould reported in the bedroom.",
        kept_matter_types=["repairs_damp_mould"],
        config=ScraperConfig(),
    )
    extra = sd.extra
    assert extra["complaint_categories"] == [
        "Property condition",
        "Complaint handling",
    ]
    assert extra["outcome_raw"] == "Maladministration"
    assert extra["outcome_normalized"] == "maladministration"
    assert extra["orders"] == ["Apologise", "Pay £500"]
    assert extra["recommendations"] == ["Review policy"]
    assert extra["landlord_name"] == "Acme Housing"
    assert extra["temporal_markers"] == {"awaabs_law_referenced": True}


def test_to_chroma_metadata_safe_scalars():
    sd = ombudsman_to_source_document(
        _meta(),
        "Body text",
        kept_matter_types=["repairs_damp_mould"],
        config=ScraperConfig(),
    )
    chroma = sd.metadata.to_chroma_metadata()
    # All values must be str/int/float/bool — no nested objects.
    for k, v in chroma.items():
        assert isinstance(v, (str, int, float, bool)), f"{k} -> {type(v)}"
    assert chroma["domain_id"] == "housing.repairs_social.v1"
    assert chroma["forum"] == "housing_ombudsman"
    assert chroma["source_publisher"] == "housing_ombudsman"
    assert chroma["source_kind"] == "ombudsman_determination"
    assert chroma["matter_types"] == "repairs_damp_mould"
