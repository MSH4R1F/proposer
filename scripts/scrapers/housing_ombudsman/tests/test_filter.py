"""Tests for the repairs/social-housing allowlist filter."""

from __future__ import annotations

import pytest

from scripts.scrapers.housing_ombudsman.filter import (
    keep_repairs_social_only,
)
from scripts.scrapers.housing_ombudsman.models import OmbudsmanCaseMetadata


def _meta(**kwargs) -> OmbudsmanCaseMetadata:
    base = dict(
        case_reference="202300000",
        source_url="https://www.housing-ombudsman.org.uk/decisions/202300000/",
    )
    base.update(kwargs)
    return OmbudsmanCaseMetadata(**base)


class TestKeepDamp:
    def test_damp_and_mould_kept(self):
        meta = _meta(complaint_categories=["Property condition"])
        body = (
            "The resident reported persistent damp and mould in the bedroom "
            "and bathroom. The landlord failed to inspect the property within "
            "the required timeframe."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is True
        assert "repairs_damp_mould" in result.matter_types

    def test_disrepair_keyword_kept(self):
        meta = _meta(complaint_categories=["Repairs"])
        body = "The boiler was broken for 6 weeks and there was no hot water."
        result = keep_repairs_social_only(meta, body)
        assert result.keep is True
        assert "repairs_disrepair" in result.matter_types

    def test_leak_kept(self):
        meta = _meta()
        body = "There was a leak from the roof that the landlord failed to repair."
        result = keep_repairs_social_only(meta, body)
        assert result.keep is True
        assert "repairs_disrepair" in result.matter_types

    def test_complaint_handling_with_repairs_kept(self):
        meta = _meta(complaint_categories=["Complaint handling", "Repairs"])
        body = (
            "The landlord's complaint handling was inadequate. The resident "
            "had reported damp and mould multiple times before any inspection."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is True
        assert "repairs_damp_mould" in result.matter_types
        assert "complaint_handling_failure" in result.matter_types


class TestRejectNonRepairs:
    def test_service_charges_rejected(self):
        meta = _meta(complaint_categories=["Leasehold service charges"])
        body = (
            "The leaseholder disputes the service charge calculation for "
            "the previous accounting year."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "non_repairs_service_charges"
        assert "service charge" in (result.matched_keywords or [])

    def test_anti_social_behaviour_rejected(self):
        meta = _meta(complaint_categories=["Anti-social behaviour"])
        body = (
            "The resident complained about noise nuisance from neighbouring "
            "tenants. The landlord investigated the anti-social behaviour."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "non_repairs_asb"

    def test_rehousing_only_rejected(self):
        meta = _meta(complaint_categories=["Rehousing"])
        body = "The resident requested a transfer request to a larger property due to overcrowding."
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "non_repairs_rehousing_only"

    def test_succession_rejected(self):
        meta = _meta()
        body = "The complaint concerns tenancy succession after the previous tenant's death."
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "non_repairs_succession"

    def test_rent_arrears_rejected(self):
        meta = _meta()
        body = "The dispute is about rent arrears accumulated during 2022."
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "non_repairs_rent_arrears"

    def test_generic_complaint_handling_rejected(self):
        meta = _meta(complaint_categories=["Complaint handling"])
        body = (
            "The complaint was about how the landlord responded to a stage 1 "
            "response query about a parking permit."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "generic_complaint_handling_no_repairs"

    def test_empty_body_rejected(self):
        meta = _meta()
        result = keep_repairs_social_only(meta, "")
        assert result.keep is False
        assert result.reject_reason == "no_repairs_signal"


class TestCategoryOnly:
    """Regression: a "Repairs" or "Property condition" category with no
    body evidence used to falsely keep a case (categories were merged
    into the haystack). Now categories and body are scanned separately
    and category-only matches are rejected as too weak to ingest."""

    def test_repairs_category_only_with_unrelated_body_is_rejected(self):
        meta = _meta(complaint_categories=["Repairs"])
        body = (
            "The resident asked the landlord to clarify the parking permit "
            "policy for the estate. There was no further substantive issue."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "category_only_no_body_evidence"

    def test_property_condition_category_only_empty_body_is_rejected(self):
        meta = _meta(complaint_categories=["Property condition"])
        result = keep_repairs_social_only(meta, "")
        assert result.keep is False
        # Empty body falls through to no_repairs_signal — also acceptable
        # as long as it is NOT kept.
        assert result.reject_reason in {
            "category_only_no_body_evidence",
            "no_repairs_signal",
        }


class TestMixedSignals:
    def test_repairs_plus_service_charge_keeps_repairs(self):
        """Joint repairs+service-charge complaints are kept (repairs wins)."""
        meta = _meta(complaint_categories=["Repairs", "Service charges"])
        body = (
            "The resident raised concerns about damp and mould in the kitchen, "
            "and disputed the service charge for cleaning communal areas."
        )
        result = keep_repairs_social_only(meta, body)
        assert result.keep is True
        assert "repairs_damp_mould" in result.matter_types
