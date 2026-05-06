"""Unit tests for GraphQualityScore."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_core.graph.graph_quality import GraphQualityScore


def test_minimum_valid_score():
    s = GraphQualityScore(
        score=0.0,
        evidence_backed_factor_count=0,
        dated_event_count=0,
        issue_count=0,
        outcome_or_remedy_candidate_count=0,
        unsupported_factor_rate=0.0,
        source_span_coverage=0.0,
        contradiction_count=0,
        usable_for_prediction=False,
        failure_reasons=["no factors extracted"],
    )
    assert s.usable_for_prediction is False


def test_score_in_unit_interval():
    for bad in (-0.01, 1.01):
        with pytest.raises(ValidationError):
            GraphQualityScore(
                score=bad,
                evidence_backed_factor_count=0,
                dated_event_count=0,
                issue_count=0,
                outcome_or_remedy_candidate_count=0,
                unsupported_factor_rate=0.0,
                source_span_coverage=0.0,
                contradiction_count=0,
                usable_for_prediction=False,
                failure_reasons=[],
            )


def test_rate_fields_in_unit_interval():
    with pytest.raises(ValidationError):
        GraphQualityScore(
            score=0.5,
            evidence_backed_factor_count=0,
            dated_event_count=0,
            issue_count=0,
            outcome_or_remedy_candidate_count=0,
            unsupported_factor_rate=1.5,
            source_span_coverage=0.0,
            contradiction_count=0,
            usable_for_prediction=False,
            failure_reasons=[],
        )

    with pytest.raises(ValidationError):
        GraphQualityScore(
            score=0.5,
            evidence_backed_factor_count=0,
            dated_event_count=0,
            issue_count=0,
            outcome_or_remedy_candidate_count=0,
            unsupported_factor_rate=0.0,
            source_span_coverage=-0.1,
            contradiction_count=0,
            usable_for_prediction=False,
            failure_reasons=[],
        )


def test_count_fields_non_negative():
    with pytest.raises(ValidationError):
        GraphQualityScore(
            score=0.5,
            evidence_backed_factor_count=-1,
            dated_event_count=0,
            issue_count=0,
            outcome_or_remedy_candidate_count=0,
            unsupported_factor_rate=0.0,
            source_span_coverage=0.0,
            contradiction_count=0,
            usable_for_prediction=False,
            failure_reasons=[],
        )


def test_failed_score_must_have_at_least_one_failure_reason():
    with pytest.raises(ValidationError):
        GraphQualityScore(
            score=0.0,
            evidence_backed_factor_count=0,
            dated_event_count=0,
            issue_count=0,
            outcome_or_remedy_candidate_count=0,
            unsupported_factor_rate=0.0,
            source_span_coverage=0.0,
            contradiction_count=0,
            usable_for_prediction=False,
            failure_reasons=[],
        )


def test_usable_score_must_have_no_failure_reasons():
    with pytest.raises(ValidationError):
        GraphQualityScore(
            score=0.9,
            evidence_backed_factor_count=8,
            dated_event_count=3,
            issue_count=2,
            outcome_or_remedy_candidate_count=2,
            unsupported_factor_rate=0.0,
            source_span_coverage=1.0,
            contradiction_count=0,
            usable_for_prediction=True,
            failure_reasons=["should be empty"],
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        GraphQualityScore(
            score=0.0,
            evidence_backed_factor_count=0,
            dated_event_count=0,
            issue_count=0,
            outcome_or_remedy_candidate_count=0,
            unsupported_factor_rate=0.0,
            source_span_coverage=0.0,
            contradiction_count=0,
            usable_for_prediction=False,
            failure_reasons=["x"],
            unexpected="oops",
        )


def test_frozen():
    s = GraphQualityScore(
        score=0.0,
        evidence_backed_factor_count=0,
        dated_event_count=0,
        issue_count=0,
        outcome_or_remedy_candidate_count=0,
        unsupported_factor_rate=0.0,
        source_span_coverage=0.0,
        contradiction_count=0,
        usable_for_prediction=False,
        failure_reasons=["x"],
    )
    with pytest.raises(ValidationError):
        s.usable_for_prediction = True
