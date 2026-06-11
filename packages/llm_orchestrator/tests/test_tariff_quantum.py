"""Tariff quantum: determination + factor severity -> amount estimate and band."""
from llm_orchestrator.models.prediction_v2 import Determination
from llm_orchestrator.pipeline.tariff_quantum import (
    clamp_to_band,
    severity_score,
    tariff_estimate,
)

# Reuse the _fa() FactorAssertion fixture from test_determination_rules.py
from llm_orchestrator.tests.test_determination_rules import _fa


def _enum_fa(factor_id, enum_value, confidence=0.9):
    from legal_core.graph.factor_assertion import (
        ExtractionMethod, FactorAssertion, FactorPolarity,
    )
    from legal_core.graph.factor_value import FactorValue, FactorValueType
    return FactorAssertion(
        factor_assertion_id=f"fa-{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs",
        value=FactorValue(value_type=FactorValueType.ENUM, enum=enum_value),
        value_type=FactorValueType.ENUM,
        confidence=confidence,
        polarity=FactorPolarity.PRO_CLAIMANT,
        supported_by=["span-1"],
        extraction_method=ExtractionMethod.LLM_EXTRACTED,
        extractor_version="test-1.0.0",
    )


def test_severity_default_is_midpoint():
    assert severity_score([]) == 0.5


def test_severity_scales_with_impact_and_aggravators():
    factors = [
        _enum_fa("impact_severity_reported", "severe"),
        _fa("vulnerability_known", boolean=True),
        _fa("repair_delay_days", duration_days=200),
    ]
    assert severity_score(factors) == 1.0  # 0.85 + 0.15 + 0.10 capped at 1.0


def test_maladministration_band_interpolation():
    amount, band = tariff_estimate(Determination.MALADMINISTRATION, [])
    assert band == (100, 1200)
    assert amount == 650  # 100 + round(1100 * 0.5)


def test_zero_band_classes_return_zero():
    amount, band = tariff_estimate(Determination.NO_MALADMINISTRATION, [])
    assert amount == 0.0
    assert band == (0, 0)


def test_severe_band():
    factors = [_enum_fa("impact_severity_reported", "minor")]
    amount, band = tariff_estimate(Determination.SEVERE_MALADMINISTRATION, factors)
    assert band == (600, 3000)
    assert amount == 600 + round(2400 * 0.3)


def test_unknown_determination_returns_none():
    amount, band = tariff_estimate(None, [])
    assert amount is None and band is None


# --- clamp_to_band tests ---

def test_clamp_none_amount_tariff_fill():
    """None amount is filled with tariff estimate (tariff_fill adjustment)."""
    final, band, adj = clamp_to_band(None, Determination.MALADMINISTRATION, [])
    assert adj == "tariff_fill"
    assert band == (100, 1200)
    assert final == 650.0  # 100 + round(1100 * 0.5)


def test_clamp_amount_within_tolerance_kept():
    """Amount within [low*0.5, high*1.5] tolerance is kept as-is (adj None)."""
    final, band, adj = clamp_to_band(300.0, Determination.MALADMINISTRATION, [])
    assert adj is None
    assert final == 300.0
    assert band == (100, 1200)


def test_clamp_amount_below_half_low_snaps_to_low():
    """Amount below low*0.5 (e.g. £40 for maladministration band low=100) snaps to low."""
    final, band, adj = clamp_to_band(40.0, Determination.MALADMINISTRATION, [])
    assert adj == "snap_low"
    assert final == 100.0
    assert band == (100, 1200)


def test_clamp_amount_above_1p5x_high_snaps_to_high():
    """Amount above high*1.5 (e.g. £2000 for maladministration band high=1200) snaps to high."""
    final, band, adj = clamp_to_band(2000.0, Determination.MALADMINISTRATION, [])
    assert adj == "snap_high"
    assert final == 1200.0
    assert band == (100, 1200)


def test_clamp_zero_band_with_nonzero_amount_returns_zero():
    """Zero-band determination (no_maladministration) always returns 0.0."""
    final, band, adj = clamp_to_band(400.0, Determination.NO_MALADMINISTRATION, [])
    assert final == 0.0
    assert band == (0, 0)
    # snap_high is the adjustment since amount > 0 but high==0
    assert adj == "snap_high"


