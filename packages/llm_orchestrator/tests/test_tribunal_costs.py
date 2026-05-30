"""Unit tests for :func:`get_cost_benefit_analysis` settlement-range handling.

Regression coverage for the mediation ``/expectation`` 500: a degraded or
"uncertain" prediction (e.g. produced when retrieval is unavailable) persists
``predicted_settlement_range=None``. Cost-benefit framing must degrade to £0
rather than raising, so the mediation expectation endpoint cannot 500 on an
uncertain prediction.
"""

import pytest

from llm_orchestrator.data.tribunal_costs import (
    CostBenefitAnalysis,
    get_cost_benefit_analysis,
)


def test_numeric_range_produces_midpoint_amount() -> None:
    analysis = get_cost_benefit_analysis(
        "tenant", {"predicted_settlement_range": [600, 900]}
    )
    assert analysis.settlement_range_low == 600.0
    assert analysis.settlement_range_high == 900.0
    assert analysis.settlement_amount == 750.0


@pytest.mark.parametrize("role", ["tenant", "landlord"])
def test_none_settlement_range_does_not_crash(role: str) -> None:
    # A degraded/uncertain prediction persists predicted_settlement_range=None.
    analysis = get_cost_benefit_analysis(role, {"predicted_settlement_range": None})
    assert isinstance(analysis, CostBenefitAnalysis)
    assert analysis.settlement_range_low == 0.0
    assert analysis.settlement_range_high == 0.0
    assert analysis.settlement_amount == 0.0


@pytest.mark.parametrize("role", ["tenant", "landlord"])
def test_list_of_none_settlement_range_does_not_crash(role: str) -> None:
    analysis = get_cost_benefit_analysis(
        role, {"predicted_settlement_range": [None, None]}
    )
    assert analysis.settlement_range_low == 0.0
    assert analysis.settlement_range_high == 0.0


def test_missing_range_key_defaults_to_zero() -> None:
    analysis = get_cost_benefit_analysis("landlord", {})
    assert analysis.settlement_range_low == 0.0
    assert analysis.settlement_range_high == 0.0


def test_single_element_range_uses_value_for_both_bounds() -> None:
    analysis = get_cost_benefit_analysis("tenant", {"predicted_settlement_range": [500]})
    assert analysis.settlement_range_low == 500.0
    assert analysis.settlement_range_high == 500.0
