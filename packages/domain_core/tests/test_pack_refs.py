"""Unit tests for PackReferenceSet (DomainSpec extension)."""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from domain_core.pack_refs import PackReferenceSet


def test_minimum_valid_pack_refs():
    refs = PackReferenceSet(
        factor_catalog_ref="ref://factor_catalog/housing_repairs_social_v1",
        outcome_schema_ref="ref://outcome_schema/housing_repairs_social_v1",
        remedy_schema_ref="ref://remedy_schema/housing_repairs_social_v1",
        retrieval_profile_ref="ref://retrieval_profile/housing_repairs_social_v1",
        evaluation_profile_ref="ref://evaluation_profile/housing_repairs_social_v1",
    )
    assert refs.factor_catalog_ref.startswith("ref://factor_catalog/")


def test_all_refs_are_optional_for_transition_period():
    refs = PackReferenceSet()
    assert refs.factor_catalog_ref is None
    assert refs.outcome_schema_ref is None


def test_factor_catalog_ref_must_use_correct_kind():
    with pytest.raises(ValidationError):
        PackReferenceSet(
            factor_catalog_ref="ref://prompt_pack/oops",
        )


def test_outcome_schema_ref_must_use_correct_kind():
    with pytest.raises(ValidationError):
        PackReferenceSet(
            outcome_schema_ref="ref://factor_catalog/wrong_kind",
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        PackReferenceSet(unexpected="oops")


def test_frozen():
    refs = PackReferenceSet(
        factor_catalog_ref="ref://factor_catalog/x",
    )
    with pytest.raises(ValidationError):
        refs.factor_catalog_ref = "ref://factor_catalog/y"


def test_invalid_ref_uri_format_rejected():
    with pytest.raises(ValidationError):
        PackReferenceSet(factor_catalog_ref="not_a_ref_uri")


def test_ref_id_segment_required():
    with pytest.raises(ValidationError):
        PackReferenceSet(factor_catalog_ref="ref://factor_catalog/")


def test_domain_spec_accepts_pack_refs_field():
    """DomainSpec.pack_refs is optional and defaults to None."""
    from domain_core.spec import DomainSpec

    assert "pack_refs" in DomainSpec.model_fields
    assert DomainSpec.model_fields["pack_refs"].default is None


def test_pack_refs_round_trips_through_json():
    original = PackReferenceSet(
        factor_catalog_ref="ref://factor_catalog/housing_repairs_social_v1",
        outcome_schema_ref="ref://outcome_schema/housing_repairs_social_v1",
    )
    payload = original.model_dump_json()
    restored = PackReferenceSet.model_validate_json(payload)
    assert restored == original


def test_warn_if_missing_emits_user_warning_for_none_pack_refs():
    from domain_core.pack_refs import warn_if_missing

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_if_missing(spec_id="housing.repairs_social.v1", pack_refs=None)

    matches = [
        w
        for w in caught
        if issubclass(w.category, UserWarning) and "pack_refs" in str(w.message)
    ]
    assert len(matches) == 1, f"expected one UserWarning, got {caught}"
    assert "housing.repairs_social.v1" in str(matches[0].message)


def test_warn_if_missing_silent_when_any_ref_present():
    from domain_core.pack_refs import warn_if_missing

    refs = PackReferenceSet(
        factor_catalog_ref="ref://factor_catalog/x",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_if_missing(spec_id="housing.repairs_social.v1", pack_refs=refs)

    matches = [
        w
        for w in caught
        if issubclass(w.category, UserWarning) and "pack_refs" in str(w.message)
    ]
    assert matches == []


def test_warn_if_missing_warns_when_all_fields_none_in_present_pack_refs():
    """An empty PackReferenceSet (all None) is also a missing-pack signal."""
    from domain_core.pack_refs import warn_if_missing

    refs = PackReferenceSet()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_if_missing(spec_id="housing.repairs_social.v1", pack_refs=refs)

    matches = [
        w
        for w in caught
        if issubclass(w.category, UserWarning) and "pack_refs" in str(w.message)
    ]
    assert len(matches) == 1


def test_pack_reference_set_exported_from_top_level():
    import domain_core

    assert hasattr(domain_core, "PackReferenceSet")
    assert hasattr(domain_core, "warn_if_missing")
    assert "PackReferenceSet" in domain_core.__all__
    assert "warn_if_missing" in domain_core.__all__