def test_clamp_unknown_determination_returns_amount_unchanged():
    """None determination: band is None, amount passes through unchanged."""
    final, band, adj = clamp_to_band(400.0, None, [])
    assert final == 400.0
    assert band is None
    assert adj is None


# ---------------------------------------------------------------------------
# Gate-independence tests for _apply_determination_postrules
# ---------------------------------------------------------------------------
# _apply_determination_postrules reads nothing from self, so we can use
# IssuePredictor.__new__(IssuePredictor) to get a bare instance without
# triggering the heavy __init__.
# ---------------------------------------------------------------------------

import types

from llm_orchestrator.models.prediction_v2 import (
    Determination,
    IssueOutcome,
    IssueType,
    IssuePrediction,
)
from llm_orchestrator.pipeline.issue_predictor import IssuePredictor


def _make_prediction(determination, amount=None):
    """Return a minimal IssuePrediction with the given determination and amount."""
    return IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        predicted_outcome=IssueOutcome.TENANT_WINS,
        confidence=0.8,
        predicted_determination=determination,
        predicted_amount=amount,
    )


def _make_case_graph(factors):
    """Return a minimal case-graph stub with the given factor_assertions."""
    return types.SimpleNamespace(factor_assertions=factors)


def test_rules_off_tariff_on_fills_amount_and_leaves_determination_unruled(monkeypatch):
    """RULES=0, TARIFF=1: tariff fills None amount; R1 rule does NOT fire.

    The factor list includes issue_outside_jurisdiction=True, which would
    normally trigger R1 and flip the determination to OUTSIDE_JURISDICTION.
    With RULES=0 that must NOT happen.  The tariff DOES run on the raw LLM
    determination (MALADMINISTRATION) and fills the None amount from its band.
    """
    monkeypatch.setenv("STREAM_C_DETERMINATION_RULES", "0")
    monkeypatch.setenv("STREAM_C_TARIFF_QUANTUM", "1")

    # R1 trigger factor (would override determination if rules ran)
    factors = [_fa("issue_outside_jurisdiction", boolean=True)]
    prediction = _make_prediction(Determination.MALADMINISTRATION, amount=None)
    case_graph = _make_case_graph(factors)

    predictor = IssuePredictor.__new__(IssuePredictor)
    result = predictor._apply_determination_postrules(prediction, case_graph)

    # Determination must stay as LLM proposed (rules gate was off)
    assert result.predicted_determination is Determination.MALADMINISTRATION, (
        "R1 must not fire when STREAM_C_DETERMINATION_RULES=0"
    )
    # Amount must be filled by tariff from MALADMINISTRATION band [100, 1200]
    assert result.predicted_amount is not None, (
        "Tariff quantum must fill None amount when STREAM_C_TARIFF_QUANTUM=1"
    )
    assert 100.0 <= result.predicted_amount <= 1200.0, (
        f"Filled amount {result.predicted_amount} outside MALADMINISTRATION band [100, 1200]"
    )


def test_rules_on_tariff_off_fires_rules_leaves_amount_untouched(monkeypatch):
    """RULES=1, TARIFF=0: R1 fires and changes determination; amount is untouched.

    A None amount must remain None (tariff gate is off, so no fill happens).
    """
    monkeypatch.setenv("STREAM_C_DETERMINATION_RULES", "1")
    monkeypatch.setenv("STREAM_C_TARIFF_QUANTUM", "0")

    factors = [_fa("issue_outside_jurisdiction", boolean=True)]
    original_amount = None
    prediction = _make_prediction(Determination.MALADMINISTRATION, amount=original_amount)
    case_graph = _make_case_graph(factors)

    predictor = IssuePredictor.__new__(IssuePredictor)
    result = predictor._apply_determination_postrules(prediction, case_graph)

    # R1 must have fired and changed the determination
    assert result.predicted_determination is Determination.OUTSIDE_JURISDICTION, (
        "R1 must fire and set OUTSIDE_JURISDICTION when STREAM_C_DETERMINATION_RULES=1"
    )
    # Amount must remain untouched (tariff gate is off)
    assert result.predicted_amount is original_amount, (
        "Tariff quantum must not fill amount when STREAM_C_TARIFF_QUANTUM=0"
    )
