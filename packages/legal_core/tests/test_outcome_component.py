"""Unit tests for OutcomeComponent and RemedyComponent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_core.graph.outcome_component import (
    OutcomeComponent,
    RemedyComponent,
)


# ---------------------------------------------------------------------------
# OutcomeComponent
# ---------------------------------------------------------------------------


def test_outcome_component_minimum_valid():
    oc = OutcomeComponent(
        outcome_component_id="oc_1",
        outcome_id="fault_finding",
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        confidence=0.8,
    )
    assert oc.outcome_component_id == "oc_1"
    assert oc.outcome_id == "fault_finding"
    assert oc.confidence == 0.8
    assert oc.supporting_factor_ids == []
    assert oc.mitigating_factor_ids == []
    assert oc.supported_by_propositions == []


def test_outcome_component_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        OutcomeComponent(
            outcome_component_id="oc_1",
            outcome_id="fault_finding",
            domain_id="d",
            claim_head_id="ch",
            confidence=0.5,
            unexpected="oops",
        )


def test_outcome_component_frozen_after_construction():
    oc = OutcomeComponent(
        outcome_component_id="oc_1",
        outcome_id="fault_finding",
        domain_id="d",
        claim_head_id="ch",
        confidence=0.5,
    )
    with pytest.raises(ValidationError):
        oc.confidence = 0.9


def test_outcome_component_confidence_lower_bound():
    with pytest.raises(ValidationError):
        OutcomeComponent(
            outcome_component_id="oc_1",
            outcome_id="fault_finding",
            domain_id="d",
            claim_head_id="ch",
            confidence=-0.1,
        )


def test_outcome_component_confidence_upper_bound():
    with pytest.raises(ValidationError):
        OutcomeComponent(
            outcome_component_id="oc_1",
            outcome_id="fault_finding",
            domain_id="d",
            claim_head_id="ch",
            confidence=1.1,
        )


def test_outcome_component_default_lists_are_empty():
    oc = OutcomeComponent(
        outcome_component_id="oc_1",
        outcome_id="fault_finding",
        domain_id="d",
        claim_head_id="ch",
        confidence=0.5,
    )
    assert oc.supporting_factor_ids == []
    assert oc.mitigating_factor_ids == []
    assert oc.supported_by_propositions == []
    # Round-trip via model_dump preserves empty lists.
    dumped = oc.model_dump()
    assert dumped["supporting_factor_ids"] == []
    assert dumped["mitigating_factor_ids"] == []
    assert dumped["supported_by_propositions"] == []


# ---------------------------------------------------------------------------
# RemedyComponent
# ---------------------------------------------------------------------------


def test_remedy_component_minimum_valid():
    rc = RemedyComponent(
        remedy_component_id="rc_1",
        remedy_id="compensation",
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        confidence=0.7,
    )
    assert rc.remedy_component_id == "rc_1"
    assert rc.remedy_id == "compensation"
    assert rc.money_minor_units is None
    assert rc.money_currency is None
    assert rc.supporting_factor_ids == []
    assert rc.supported_by_propositions == []


def test_remedy_component_money_round_trip():
    rc = RemedyComponent(
        remedy_component_id="rc_1",
        remedy_id="compensation",
        domain_id="d",
        claim_head_id="ch",
        confidence=0.7,
        money_minor_units=12000,
        money_currency="GBP",
    )
    assert rc.money_minor_units == 12000
    assert rc.money_currency == "GBP"
    dumped = rc.model_dump()
    assert dumped["money_minor_units"] == 12000
    assert dumped["money_currency"] == "GBP"


def test_remedy_component_money_minor_units_negative_rejected():
    with pytest.raises(ValidationError):
        RemedyComponent(
            remedy_component_id="rc_1",
            remedy_id="compensation",
            domain_id="d",
            claim_head_id="ch",
            confidence=0.5,
            money_minor_units=-1,
            money_currency="GBP",
        )


def test_remedy_component_money_currency_non_gbp_rejected():
    with pytest.raises(ValidationError):
        RemedyComponent(
            remedy_component_id="rc_1",
            remedy_id="compensation",
            domain_id="d",
            claim_head_id="ch",
            confidence=0.5,
            money_minor_units=100,
            money_currency="USD",
        )


def test_remedy_component_money_units_without_currency_rejected():
    with pytest.raises(ValidationError):
        RemedyComponent(
            remedy_component_id="rc_1",
            remedy_id="compensation",
            domain_id="d",
            claim_head_id="ch",
            confidence=0.5,
            money_minor_units=100,
        )


def test_remedy_component_money_currency_without_units_rejected():
    with pytest.raises(ValidationError):
        RemedyComponent(
            remedy_component_id="rc_1",
            remedy_id="compensation",
            domain_id="d",
            claim_head_id="ch",
            confidence=0.5,
            money_currency="GBP",
        )


def test_remedy_component_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        RemedyComponent(
            remedy_component_id="rc_1",
            remedy_id="compensation",
            domain_id="d",
            claim_head_id="ch",
            confidence=0.5,
            unexpected="x",
        )


def test_remedy_component_frozen_after_construction():
    rc = RemedyComponent(
        remedy_component_id="rc_1",
        remedy_id="compensation",
        domain_id="d",
        claim_head_id="ch",
        confidence=0.5,
    )
    with pytest.raises(ValidationError):
        rc.confidence = 0.9
