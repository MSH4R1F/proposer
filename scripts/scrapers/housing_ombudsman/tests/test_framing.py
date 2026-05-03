"""Verify the housing.repairs_social.v1 forum profile prohibits court-damages framing.

This is a tiny string-membership check on the YAML — no pipeline needed.
"""

from __future__ import annotations

from domain_core.registry import load_domain_specs


def test_repairs_social_forum_prohibits_tribunal_award_framing():
    specs = load_domain_specs()
    spec = specs["housing.repairs_social.v1"]
    profiles = [
        p for p in spec.forum_profiles if p.forum.value == "housing_ombudsman"
    ]
    assert len(profiles) == 1, (
        f"expected exactly one housing_ombudsman forum profile, "
        f"got {len(profiles)}"
    )
    profile = profiles[0]
    prohibited = list(profile.prohibited_phrases)
    assert "the tribunal would award" in prohibited
    assert "court damages" in prohibited
    assert "the court will order" in prohibited


def test_repairs_social_forum_required_disclaimer_is_information_not_advice():
    specs = load_domain_specs()
    spec = specs["housing.repairs_social.v1"]
    profile = next(
        p for p in spec.forum_profiles if p.forum.value == "housing_ombudsman"
    )
    text = " ".join(profile.required_disclaimers).lower()
    assert "not legal advice" in text
    assert "ombudsman" in text
