"""Tests for determination-class metrics added in 2026-05-06."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from eval.metrics.accuracy import (
    amount_mae_gbp_by_construct,
    determination_accuracy,
    determination_class_recall,
)
from eval.metrics.types import IssuePrediction, Prediction
from eval.schema import (
    CaseSize,
    ClaimType,
    Determination,
    GoldCase,
    GroundTruthOutcome,
    Party,
    PartyRole,
    Provenance,
    ReasoningQuote,
    RegionUK,
    SchemaVersion,
    Winner,
)


def _make_gold(
    case_id: str,
    determination: Determination,
    *,
    amount_ordered: Decimal | None = None,
    amount_offered: Decimal | None = None,
    amount_global: Decimal | None = None,
    total: Decimal = Decimal("0"),
) -> GoldCase:
    overall_winner = Winner.LANDLORD if determination in (
        Determination.REASONABLE_REDRESS,
        Determination.NO_MALADMINISTRATION,
        Determination.OUTSIDE_JURISDICTION,
    ) else Winner.TENANT if determination != Determination.RESOLVED_WITH_INTERVENTION else Winner.SPLIT
    return GoldCase(
        schema_version=SchemaVersion.V1,
        case_id=case_id,
        decision_date=date(2025, 6, 1),
        region=RegionUK.LONDON,
        case_size=CaseSize.UNKNOWN,
        disputed_amount_gbp=None,
        claim_types=[ClaimType.DISREPAIR],
        source_pdf_sha256="0" * 64,
        parties=[
            Party(role=PartyRole.TENANT, represented=False),
            Party(role=PartyRole.LANDLORD, represented=False),
        ],
        facts="x" * 60,
        evidence=[],
        evidence_unavailable_reason="fixture",
        statutory_basis=[],
        statutory_basis_unavailable_reason="fixture",
        ground_truth_outcome=GroundTruthOutcome(
            overall_winner=overall_winner,
            total_awarded_gbp=total,
            per_issue=[],
            unapportioned_reason="Housing Ombudsman global compensation order.",
            determination=determination,
            amount_ordered_now_gbp=amount_ordered,
            amount_previously_offered_gbp=amount_offered,
            amount_global_unapportioned_gbp=amount_global,
        ),
        key_reasoning_quotes=[
            ReasoningQuote(text="example", provenance=Provenance(page=1, paragraph=1)),
        ],
        domain_id="housing.repairs_social.v1",
        matter_type="repairs_disrepair",
    )


def _pred(
    case_id: str,
    *,
    determination: Determination | None = None,
    amount: Decimal | None = None,
    construct: str | None = None,
    overall_winner: Winner = Winner.TENANT,
) -> Prediction:
    return Prediction(
        case_id=case_id,
        overall_winner=overall_winner,
        overall_win_probability=0.5,
        total_predicted_gbp=amount,
        per_issue=[
            IssuePrediction(
                issue="disrepair",
                predicted_winner=overall_winner,
                win_probability=0.5,
                predicted_amount_gbp=amount,
                abstained=False,
                amount_construct=construct,
            )
        ],
        abstained=False,
        predicted_determination=determination,
    )


class TestDeterminationAccuracy:
    def test_all_correct(self):
        gold = [_make_gold("a", Determination.MALADMINISTRATION)]
        preds = [_pred("a", determination=Determination.MALADMINISTRATION)]
        assert determination_accuracy(gold, preds) == 1.0

    def test_all_wrong(self):
        gold = [_make_gold("a", Determination.MALADMINISTRATION)]
        preds = [_pred("a", determination=Determination.NO_MALADMINISTRATION,
                        overall_winner=Winner.LANDLORD)]
        assert determination_accuracy(gold, preds) == 0.0

    def test_missing_prediction_counts_as_wrong(self):
        gold = [_make_gold("a", Determination.MALADMINISTRATION)]
        preds = [_pred("a", determination=None)]
        assert determination_accuracy(gold, preds) == 0.0

    def test_zero_when_no_gold_determination(self):
        # Legacy gold without determination — denom=0 returns 0.0
        legacy_gold = _make_gold("a", Determination.MALADMINISTRATION)
        legacy_gold.ground_truth_outcome.determination = None  # bypass for legacy test
        preds = [_pred("a")]
        assert determination_accuracy([legacy_gold], preds) == 0.0


class TestDeterminationClassRecall:
    def test_recall_per_class(self):
        gold = [
            _make_gold("a", Determination.MALADMINISTRATION),
            _make_gold("b", Determination.MALADMINISTRATION),
            _make_gold("c", Determination.REASONABLE_REDRESS),
        ]
        preds = [
            _pred("a", determination=Determination.MALADMINISTRATION),
            _pred("b", determination=Determination.REASONABLE_REDRESS,
                  overall_winner=Winner.LANDLORD),
            _pred("c", determination=Determination.REASONABLE_REDRESS,
                  overall_winner=Winner.LANDLORD),
        ]
        recalls = determination_class_recall(gold, preds)
        assert recalls[Determination.MALADMINISTRATION] == pytest.approx(0.5)
        assert recalls[Determination.REASONABLE_REDRESS] == pytest.approx(1.0)

    def test_class_absent_from_gold_excluded(self):
        gold = [_make_gold("a", Determination.MALADMINISTRATION)]
        preds = [_pred("a", determination=Determination.MALADMINISTRATION)]
        recalls = determination_class_recall(gold, preds)
        assert Determination.SEVERE_MALADMINISTRATION not in recalls

    def test_empty_when_no_gold_determination(self):
        legacy_gold = _make_gold("a", Determination.MALADMINISTRATION)
        legacy_gold.ground_truth_outcome.determination = None
        preds = [_pred("a")]
        assert determination_class_recall([legacy_gold], preds) == {}


class TestAmountMaeByConstruct:
    def test_ordered_now_only(self):
        gold = [_make_gold(
            "a", Determination.MALADMINISTRATION,
            amount_ordered=Decimal("500"), total=Decimal("500"),
        )]
        preds = [_pred("a", amount=Decimal("400"), construct="ordered_now")]
        assert amount_mae_gbp_by_construct(gold, preds, "ordered_now") == 100.0

    def test_construct_filter_skips_other_classes(self):
        gold = [
            _make_gold("a", Determination.MALADMINISTRATION,
                       amount_ordered=Decimal("500"), total=Decimal("500")),
            _make_gold("b", Determination.REASONABLE_REDRESS,
                       amount_offered=Decimal("1000"), total=Decimal("1000")),
        ]
        preds = [
            _pred("a", amount=Decimal("400"), construct="ordered_now"),
            _pred("b", amount=Decimal("100"), construct="ordered_now",
                  overall_winner=Winner.LANDLORD),
        ]
        # Only case 'a' has ordered_now gold; case 'b' is excluded.
        assert amount_mae_gbp_by_construct(gold, preds, "ordered_now") == 100.0

    def test_no_evaluable_returns_zero(self):
        gold = [_make_gold("a", Determination.OUTSIDE_JURISDICTION)]
        # OUTSIDE_JURISDICTION must have total=0 and all split fields None
        preds = [_pred("a", overall_winner=Winner.LANDLORD)]
        assert amount_mae_gbp_by_construct(gold, preds, "ordered_now") == 0.0

    def test_unknown_construct_raises(self):
        gold = [_make_gold("a", Determination.MALADMINISTRATION,
                           amount_ordered=Decimal("500"), total=Decimal("500"))]
        preds = [_pred("a", amount=Decimal("400"), construct="ordered_now")]
        with pytest.raises(ValueError, match="construct"):
            amount_mae_gbp_by_construct(gold, preds, "bogus")

    def test_missing_predicted_uses_actual_as_error_when_actual_nonzero(self):
        gold = [_make_gold("a", Determination.MALADMINISTRATION,
                           amount_ordered=Decimal("500"), total=Decimal("500"))]
        # Prediction has no amount (None)
        preds = [_pred("a", amount=None, construct=None)]
        assert amount_mae_gbp_by_construct(gold, preds, "ordered_now") == 500.0

    def test_missing_predicted_zero_error_when_actual_zero(self):
        # Construct field explicitly set to Decimal("0") with total=0.
        gold = [_make_gold("a", Determination.MALADMINISTRATION,
                           amount_ordered=Decimal("0"), total=Decimal("0"))]
        preds = [_pred("a", amount=None, construct=None)]
        assert amount_mae_gbp_by_construct(gold, preds, "ordered_now") == 0.0
