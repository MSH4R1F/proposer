"""Tests for eval.compare — multi-mode comparison report.

The comparison report is the thesis's RQ1 artifact: it shows whether the
hybrid pipeline beats RAG-only / KG-only / LLM-only on accuracy,
calibration, and amount estimation. Bootstrap CIs let us decide whether
"better" is significant or just noise within the 50-case sample.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from eval.compare import (
    ComparisonReport,
    ModeMetrics,
    build_comparison_report,
    report_to_dict,
    summarise_dominance,
)
from eval.metrics import IssuePrediction, Prediction
from eval.schema import Winner


# ---------- Fixtures ----------


def _build_gold_corpus():
    """Re-use the existing 10-case synthetic corpus that ships with eval.tests."""
    from pathlib import Path

    from eval.dataset import load

    fixtures = Path(__file__).parent / "fixtures"
    return load("synthetic_corpus_10", base_dir=fixtures, strict=True).cases


def _perfect_predictions(gold: list) -> list:
    """Predictions that exactly match every gold case (accuracy=1.0,
    Brier=0).

    Calibration's binary coding (see eval.metrics.calibration._iter_probability_pairs):
    actual=1 if landlord won outright, else 0. So for a perfect
    Brier-zero score, SPLIT cases must be predicted with P(landlord)=0.
    """
    out = []
    for g in gold:
        gt = g.ground_truth_outcome
        # P(landlord wins outright): 1.0 only when landlord won, 0.0 otherwise.
        p_landlord = 1.0 if gt.overall_winner is Winner.LANDLORD else 0.0
        per_issue = []
        for io in gt.per_issue:
            p = 1.0 if io.winner is Winner.LANDLORD else 0.0
            per_issue.append(
                IssuePrediction(
                    issue=io.issue,
                    predicted_winner=io.winner,
                    win_probability=p,
                    predicted_amount_gbp=io.awarded_gbp,
                )
            )
        out.append(
            Prediction(
                case_id=g.case_id,
                overall_winner=gt.overall_winner,
                overall_win_probability=p_landlord,
                total_predicted_gbp=gt.total_awarded_gbp,
                per_issue=per_issue,
            )
        )
    return out


def _flipped_predictions(gold: list) -> list:
    """Predictions that flip the winner on every case (accuracy ≈ 0)."""
    out = []
    flip = {
        Winner.TENANT: Winner.LANDLORD,
        Winner.LANDLORD: Winner.TENANT,
        Winner.SPLIT: Winner.SPLIT,
    }
    for g in gold:
        gt = g.ground_truth_outcome
        new_overall = flip[gt.overall_winner]
        if new_overall is Winner.LANDLORD:
            p_landlord = 0.95
        elif new_overall is Winner.TENANT:
            p_landlord = 0.05
        else:
            p_landlord = 0.5
        per_issue = []
        for io in gt.per_issue:
            new_w = flip[io.winner]
            if new_w is Winner.LANDLORD:
                p = 0.95
            elif new_w is Winner.TENANT:
                p = 0.05
            else:
                p = 0.5
            per_issue.append(
                IssuePrediction(
                    issue=io.issue,
                    predicted_winner=new_w,
                    win_probability=p,
                    predicted_amount_gbp=io.awarded_gbp,
                )
            )
        out.append(
            Prediction(
                case_id=g.case_id,
                overall_winner=new_overall,
                overall_win_probability=p_landlord,
                total_predicted_gbp=gt.total_awarded_gbp,
                per_issue=per_issue,
            )
        )
    return out


def _coinflip_predictions(gold: list) -> list:
    """Always say SPLIT with P(landlord)=0.5. Brier = 0.25 (worst case)
    and accuracy = (#split cases / total)."""
    out = []
    for g in gold:
        gt = g.ground_truth_outcome
        per_issue = [
            IssuePrediction(
                issue=io.issue,
                predicted_winner=Winner.SPLIT,
                win_probability=0.5,
                predicted_amount_gbp=Decimal("0"),
            )
            for io in gt.per_issue
        ]
        out.append(
            Prediction(
                case_id=g.case_id,
                overall_winner=Winner.SPLIT,
                overall_win_probability=0.5,
                total_predicted_gbp=Decimal("0"),
                per_issue=per_issue,
            )
        )
    return out


def _ombudsman_legacy_outcome_amount_gold():
    """Gold row shaped like the first reviewed Ombudsman artifact.

    The final global compensation order appears in legacy pre-decision amount
    fields, which comparison baselines must not treat as claimant demands.
    """
    from eval.schema import GoldCase

    return GoldCase.model_validate(
        {
            "schema_version": "v1",
            "case_id": "housing-ombudsman-legacy-amount",
            "decision_date": "2025-10-23",
            "region": "london",
            "region_source": "London",
            "case_size": "small",
            "disputed_amount_gbp": "575.00",
            "claim_types": ["disrepair"],
            "source_pdf_sha256": "a" * 64,
            "ocr_confidence": None,
            "parties": [
                {"role": "tenant", "represented": False},
                {"role": "landlord", "represented": False},
            ],
            "facts": (
                "Resident complained about repeated repair delays, damp and "
                "mould, and poor complaint handling before the Ombudsman "
                "issued a global compensation order."
            ),
            "evidence": [
                {
                    "kind": "ombudsman_record",
                    "description": "Housing Ombudsman determination record.",
                    "provenance": {"page": 1, "paragraph": 22},
                }
            ],
            "statutory_basis": [],
            "statutory_basis_unavailable_reason": (
                "Housing Ombudsman determination; statutory basis not extracted."
            ),
            "claimed_amounts": [
                {
                    "issue": "ombudsman_compensation",
                    "amount_gbp": "575.00",
                    "by_party": "tenant",
                }
            ],
            "ground_truth_outcome": {
                "overall_winner": "tenant",
                "total_awarded_gbp": "575.00",
                "per_issue": [],
                "unapportioned_reason": (
                    "Housing Ombudsman determination made a global compensation "
                    "order without apportioning the final total."
                ),
            },
            "key_reasoning_quotes": [
                {
                    "text": "The landlord must pay the resident £575.",
                    "provenance": {"page": 1, "paragraph": 78},
                }
            ],
            "domain_id": "housing.repairs_social.v1",
            "forum": "housing_ombudsman",
            "source_kind": "ombudsman_determination",
            "source_publisher": "housing_ombudsman",
            "retrieval_namespace_id": "housing_repairs_social_v1",
            "target_source_id": "legacy-amount",
            "corpus_version": "research_seed_2026_05",
            "matter_type": "repairs_damp_mould",
        }
    )


# ---------- Tests ----------


class TestStructure:
    def test_report_contains_all_modes(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold,
            {
                "hybrid": _perfect_predictions(gold),
                "rag_only": _perfect_predictions(gold),
                "kg_only": _flipped_predictions(gold),
                "llm_only": _coinflip_predictions(gold),
            },
            n_resamples=0,  # skip bootstrap for speed
        )
        assert isinstance(report, ComparisonReport)
        assert {m.mode for m in report.modes} == {
            "hybrid",
            "rag_only",
            "kg_only",
            "llm_only",
        }

    def test_each_mode_has_all_four_metrics(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0
        )
        m = report.modes[0]
        assert m.accuracy is not None
        assert m.amount_threshold is not None
        assert m.amount_within_20pct is not None
        assert m.amount_within_gbp100 is not None
        assert m.amount_mae_gbp is not None
        assert m.amount_median_absolute_error_gbp is not None
        assert m.amount_mean_signed_error_gbp is not None
        assert m.amount_coverage["n_evaluable"] == len(gold)
        assert m.brier is not None
        assert m.ece is not None

    def test_report_dict_keeps_legacy_amount_key_and_adds_amount_object(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0
        )
        row = report_to_dict(report)["modes"][0]
        assert row["amount_threshold"]["point"] == pytest.approx(1.0)
        assert row["amount"]["within_20pct"]["point"] == pytest.approx(1.0)
        assert row["amount"]["within_gbp100"]["point"] == pytest.approx(1.0)
        assert row["amount"]["mae_gbp"]["point"] == pytest.approx(0.0)
        assert row["amount"]["coverage"]["n_evaluable"] == len(gold)

    def test_deterministic_baselines_are_reported_separately(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0
        )
        payload = report_to_dict(report)
        baselines = {row["baseline"]: row for row in payload["baselines"]}
        assert set(baselines) == {
            "always_tenant",
            "always_landlord",
            "claim_positive_winner",
            "claim_amount_copy",
        }
        assert baselines["always_tenant"]["supported"]["winner"] is True
        assert baselines["always_tenant"]["supported"]["amount"] is False
        assert baselines["always_tenant"]["amount"]["coverage"][
            "missing_predicted_amount"
        ] == len(gold)
        assert baselines["claim_amount_copy"]["supported"]["amount"] is True
        assert baselines["claim_amount_copy"]["amount"]["coverage"][
            "n_evaluable"
        ] == len(gold)

    def test_ombudsman_outcome_amounts_do_not_feed_claim_copy_baseline(self):
        gold = [_ombudsman_legacy_outcome_amount_gold()]
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0
        )

        baselines = {
            row["baseline"]: row for row in report_to_dict(report)["baselines"]
        }
        claim_copy = baselines["claim_amount_copy"]
        assert claim_copy["supported"]["winner"] is False
        assert claim_copy["supported"]["amount"] is False
        assert claim_copy["amount"]["coverage"]["n_evaluable"] == 0
        assert claim_copy["amount"]["coverage"]["missing_predicted_amount"] == 1

    def test_n_cases_recorded(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0
        )
        assert report.n_cases == len(gold)

    def test_seed_recorded(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0, seed=7
        )
        assert report.seed == 7


