"""SHA-20 Phase 4: tests for the per-publisher citation URL mapper."""

from __future__ import annotations

from datetime import date

import pytest

from domain_core.spec import SourceKind, SourcePublisher

from rag_engine.citation_mapping import map_citation_to_url


class TestEmptyAndUnknown:
    def test_empty_source_id_returns_none(self):
        assert (
            map_citation_to_url(
                source_publisher=SourcePublisher.BAILII,
                source_kind=SourceKind.CASE_DECISION,
                source_id="",
            )
            is None
        )

    def test_unknown_source_id_returns_none(self):
        assert (
            map_citation_to_url(
                source_publisher=SourcePublisher.BAILII,
                source_kind=SourceKind.CASE_DECISION,
                source_id="Unknown",
            )
            is None
        )


class TestBailii:
    def test_bailii_falls_back_to_legacy_pattern(self, monkeypatch):
        # Force the legacy index empty so we hit the deterministic fallback.
        from llm_orchestrator.data import citation_urls as legacy

        monkeypatch.setattr(legacy, "_corpus_index", lambda: {})
        url = map_citation_to_url(
            source_publisher=SourcePublisher.BAILII,
            source_kind=SourceKind.CASE_DECISION,
            source_id="LON_00AU_HMF_2022_0046",
            year=2022,
        )
        assert url is not None
        assert url.endswith("/2022/LON_00AU_HMF_2022_0046.html")


class TestGovUk:
    def test_govuk_rpt_decision_uses_residential_property_path(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.GOVUK,
            source_kind=SourceKind.CASE_DECISION,
            source_id="lon-00ab-hma-2024-0123",
        )
        assert url == "https://www.gov.uk/residential-property-tribunal-decisions/lon-00ab-hma-2024-0123"

    def test_govuk_guidance_uses_root(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.GOVUK,
            source_kind=SourceKind.GUIDANCE,
            source_id="how-to-rent",
        )
        assert url == "https://www.gov.uk/how-to-rent"

    def test_publisher_and_kind_are_separate_keys(self):
        # Same source_id, different kinds => different URLs.
        case_url = map_citation_to_url(
            source_publisher=SourcePublisher.GOVUK,
            source_kind=SourceKind.CASE_DECISION,
            source_id="x",
        )
        guidance_url = map_citation_to_url(
            source_publisher=SourcePublisher.GOVUK,
            source_kind=SourceKind.GUIDANCE,
            source_id="x",
        )
        assert case_url != guidance_url


class TestHousingOmbudsman:
    def test_housing_ombudsman_decision_url(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.HOUSING_OMBUDSMAN,
            source_kind=SourceKind.OMBUDSMAN_DETERMINATION,
            source_id="202300123",
        )
        assert url == "https://www.housing-ombudsman.org.uk/decisions/202300123"


class TestLegislation:
    def test_legislation_without_as_of(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.LEGISLATION_GOV_UK,
            source_kind=SourceKind.STATUTE,
            source_id="ukpga/2004/34/section/213",
        )
        assert url == "https://www.legislation.gov.uk/ukpga/2004/34/section/213"

    def test_legislation_with_point_in_time_date(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.LEGISLATION_GOV_UK,
            source_kind=SourceKind.STATUTE,
            source_id="ukpga/2004/34/section/213",
            as_of=date(2012, 4, 6),
        )
        assert url == "https://www.legislation.gov.uk/ukpga/2004/34/section/213/2012-04-06"


class TestAcas:
    def test_acas_url(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.ACAS,
            source_kind=SourceKind.GUIDANCE,
            source_id="dismissals",
        )
        assert url == "https://www.acas.org.uk/dismissals"


class TestInternal:
    def test_internal_uses_proposer_uri_scheme(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.INTERNAL,
            source_kind=SourceKind.USER_EVIDENCE,
            source_id="upload-abc-123",
        )
        assert url == "proposer://internal/upload-abc-123"

    def test_manual_publisher_also_uses_internal_uri_scheme(self):
        url = map_citation_to_url(
            source_publisher=SourcePublisher.MANUAL,
            source_kind=SourceKind.SYNTHETIC,
            source_id="synth-1",
        )
        assert url == "proposer://internal/synth-1"
