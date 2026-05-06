"""Tests that the housing prompt pack includes Determination + amount_construct
instructions (so a future refactor doesn't silently delete them)."""

from llm_orchestrator.prompts.packs.housing_repairs_social_v1 import (
    _OMBUDSMAN_PREDICTION_SYSTEM,
)
from llm_orchestrator.prompts.prediction_v2 import IRAC_JSON_SCHEMA


def test_irac_json_schema_includes_amount_construct():
    assert '"amount_construct"' in IRAC_JSON_SCHEMA
    assert "ordered_now" in IRAC_JSON_SCHEMA
    assert "previously_offered" in IRAC_JSON_SCHEMA
    assert "global_unapportioned" in IRAC_JSON_SCHEMA


def test_irac_json_schema_includes_predicted_determination():
    assert '"predicted_determination"' in IRAC_JSON_SCHEMA
    # All 7 Determination values must appear in the example.
    for value in (
        "maladministration",
        "severe_maladministration",
        "service_failure",
        "reasonable_redress",
        "no_maladministration",
        "resolved_with_intervention",
        "outside_jurisdiction",
    ):
        assert value in IRAC_JSON_SCHEMA


def test_irac_json_rules_explain_amount_construct():
    assert "amount_construct" in IRAC_JSON_SCHEMA
    assert "fresh Ombudsman compensation order" in IRAC_JSON_SCHEMA


def test_housing_prompt_includes_determination_block():
    assert "DETERMINATION CLASS" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "reasonable_redress" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "outside_jurisdiction" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "resolved_with_intervention" in _OMBUDSMAN_PREDICTION_SYSTEM


def test_housing_prompt_includes_amount_construct_block():
    assert "AMOUNT CONSTRUCT" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "previously_offered" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "ordered_now" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "global_unapportioned" in _OMBUDSMAN_PREDICTION_SYSTEM


def test_housing_prompt_includes_abstain_triggers():
    assert "ABSTAIN TRIGGERS" in _OMBUDSMAN_PREDICTION_SYSTEM
    assert "outside_jurisdiction" in _OMBUDSMAN_PREDICTION_SYSTEM
