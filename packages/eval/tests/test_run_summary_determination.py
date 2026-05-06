"""Tests that the per-mode summary block includes the new determination
metrics (Task 7).

The summary.json `modes` block consumed by the thesis is built by
`run_full_eval.py` from the ablation report produced by
`eval.compare.build_comparison_report` (whose per-mode helper is
`_compute_mode_metrics`, rendered to dict by `_mode_metrics_to_dict` /
`_amount_metrics_to_dict`). This test exercises the public entry point
`build_comparison_report` plus `report_to_dict`, which is what the
ablate CLI / run_full_eval orchestrator actually emit.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from eval.compare import build_comparison_report, report_to_dict
from eval.metrics.types import IssuePrediction, Prediction
from eval.schema import (
    CaseSize,
    ClaimType,
    ClaimedAmount,
    Determination,
    GoldCase,
    GroundTruthOutcome,
    IssueOutcome,
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
    if determination in (
        Determination.REASONABLE_REDRESS,
        Determination.NO_MALADMINISTRATION,
        Determination.OUTSIDE_JURISDICTION,
    ):
        overall_winner = Winner.LANDLORD
    elif determination == Determination.RESOLVED_WITH_INTERVENTION:
        overall_winner = Winner.SPLIT
    else:
        overall_winner = Winner.TENANT
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
            )
        ],
        abstained=False,
        predicted_determination=determination,
    )


class TestPerModeSummaryDetermination:
    """The per-mode amount sub-dict gains three construct-keyed MAE keys
    and the per-mode payload gains a top-level `determination` block."""

    def test_amount_block_exposes_per_construct_mae(self):
        gold = [
            _make_gold(
                "a",
                Determination.MALADMINISTRATION,
                amount_ordered=Decimal("500"),
                total=Decimal("500"),
            ),
            _make_gold(
                "b",
                Determination.MALADMINISTRATION,
                amount_ordered=Decimal("300"),
                total=Decimal("300"),
            ),
        ]
        preds = [
            _pred(
                "a",
                determination=Determination.MALADMINISTRATION,
                amount=Decimal("400"),
            ),
            _pred(
                "b",
                determination=Determination.SERVICE_FAILURE,
                amount=Decimal("250"),
            ),
        ]
        report = build_comparison_report(
            gold,
            {"hybrid": preds},
            n_resamples=0,
            seed=0,
        )
        payload = report_to_dict(report)
        amount = payload["modes"][0]["amount"]
        assert "mae_gbp_ordered_now" in amount
        assert "mae_gbp_previously_offered" in amount
        assert "mae_gbp_global_unapportioned" in amount
        # |400-500| + |250-300| = 100 + 50, average = 75
        assert amount["mae_gbp_ordered_now"] == pytest.approx(75.0)
        # Nothing in those constructs in the gold -> 0.0
        assert amount["mae_gbp_previously_offered"] == pytest.approx(0.0)
        assert amount["mae_gbp_global_unapportioned"] == pytest.approx(0.0)

    def test_determination_block_exposes_accuracy_and_class_recall(self):
        gold = [
            _make_gold(
                "a",
                Determination.MALADMINISTRATION,
                amount_ordered=Decimal("500"),
                total=Decimal("500"),
            ),
            _make_gold(
                "b",
                Determination.MALADMINISTRATION,
                amount_ordered=Decimal("300"),
                total=Decimal("300"),
            ),
        ]
        preds = [
            _pred("a", determination=Determination.MALADMINISTRATION),
            _pred("b", determination=Determination.SERVICE_FAILURE),
        ]
        report = build_comparison_report(
            gold,
            {"hybrid": preds},
            n_resamples=0,
            seed=0,
        )
        payload = report_to_dict(report)
        mode_row = payload["modes"][0]
        assert "determination" in mode_row
        det = mode_row["determination"]
        # 1/2 correct
        assert det["accuracy"] == pytest.approx(0.5)
        # Only MALADMINISTRATION is in gold; recall = 1/2
        assert "maladministration" in det["class_recall"]
        assert det["class_recall"]["maladministration"] == pytest.approx(0.5)
        assert det["n_with_gold_determination"] == 2

    def test_legacy_gold_without_determination_yields_zeros_and_empty_recall(self):
        """Legacy housing_v1 gold (no determination set) must keep producing the
        same numbers it always has — the new metrics default to 0.0 / {}."""

        # Legacy gold: no domain_id (pre-Ombudsman housing_v1 deposits/RRO style).
        # disputed_amount_gbp + claimed_amounts required; per_issue must align.
        gold_case = GoldCase(
            schema_version=SchemaVersion.V1,
            case_id="legacy-1",
            decision_date=date(2024, 6, 1),
            region=RegionUK.LONDON,
            case_size=CaseSize.SMALL,
            disputed_amount_gbp=Decimal("100"),
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
            claimed_amounts=[
                ClaimedAmount(
                    issue="disrepair",
                    amount_gbp=Decimal("100"),
                    by_party=PartyRole.TENANT,
                ),
            ],
            ground_truth_outcome=GroundTruthOutcome(
                overall_winner=Winner.TENANT,
                total_awarded_gbp=Decimal("100"),
                per_issue=[
                    IssueOutcome(
                        issue="disrepair",
                        winner=Winner.TENANT,
                        awarded_gbp=Decimal("100"),
                    ),
                ],
            ),
            key_reasoning_quotes=[
                ReasoningQuote(
                    text="example",
                    provenance=Provenance(page=1, paragraph=1),
                ),
            ],
        )
        preds = [_pred("legacy-1", determination=None)]
        report = build_comparison_report(
            [gold_case],
            {"hybrid": preds},
            n_resamples=0,
            seed=0,
        )
        payload = report_to_dict(report)
        amount = payload["modes"][0]["amount"]
        assert amount["mae_gbp_ordered_now"] == pytest.approx(0.0)
        assert amount["mae_gbp_previously_offered"] == pytest.approx(0.0)
        assert amount["mae_gbp_global_unapportioned"] == pytest.approx(0.0)
        det = payload["modes"][0]["determination"]
        assert det["accuracy"] == pytest.approx(0.0)
        assert det["class_recall"] == {}
        assert det["n_with_gold_determination"] == 0
