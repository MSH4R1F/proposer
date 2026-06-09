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
    assert band == (100, 600)
    assert amount == 350  # 100 + 500 * 0.5


def test_zero_band_classes_return_zero():
    amount, band = tariff_estimate(Determination.NO_MALADMINISTRATION, [])
    assert amount == 0.0
    assert band == (0, 0)


def test_severe_band():
    factors = [_enum_fa("impact_severity_reported", "minor")]
    amount, band = tariff_estimate(Determination.SEVERE_MALADMINISTRATION, factors)
    assert band == (600, 2000)
    assert amount == 600 + round(1400 * 0.3)


def test_unknown_determination_returns_none():
    amount, band = tariff_estimate(None, [])
    assert amount is None and band is None


# --- clamp_to_band tests ---

def test_clamp_none_amount_tariff_fill():
    """None amount is filled with tariff estimate (tariff_fill adjustment)."""
    final, band, adj = clamp_to_band(None, Determination.MALADMINISTRATION, [])
    assert adj == "tariff_fill"
    assert band == (100, 600)
    assert final == 350.0  # midpoint estimate


def test_clamp_amount_within_tolerance_kept():
    """Amount within [low*0.5, high*1.5] tolerance is kept as-is (adj None)."""
    final, band, adj = clamp_to_band(300.0, Determination.MALADMINISTRATION, [])
    assert adj is None
    assert final == 300.0
    assert band == (100, 600)


def test_clamp_amount_below_half_low_snaps_to_low():
    """Amount below low*0.5 (e.g. £40 for maladministration band low=100) snaps to low."""
    final, band, adj = clamp_to_band(40.0, Determination.MALADMINISTRATION, [])
    assert adj == "snap_low"
    assert final == 100.0
    assert band == (100, 600)


def test_clamp_amount_above_1p5x_high_snaps_to_high():
    """Amount above high*1.5 (e.g. £1000 for maladministration band high=600) snaps to high."""
    final, band, adj = clamp_to_band(1000.0, Determination.MALADMINISTRATION, [])
    assert adj == "snap_high"
    assert final == 600.0
    assert band == (100, 600)


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
