"""Unit tests for FactorValue typed value carrier."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from legal_core.graph.factor_value import FactorValue, FactorValueType


def test_boolean_value_round_trip():
    fv = FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True)
    assert fv.boolean is True
    assert fv.number is None
    assert fv.value_type is FactorValueType.BOOLEAN


def test_money_value_uses_minor_units_and_currency():
    fv = FactorValue(
        value_type=FactorValueType.MONEY,
        money_minor_units=12345,  # GBP 123.45
        money_currency="GBP",
    )
    assert fv.money_minor_units == 12345
    assert fv.money_currency == "GBP"


def test_money_requires_currency_when_minor_units_set():
    with pytest.raises(ValidationError):
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=100,
            money_currency=None,
        )


def test_duration_uses_days():
    fv = FactorValue(value_type=FactorValueType.DURATION, duration_days=42)
    assert fv.duration_days == 42


def test_date_value():
    fv = FactorValue(value_type=FactorValueType.DATE, date=date(2026, 5, 6))
    assert fv.date == date(2026, 5, 6)


def test_enum_value():
    fv = FactorValue(value_type=FactorValueType.ENUM, enum="conduct")
    assert fv.enum == "conduct"


def test_number_value():
    fv = FactorValue(value_type=FactorValueType.NUMBER, number=3.14)
    assert fv.number == 3.14


def test_value_type_must_match_populated_field():
    with pytest.raises(ValidationError):
        FactorValue(value_type=FactorValueType.BOOLEAN, number=1.0)


def test_at_most_one_typed_field_populated():
    with pytest.raises(ValidationError):
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True, number=1.0)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        FactorValue(
            value_type=FactorValueType.BOOLEAN,
            boolean=True,
            unexpected_field="oops",
        )


def test_immutable():
    fv = FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True)
    with pytest.raises(ValidationError):
        fv.boolean = False


def test_currency_only_gbp_allowed():
    with pytest.raises(ValidationError):
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=100,
            money_currency="USD",
        )
