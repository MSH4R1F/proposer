"""Tests for the Determination ontology added in 2026-05-06."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from eval.schema import (
    ComplaintFinding,
    Determination,
)


class TestDeterminationEnum:
    def test_enum_values(self):
        assert Determination.MALADMINISTRATION.value == "maladministration"
        assert Determination.SEVERE_MALADMINISTRATION.value == "severe_maladministration"
        assert Determination.SERVICE_FAILURE.value == "service_failure"
        assert Determination.REASONABLE_REDRESS.value == "reasonable_redress"
        assert Determination.NO_MALADMINISTRATION.value == "no_maladministration"
        assert Determination.RESOLVED_WITH_INTERVENTION.value == "resolved_with_intervention"
        assert Determination.OUTSIDE_JURISDICTION.value == "outside_jurisdiction"


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
