"""Round-trip JSON serialization for legal_core models."""

from __future__ import annotations

import json
from datetime import date

from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType
from legal_core.graph.graph_quality import GraphQualityScore


def test_factor_value_json_round_trip_all_types():
    cases = [
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        FactorValue(value_type=FactorValueType.ENUM, enum="conduct"),
        FactorValue(value_type=FactorValueType.NUMBER, number=42.0),
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=12345,
            money_currency="GBP",
        ),
        FactorValue(value_type=FactorValueType.DATE, date=date(2026, 5, 6)),
        FactorValue(value_type=FactorValueType.DURATION, duration_days=42),
    ]
    for original in cases:
        payload = original.model_dump_json()
        restored = FactorValue.model_validate_json(payload)
        assert restored == original


def test_factor_assertion_json_round_trip():
    original = FactorAssertion(
        factor_assertion_id="fa_1",
        factor_id="inspection_offered",
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.92,
        polarity=FactorPolarity.PRO_RESPONDENT,
        expected_effects=["supports_no_maladministration"],
        maps_to_outcomes=["no_maladministration"],
        maps_to_remedies=[],
        supported_by=["span_14"],
        refuted_by=[],
        linked_events=["event_inspection_2021_06_14"],
        linked_issues=["issue_damp_mould"],
        source_span_refs=["span_14"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="extract_v1",
        verifier_version="verify_v1",
        requires_human_review=False,
    )
    payload = original.model_dump_json()
    restored = FactorAssertion.model_validate_json(payload)
    assert restored == original


def test_graph_quality_score_json_round_trip():
    original = GraphQualityScore(
        score=0.76,
        evidence_backed_factor_count=8,
        dated_event_count=3,
        issue_count=2,
        outcome_or_remedy_candidate_count=2,
        unsupported_factor_rate=0.10,
        source_span_coverage=0.92,
        contradiction_count=0,
        usable_for_prediction=True,
        failure_reasons=[],
    )
    payload = original.model_dump_json()
    restored = GraphQualityScore.model_validate_json(payload)
    assert restored == original


def test_factor_assertion_in_collection_json_round_trip():
    fa = FactorAssertion(
        factor_assertion_id="fa_1",
        factor_id="x",
        domain_id="d",
        claim_head_id="ch",
        value=FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.5,
        polarity=FactorPolarity.NEUTRAL,
        expected_effects=[],
        maps_to_outcomes=[],
        maps_to_remedies=[],
        supported_by=["s"],
        refuted_by=[],
        linked_events=[],
        linked_issues=[],
        source_span_refs=["s"],
        extraction_method=ExtractionMethod.LLM_EXTRACTED,
        extractor_version="v",
    )
    serialized = [json.loads(fa.model_dump_json()), json.loads(fa.model_dump_json())]
    restored = [FactorAssertion.model_validate(item) for item in serialized]
    assert restored[0] == fa
    assert restored[1] == fa
