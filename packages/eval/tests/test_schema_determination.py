"""Tests for the Determination ontology added in 2026-05-06."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from eval.schema import (
    ComplaintFinding,
    Determination,
    GroundTruthOutcome,
    IssueOutcome,
    Winner,
)


class TestDeterminationEnum:
    def test_enum_values(self):
        assert {d.value for d in Determination} == {
            "maladministration",
            "severe_maladministration",
            "service_failure",
            "reasonable_redress",
            "no_maladministration",
            "resolved_with_intervention",
            "outside_jurisdiction",
        }

    def test_legacy_winner_for_handles_every_determination(self):
        from eval.schema import _legacy_winner_for
        # Every Determination value must produce a Winner — guards against a
        # future enum addition that forgets to update _legacy_winner_for.
        seen = set()
        for d in Determination:
            seen.add(_legacy_winner_for(d))
        # Sanity: at least all three Winner values appear in the mapping.
        from eval.schema import Winner
        assert seen == {Winner.TENANT, Winner.LANDLORD, Winner.SPLIT}


class TestComplaintFinding:
    def test_minimal_valid(self):
        cf = ComplaintFinding(
            complaint_label="damp_and_mould",
            finding=Determination.MALADMINISTRATION,
            awarded_gbp=Decimal("250"),
        )
        assert cf.awarded_gbp == Decimal("250")

    def test_default_award_zero(self):
        cf = ComplaintFinding(
            complaint_label="x",
            finding=Determination.NO_MALADMINISTRATION,
        )
        assert cf.awarded_gbp == Decimal("0")

    def test_complaint_label_min_length(self):
        with pytest.raises(ValidationError):
            ComplaintFinding(complaint_label="", finding=Determination.MALADMINISTRATION)

    def test_negative_award_rejected(self):
        with pytest.raises(ValidationError):
            ComplaintFinding(
                complaint_label="x",
                finding=Determination.MALADMINISTRATION,
                awarded_gbp=Decimal("-1"),
            )


class TestGroundTruthOutcomeExtended:
    def _base_unapportioned_kwargs(self, **overrides):
        kwargs = dict(
            overall_winner=Winner.TENANT,
            total_awarded_gbp=Decimal("500"),
            per_issue=[],
            unapportioned_reason="Housing Ombudsman global compensation order.",
        )
        kwargs.update(overrides)
        return kwargs

    def test_legacy_outcome_still_valid(self):
        gto = GroundTruthOutcome(**self._base_unapportioned_kwargs())
        assert gto.determination is None
        assert gto.determination_per_complaint == []
        assert gto.amount_ordered_now_gbp is None
        assert gto.amount_previously_offered_gbp is None
        assert gto.amount_global_unapportioned_gbp is None
        assert gto.overall_winner_legacy is None

    def test_with_determination(self):
        gto = GroundTruthOutcome(
            **self._base_unapportioned_kwargs(
                determination=Determination.MALADMINISTRATION,
                amount_ordered_now_gbp=Decimal("500"),
            )
        )
        assert gto.determination == Determination.MALADMINISTRATION
        assert gto.amount_ordered_now_gbp == Decimal("500")

    def test_with_determination_per_complaint(self):
        gto = GroundTruthOutcome(
            **self._base_unapportioned_kwargs(
                determination=Determination.MALADMINISTRATION,
                determination_per_complaint=[
                    ComplaintFinding(
                        complaint_label="damp_and_mould",
                        finding=Determination.MALADMINISTRATION,
                        awarded_gbp=Decimal("400"),
                    ),
                    ComplaintFinding(
                        complaint_label="complaint_handling",
                        finding=Determination.SERVICE_FAILURE,
                        awarded_gbp=Decimal("100"),
                    ),
                ],
                amount_ordered_now_gbp=Decimal("500"),
            )
        )
        assert len(gto.determination_per_complaint) == 2

    def test_split_amounts_sum_must_not_exceed_total(self):
        # If any of the split amounts is set, sum must equal total_awarded_gbp.
        with pytest.raises(ValidationError, match=r"sum.*amount_(ordered|previously|global)"):
            GroundTruthOutcome(
                **self._base_unapportioned_kwargs(
                    determination=Determination.MALADMINISTRATION,
                    amount_ordered_now_gbp=Decimal("400"),
                    # 400 != 500 total
                )
            )

    def test_split_amounts_can_combine(self):
        gto = GroundTruthOutcome(
            **self._base_unapportioned_kwargs(
                determination=Determination.MALADMINISTRATION,
                amount_ordered_now_gbp=Decimal("200"),
                amount_previously_offered_gbp=Decimal("300"),
                # 200 + 300 == 500 total
            )
        )
        assert gto.amount_ordered_now_gbp + gto.amount_previously_offered_gbp == gto.total_awarded_gbp

    def test_outside_jurisdiction_must_have_zero_amounts(self):
        with pytest.raises(ValidationError, match="outside_jurisdiction"):
            GroundTruthOutcome(
                **self._base_unapportioned_kwargs(
                    overall_winner=Winner.LANDLORD,
                    total_awarded_gbp=Decimal("100"),
                    determination=Determination.OUTSIDE_JURISDICTION,
                    amount_ordered_now_gbp=Decimal("100"),
                )
            )

    def test_outside_jurisdiction_with_nonzero_total_no_split_rejected(self):
        # INV-D2 must trip even when no split fields are set, if total is non-zero.
        with pytest.raises(ValidationError, match="outside_jurisdiction"):
            GroundTruthOutcome(
                **self._base_unapportioned_kwargs(
                    overall_winner=Winner.LANDLORD,
                    total_awarded_gbp=Decimal("100"),
                    determination=Determination.OUTSIDE_JURISDICTION,
                    # No split fields set — INV-D1 should NOT trip; INV-D2 must.
                )
            )

    def test_outside_jurisdiction_zero_total_ok(self):
        gto = GroundTruthOutcome(
            **self._base_unapportioned_kwargs(
                overall_winner=Winner.LANDLORD,
                total_awarded_gbp=Decimal("0"),
                determination=Determination.OUTSIDE_JURISDICTION,
            )
        )
        assert gto.amount_ordered_now_gbp is None

    def test_overall_winner_legacy_derives_from_determination(self):
        # When set, overall_winner_legacy must match the canonical mapping
        gto = GroundTruthOutcome(
            **self._base_unapportioned_kwargs(
                determination=Determination.REASONABLE_REDRESS,
                overall_winner=Winner.LANDLORD,
                overall_winner_legacy=Winner.LANDLORD,
                amount_previously_offered_gbp=Decimal("500"),
            )
        )
        assert gto.overall_winner_legacy == Winner.LANDLORD

    def test_overall_winner_legacy_inconsistent_rejected(self):
        with pytest.raises(ValidationError, match="overall_winner_legacy"):
            GroundTruthOutcome(
                **self._base_unapportioned_kwargs(
                    determination=Determination.MALADMINISTRATION,
                    overall_winner=Winner.TENANT,
                    overall_winner_legacy=Winner.LANDLORD,  # wrong polarity
                    amount_ordered_now_gbp=Decimal("500"),
                )
            )
