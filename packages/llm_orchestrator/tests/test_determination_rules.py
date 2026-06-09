"""Rules-then-LLM determination layer over FactorAssertions."""
from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from llm_orchestrator.models.prediction_v2 import Determination
from llm_orchestrator.pipeline.determination_rules import apply_determination_rules


def _fa(factor_id, *, boolean=None, duration_days=None, confidence=0.9,
        polarity=FactorPolarity.NEUTRAL):
    if boolean is not None:
        value = FactorValue(value_type=FactorValueType.BOOLEAN, boolean=boolean)
        vt = FactorValueType.BOOLEAN
    else:
        value = FactorValue(value_type=FactorValueType.DURATION, duration_days=duration_days)
        vt = FactorValueType.DURATION
    return FactorAssertion(
        factor_assertion_id=f"fa-{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs",
        value=value,
        value_type=vt,
        confidence=confidence,
        polarity=polarity,
        supported_by=["span-1"],
        extraction_method=ExtractionMethod.LLM_EXTRACTED,
        extractor_version="test-1.0.0",
    )


def test_jurisdiction_rule_overrides():
    det, rule = apply_determination_rules(
        Determination.MALADMINISTRATION, predicted_amount=400.0,
        factors=[_fa("issue_outside_jurisdiction", boolean=True)],
    )
    assert det is Determination.OUTSIDE_JURISDICTION
    assert rule == "R1_outside_jurisdiction"


def test_severe_upgrade_needs_two_aggravators():
    factors = [
        _fa("vulnerability_known", boolean=True),
        _fa("repair_delay_days", duration_days=400),
    ]
    det, rule = apply_determination_rules(
        Determination.MALADMINISTRATION, predicted_amount=600.0, factors=factors)
    assert det is Determination.SEVERE_MALADMINISTRATION
    assert rule == "R2_severe_upgrade"


def test_single_aggravator_does_not_upgrade():
    factors = [_fa("vulnerability_known", boolean=True)]
    det, rule = apply_determination_rules(
        Determination.MALADMINISTRATION, predicted_amount=400.0, factors=factors)
    assert det is Determination.MALADMINISTRATION
    assert rule is None


def test_reasonable_redress_requires_prior_offer_and_no_fresh_award():
    factors = [_fa("prior_compensation_or_apology_offered", boolean=True)]
    det, rule = apply_determination_rules(
        Determination.MALADMINISTRATION, predicted_amount=None, factors=factors)
    assert det is Determination.REASONABLE_REDRESS
    assert rule == "R3_reasonable_redress"


def test_reasonable_redress_not_applied_when_fresh_award_predicted():
    factors = [_fa("prior_compensation_or_apology_offered", boolean=True)]
    det, rule = apply_determination_rules(
        Determination.MALADMINISTRATION, predicted_amount=350.0, factors=factors)
    assert det is Determination.MALADMINISTRATION
    assert rule is None


def test_low_confidence_factors_ignored():
    factors = [_fa("issue_outside_jurisdiction", boolean=True, confidence=0.5)]
    det, rule = apply_determination_rules(
        Determination.MALADMINISTRATION, predicted_amount=400.0, factors=factors)
    assert det is Determination.MALADMINISTRATION
    assert rule is None


def test_no_factors_is_a_noop():
    det, rule = apply_determination_rules(
        Determination.SERVICE_FAILURE, predicted_amount=100.0, factors=[])
    assert det is Determination.SERVICE_FAILURE
    assert rule is None