class TestMetricCorrectness:
    def test_perfect_predictions_yield_perfect_accuracy(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"hybrid": _perfect_predictions(gold)}, n_resamples=0
        )
        m = next(m for m in report.modes if m.mode == "hybrid")
        assert m.accuracy.point == pytest.approx(1.0)
        # Brier = 0 for perfect 0/1 calls matching ground truth
        assert m.brier.point == pytest.approx(0.0)

    def test_coinflip_yields_brier_at_quarter(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold, {"llm_only": _coinflip_predictions(gold)}, n_resamples=0
        )
        m = report.modes[0]
        assert m.brier.point == pytest.approx(0.25)


class TestRanking:
    def test_perfect_beats_flipped_on_accuracy(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold,
            {
                "hybrid": _perfect_predictions(gold),
                "rag_only": _flipped_predictions(gold),
            },
            n_resamples=0,
        )
        ranked = report.ranked_by("accuracy")
        assert ranked[0].mode == "hybrid"
        assert ranked[1].mode == "rag_only"

    def test_brier_ranks_lower_first(self):
        """Lower-is-better metric: ranking puts perfect (Brier=0) before
        coinflip (Brier=0.25)."""
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold,
            {
                "hybrid": _perfect_predictions(gold),
                "llm_only": _coinflip_predictions(gold),
            },
            n_resamples=0,
        )
        ranked = report.ranked_by("brier")
        assert ranked[0].mode == "hybrid"
        assert ranked[1].mode == "llm_only"


