"""Determination→outcome consistency mapping (STREAM_C_DET_OUTCOME_CONSISTENCY).

Ombudsman repairs semantics: any upheld failing (incl. reasonable_redress:
offer ordered to be honoured) is a resident-favourable outcome.
outside_jurisdiction and no_maladministration map to landlord_wins;
all other non-None determinations map to tenant_wins.
"""
import types

import pytest

from llm_orchestrator.models.prediction_v2 import (
    Determination,
    IssueOutcome,
    IssueType,
    IssuePrediction,
)
from llm_orchestrator.pipeline.issue_predictor import IssuePredictor

# Reuse the _fa() FactorAssertion fixture from test_determination_rules.py
from llm_orchestrator.tests.test_determination_rules import _fa


def _make_prediction(determination, outcome=IssueOutcome.TENANT_WINS, amount=None):
    """Return a minimal IssuePrediction with the given determination and outcome."""
    return IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        predicted_outcome=outcome,
        confidence=0.8,
        predicted_determination=determination,
        predicted_amount=amount,
    )


def _make_case_graph(factors=None):
    """Return a minimal case-graph stub with the given factor_assertions."""
    return types.SimpleNamespace(factor_assertions=factors or [_fa("vulnerability_known", boolean=False)])


def _run(prediction, monkeypatch, *, consistency="1", rules="0", tariff="0"):
    """Run _apply_determination_postrules with the given flag settings."""
    monkeypatch.setenv("STREAM_C_DET_OUTCOME_CONSISTENCY", consistency)
    monkeypatch.setenv("STREAM_C_DETERMINATION_RULES", rules)
    monkeypatch.setenv("STREAM_C_TARIFF_QUANTUM", tariff)
    predictor = IssuePredictor.__new__(IssuePredictor)
    case_graph = _make_case_graph()
    return predictor._apply_determination_postrules(prediction, case_graph)


# ---------------------------------------------------------------------------
# Test 1: reasonable_redress + landlord_wins → tenant_wins
# ---------------------------------------------------------------------------

def test_reasonable_redress_landlord_outcome_corrected_to_tenant(monkeypatch):
    """det=reasonable_redress + outcome=landlord_wins must be corrected to tenant_wins.

    Reasonable_redress means the Ombudsman orders the prior offer to be
    honoured — this is a resident-favourable outcome.
    """
    prediction = _make_prediction(
        Determination.REASONABLE_REDRESS,
        outcome=IssueOutcome.LANDLORD_WINS,
    )
    result = _run(prediction, monkeypatch)
    assert result.outcome is IssueOutcome.TENANT_WINS, (
        "reasonable_redress with landlord_wins outcome must be corrected to tenant_wins"
    )


# ---------------------------------------------------------------------------
# Test 2: no_maladministration + tenant_wins → landlord_wins
# ---------------------------------------------------------------------------

def test_no_maladministration_tenant_outcome_corrected_to_landlord(monkeypatch):
    """det=no_maladministration + outcome=tenant_wins must be corrected to landlord_wins."""
    prediction = _make_prediction(
        Determination.NO_MALADMINISTRATION,
        outcome=IssueOutcome.TENANT_WINS,
    )
    result = _run(prediction, monkeypatch)
    assert result.outcome is IssueOutcome.LANDLORD_WINS, (
        "no_maladministration with tenant_wins outcome must be corrected to landlord_wins"
    )


# ---------------------------------------------------------------------------
# Test 3: outside_jurisdiction → landlord_wins regardless of original outcome
# ---------------------------------------------------------------------------

def test_outside_jurisdiction_maps_to_landlord_wins(monkeypatch):
    """det=outside_jurisdiction must always produce landlord_wins outcome."""
    prediction = _make_prediction(
        Determination.OUTSIDE_JURISDICTION,
        outcome=IssueOutcome.TENANT_WINS,
    )
    result = _run(prediction, monkeypatch)
    assert result.outcome is IssueOutcome.LANDLORD_WINS, (
        "outside_jurisdiction must map to landlord_wins"
    )


# ---------------------------------------------------------------------------
# Test 4: flag=0 → outcome untouched even when inconsistent
# ---------------------------------------------------------------------------

def test_flag_off_leaves_outcome_untouched(monkeypatch):
    """With STREAM_C_DET_OUTCOME_CONSISTENCY=0, outcome is never overridden."""
    prediction = _make_prediction(
        Determination.REASONABLE_REDRESS,
        outcome=IssueOutcome.LANDLORD_WINS,  # intentionally inconsistent
    )
    result = _run(prediction, monkeypatch, consistency="0")
    assert result.outcome is IssueOutcome.LANDLORD_WINS, (
        "Consistency block must be a no-op when STREAM_C_DET_OUTCOME_CONSISTENCY=0"
    )


# ---------------------------------------------------------------------------
# Test 5: determination None → untouched (early-exit guard)
# ---------------------------------------------------------------------------

def test_none_determination_guard_skips_all_blocks(monkeypatch):
    """When predicted_determination is None the method returns early and does
    not touch the outcome (the shared factors/determination guard fires)."""
    monkeypatch.setenv("STREAM_C_DET_OUTCOME_CONSISTENCY", "1")
    monkeypatch.setenv("STREAM_C_DETERMINATION_RULES", "0")
    monkeypatch.setenv("STREAM_C_TARIFF_QUANTUM", "0")
    prediction = IssuePrediction(
        issue_type=IssueType.REPAIRS_DISREPAIR,
        predicted_outcome=IssueOutcome.LANDLORD_WINS,
        confidence=0.8,
        predicted_determination=None,
        predicted_amount=None,
    )
    predictor = IssuePredictor.__new__(IssuePredictor)
    # Even with factors present, None determination must trigger the early guard
    case_graph = _make_case_graph()
    result = predictor._apply_determination_postrules(prediction, case_graph)
    assert result.outcome is IssueOutcome.LANDLORD_WINS, (
        "None determination must cause early return; outcome must be untouched"
    )
