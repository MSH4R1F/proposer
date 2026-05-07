"""Unit tests for FactorAssertion."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType


def _make_value() -> FactorValue:
    return FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True)


def test_minimum_valid_assertion():
    fa = FactorAssertion(
        factor_assertion_id="fa_1",
        factor_id="inspection_offered",
        domain_id="housing.repairs_social.v1",
        claim_head_id="repairs_damp_mould",
        value=_make_value(),
        value_type=FactorValueType.BOOLEAN,
        confidence=0.9,
        polarity=FactorPolarity.PRO_RESPONDENT,
        expected_effects=[],
        maps_to_outcomes=[],
        maps_to_remedies=[],
        supported_by=["span_1"],
        refuted_by=[],
        linked_events=[],
        linked_issues=[],
        source_span_refs=["span_1"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="extract_v1",
        verifier_version="verify_v1",
    )
    assert fa.factor_id == "inspection_offered"
    assert fa.requires_human_review is False


def test_value_type_must_match_value_payload():
    bool_value = FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True)
    with pytest.raises(ValidationError):
        FactorAssertion(
            factor_assertion_id="fa_1",
            factor_id="x",
            domain_id="d",
            claim_head_id="ch",
            value=bool_value,
            value_type=FactorValueType.NUMBER,
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
            extraction_method=ExtractionMethod.DETERMINISTIC,
            extractor_version="v",
        )


def test_confidence_in_unit_interval():
    for bad in (-0.1, 1.1, 2.0):
        with pytest.raises(ValidationError):
            FactorAssertion(
                factor_assertion_id="fa_1",
                factor_id="x",
                domain_id="d",
                claim_head_id="ch",
                value=_make_value(),
                value_type=FactorValueType.BOOLEAN,
                confidence=bad,
                polarity=FactorPolarity.NEUTRAL,
                expected_effects=[],
                maps_to_outcomes=[],
                maps_to_remedies=[],
                supported_by=["s"],
                refuted_by=[],
                linked_events=[],
                linked_issues=[],
                source_span_refs=["s"],
                extraction_method=ExtractionMethod.DETERMINISTIC,
                extractor_version="v",
            )


def test_non_deterministic_requires_evidence_span():
    with pytest.raises(ValidationError):
        FactorAssertion(
            factor_assertion_id="fa_1",
            factor_id="x",
            domain_id="d",
            claim_head_id="ch",
            value=_make_value(),
            value_type=FactorValueType.BOOLEAN,
            confidence=0.5,
            polarity=FactorPolarity.NEUTRAL,
            expected_effects=[],
            maps_to_outcomes=[],
            maps_to_remedies=[],
            supported_by=[],
            refuted_by=[],
            linked_events=[],
            linked_issues=[],
            source_span_refs=[],
            extraction_method=ExtractionMethod.LLM_VERIFIED,
            extractor_version="v",
            verifier_version="vv",
        )


def test_deterministic_may_skip_evidence_span():
    fa = FactorAssertion(
        factor_assertion_id="fa_1",
        factor_id="claim_in_time",
        domain_id="d",
        claim_head_id="ch",
        value=_make_value(),
        value_type=FactorValueType.BOOLEAN,
        confidence=1.0,
        polarity=FactorPolarity.NEUTRAL,
        expected_effects=[],
        maps_to_outcomes=[],
        maps_to_remedies=[],
        supported_by=[],
        refuted_by=[],
        linked_events=[],
        linked_issues=[],
        source_span_refs=[],
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extractor_version="calc_v1",
    )
    assert fa.factor_id == "claim_in_time"


def test_llm_verified_requires_verifier_version():
    with pytest.raises(ValidationError):
        FactorAssertion(
            factor_assertion_id="fa_1",
            factor_id="x",
            domain_id="d",
            claim_head_id="ch",
            value=_make_value(),
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
            extraction_method=ExtractionMethod.LLM_VERIFIED,
            extractor_version="v",
            verifier_version=None,
        )


def test_polarity_is_abstract_only():
    valid = {p.value for p in FactorPolarity}
    assert valid == {"pro_claimant", "pro_respondent", "neutral"}


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        FactorAssertion(
            factor_assertion_id="fa_1",
            factor_id="x",
            domain_id="d",
            claim_head_id="ch",
            value=_make_value(),
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
            extraction_method=ExtractionMethod.DETERMINISTIC,
            extractor_version="v",
            unexpected="oops",
        )


def test_frozen_after_construction():
    fa = FactorAssertion(
        factor_assertion_id="fa_1",
        factor_id="x",
        domain_id="d",
        claim_head_id="ch",
        value=_make_value(),
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
        extraction_method=ExtractionMethod.DETERMINISTIC,
        extractor_version="v",
    )
    with pytest.raises(ValidationError):
        fa.confidence = 0.9