class TestBootstrapIntegration:
    def test_with_bootstrap_emits_ci_band(self):
        gold = _build_gold_corpus()
        report = build_comparison_report(
            gold,
            {"hybrid": _perfect_predictions(gold)},
            n_resamples=200,
            seed=42,
        )
        m = report.modes[0]
        # With perfect predictions there's no variance: lower==point==upper.
        assert m.accuracy.lower_95 == pytest.approx(m.accuracy.point)
        assert m.accuracy.upper_95 == pytest.approx(m.accuracy.point)
        # n_resamples is recorded.
        assert m.accuracy.n_resamples == 200

    def test_seed_determinism(self):
        gold = _build_gold_corpus()
        # Use coinflip predictions so there's variance to resample
        preds = _coinflip_predictions(gold)
        report1 = build_comparison_report(
            gold, {"llm_only": preds}, n_resamples=200, seed=42
        )
        report2 = build_comparison_report(
            gold, {"llm_only": preds}, n_resamples=200, seed=42
        )
        m1 = report1.modes[0].brier
        m2 = report2.modes[0].brier
        assert m1.lower_95 == m2.lower_95
        assert m1.upper_95 == m2.upper_95


class TestDominance:
    def test_dominates_when_lower_ci_above_other_upper(self):
        """A mode dominates another on a higher-is-better metric when its
        lower CI bound exceeds the other's upper CI bound."""
        a = ModeMetrics(
            mode="hybrid",
            accuracy=_metric_result(point=0.85, lower=0.78, upper=0.91),
            amount_threshold=_metric_result(point=0.70, lower=0.60, upper=0.80),
            brier=_metric_result(point=0.10, lower=0.07, upper=0.13),
            ece=_metric_result(point=0.05, lower=0.03, upper=0.08),
        )
        b = ModeMetrics(
            mode="kg_only",
            accuracy=_metric_result(point=0.55, lower=0.45, upper=0.65),
            amount_threshold=_metric_result(point=0.30, lower=0.20, upper=0.40),
            brier=_metric_result(point=0.30, lower=0.27, upper=0.33),
            ece=_metric_result(point=0.18, lower=0.15, upper=0.21),
        )
        outcome = summarise_dominance(a, b)
        # On accuracy a's lower (0.78) > b's upper (0.65) → a dominates b.
        assert outcome["accuracy"] == "a_dominates"
        # On Brier (lower-is-better) a's upper (0.13) < b's lower (0.27) → a dominates.
        assert outcome["brier"] == "a_dominates"

    def test_no_dominance_when_cis_overlap(self):
        a = ModeMetrics(
            mode="hybrid",
            accuracy=_metric_result(point=0.75, lower=0.65, upper=0.85),
            amount_threshold=_metric_result(point=0.60, lower=0.50, upper=0.70),
            brier=_metric_result(point=0.18, lower=0.15, upper=0.22),
            ece=_metric_result(point=0.10, lower=0.07, upper=0.13),
        )
        b = ModeMetrics(
            mode="rag_only",
            accuracy=_metric_result(point=0.72, lower=0.62, upper=0.82),
            amount_threshold=_metric_result(point=0.55, lower=0.45, upper=0.65),
            brier=_metric_result(point=0.20, lower=0.17, upper=0.24),
            ece=_metric_result(point=0.12, lower=0.09, upper=0.15),
        )
        outcome = summarise_dominance(a, b)
        # CIs overlap on every metric → no_dominance.
        assert outcome["accuracy"] == "no_dominance"
        assert outcome["brier"] == "no_dominance"
        assert outcome["amount_threshold"] == "no_dominance"
        assert outcome["ece"] == "no_dominance"


class TestErrors:
    def test_empty_gold_raises(self):
        with pytest.raises(ValueError):
            build_comparison_report([], {"hybrid": []}, n_resamples=0)

    def test_no_modes_raises(self):
        gold = _build_gold_corpus()
        with pytest.raises(ValueError):
            build_comparison_report(gold, {}, n_resamples=0)

    def test_misaligned_predictions_raises(self):
        gold = _build_gold_corpus()
        # Drop one prediction — length mismatch → bootstrap_ci will raise.
        bad = _perfect_predictions(gold)[:-1]
        with pytest.raises(ValueError):
            build_comparison_report(gold, {"hybrid": bad}, n_resamples=0)


# Helper to build MetricResult for dominance tests
def _metric_result(*, point: float, lower: float, upper: float):
    from eval.metrics.types import MetricResult

    return MetricResult(
        point=point, lower_95=lower, upper_95=upper, n=50, n_resamples=1000
    )
