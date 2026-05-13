"""Tests for the merits-quality Stage-2 filter."""

from __future__ import annotations

import pytest

from scripts.scrapers.employment_tribunal.filter import (
    keep_unfair_dismissal_merits_only,
)
from scripts.scrapers.employment_tribunal.models import Country, ETCaseMetadata


def _meta(**kwargs) -> ETCaseMetadata:
    base = dict(
        case_reference="case-ref",
        source_url="https://www.gov.uk/employment-tribunal-decisions/case-ref",
        source_license_observed="OGL-3.0",
    )
    base.update(kwargs)
    return ETCaseMetadata(**base)


class TestKeepCleanMerits:
    def test_section_98_judgment_kept(self):
        body = (
            "The tribunal considered section 98 of the Employment Rights Act "
            "1996 and the band of reasonable responses. We find the dismissal "
            "was unfair."
        )
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is True
        assert "unfair_dismissal" in result.matter_types

    def test_polkey_alone_is_sufficient(self):
        body = "A Polkey deduction of 25% would have been appropriate."
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is True


class TestRejectNonMerits:
    @pytest.mark.parametrize(
        "body, expected_reason",
        [
            ("This was a preliminary hearing to set directions.", "preliminary_only"),
            ("The claim is struck out for non-compliance.", "strike_out"),
            ("The claim was withdrawn by the claimant.", "withdrawal"),
            ("This is a reconsideration of the judgment.", "reconsideration"),
            ("Default judgment is entered against the respondent.", "default_judgment"),
            ("This is a remedy hearing only; liability decided previously.", "remedy_only"),
            ("Jurisdiction decision only; merits to follow.", "jurisdiction_only"),
        ],
    )
    def test_pattern_rejects(self, body, expected_reason):
        # Note: include merits language too — the reject patterns should win
        # even when the merits framework is otherwise present.
        body = body + " section 98 ERA 1996 referenced."
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is False, f"expected reject for {expected_reason!r}"
        assert result.reject_reason == expected_reason

    def test_no_merits_signal_rejected(self):
        body = "Some unrelated reasoning about contract law."
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is False
        assert result.reject_reason == "no_unfair_dismissal_merits_signal"

    def test_discrimination_dominated_rejected(self):
        # The discrimination_led fixture inspired this — Equality Act 2010
        # framework dominates a passing UD mention.
        body = (
            "The Equality Act 2010 claim is well-founded. Direct discrimination "
            "and harassment are established. Indirect discrimination is also "
            "made out, alongside victimisation. The unfair-dismissal head "
            "(section 98 ERA 1996) was withdrawn at the start of the hearing."
        )
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is False
        # withdrawal pattern fires first on the "withdrawn" verb — that's an
        # acceptable outcome because withdrawal is also a hard reject reason.
        assert result.reject_reason in {"unfair_dismissal_not_lead_issue", "withdrawal"}

    def test_outcome_level_rejection_preliminary(self):
        meta = _meta(outcome_normalized="preliminary")
        body = "section 98 ERA 1996 mentioned but this is a preliminary issue."
        result = keep_unfair_dismissal_merits_only(meta, body)
        assert result.keep is False
        assert result.reject_reason == "preliminary_only"


class TestExcerpt:
    def test_kept_carries_matched_signal(self):
        body = "The dismissal was unfair under section 98 of the ERA 1996."
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is True
        assert any("98" in s or "unfair" in s.lower() for s in result.matched_signals)

    def test_rejected_carries_excerpt(self):
        body = (
            "This was a preliminary hearing on case management. Section 98 "
            "ERA 1996 was discussed only to scope the merits."
        )
        result = keep_unfair_dismissal_merits_only(_meta(), body)
        assert result.keep is False
        assert result.excerpt is not None
        assert "preliminary" in result.excerpt.lower()
