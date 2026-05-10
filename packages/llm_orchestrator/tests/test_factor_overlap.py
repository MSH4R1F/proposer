"""Tests for the bucketed similarity helpers used by the factor-overlap
comparator pass (Task 5.2).

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §9.2.1
"""

from __future__ import annotations

from datetime import date

import pytest

from domain_packs.registry import get_domain_pack
from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType

from llm_orchestrator.pipeline._factor_overlap import (
    boolean_similarity,
    date_similarity,
    duration_similarity,
    enum_similarity,
    factor_overlap,
    money_similarity,
)


# ---------------------------------------------------------------------------
# Helpers — minimal FactorAssertion construction for dispatch tests
# ---------------------------------------------------------------------------


def _make_fa(
    factor_id: str,
    value: FactorValue,
    *,
    polarity: FactorPolarity = FactorPolarity.PRO_CLAIMANT,
) -> FactorAssertion:
    return FactorAssertion(
        factor_assertion_id=f"fa_{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        value=value,
        value_type=value.value_type,
        confidence=0.9,
        polarity=polarity,
        supported_by=["span_1"],
        extraction_method=ExtractionMethod.LLM_VERIFIED,
        extractor_version="test_extractor_v1",
        verifier_version="test_verifier_v1",
    )


# ---------------------------------------------------------------------------
# money_similarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (5000, 5000, 1.0),        # both in bucket 0
        (5000, 9999, 1.0),        # both in bucket 0
        (5000, 10000, 0.5),       # adjacent: bucket 0 -> bucket 1
        (5000, 50000, 0.0),       # 2 buckets apart
        (10000, 49999, 1.0),      # both in bucket 1
        (49999, 50000, 0.5),      # adjacent
        (1000000, 5000000, 1.0),  # both in last bucket (open-ended top)
        (0, 0, 1.0),
        (0, 10000, 0.5),
        (1000000, 200000, 0.5),   # adjacent at top boundary
        (0, 200000, 0.0),         # 3 buckets apart
    ],
)
def test_money_similarity(a, b, expected):
    edges = [0, 10000, 50000, 200000, 1000000]
    assert money_similarity(a, b, edges) == expected


def test_money_similarity_is_symmetric():
    edges = [0, 10000, 50000, 200000, 1000000]
    assert money_similarity(5000, 50000, edges) == money_similarity(50000, 5000, edges)


# ---------------------------------------------------------------------------
# duration_similarity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (3, 5, 1.0),         # both in bucket 0 ([1, 7))
        (5, 7, 0.5),         # adjacent
        (5, 30, 0.0),        # 2 apart
        (1000, 2000, 1.0),   # both in last bucket (>= 365)
        (1, 1, 1.0),         # exactly on edge[0]
        (90, 365, 0.5),      # adjacent at top
        (7, 30, 0.5),        # adjacent: [7,30) and [30,90)
    ],
)
def test_duration_similarity(a, b, expected):
    edges = [1, 7, 30, 90, 365]
    assert duration_similarity(a, b, edges) == expected


# ---------------------------------------------------------------------------
# date_similarity
# ---------------------------------------------------------------------------


def test_date_same_month_returns_same_month_score():
    sim = date_similarity(
        date(2026, 1, 15), date(2026, 1, 28),
        same_year=0.5, same_month=1.0, other=0.0,
    )
    assert sim == 1.0


def test_date_same_year_different_month_returns_same_year_score():
    sim = date_similarity(
        date(2026, 1, 15), date(2026, 6, 15),
        same_year=0.5, same_month=1.0, other=0.0,
    )
    assert sim == 0.5


def test_date_different_year_returns_other_score():
    sim = date_similarity(
        date(2026, 1, 15), date(2025, 1, 15),
        same_year=0.5, same_month=1.0, other=0.0,
    )
    assert sim == 0.0


def test_date_identical_returns_same_month_score():
    sim = date_similarity(
        date(2026, 5, 7), date(2026, 5, 7),
        same_year=0.5, same_month=1.0, other=0.0,
    )
    assert sim == 1.0


# ---------------------------------------------------------------------------
# boolean_similarity
# ---------------------------------------------------------------------------


def test_boolean_similarity_both_true():
    assert boolean_similarity(True, True) == 1.0


def test_boolean_similarity_both_false():
    assert boolean_similarity(False, False) == 1.0


def test_boolean_similarity_mismatch_true_false():
    assert boolean_similarity(True, False) == 0.0


def test_boolean_similarity_mismatch_false_true():
    assert boolean_similarity(False, True) == 0.0


# ---------------------------------------------------------------------------
# enum_similarity
# ---------------------------------------------------------------------------


def test_enum_similarity_equal():
    assert enum_similarity("severe", "severe") == 1.0


def test_enum_similarity_unequal():
    assert enum_similarity("severe", "moderate") == 0.0


def test_enum_similarity_case_sensitive():
    # Spec §9.2.1: equality only, no semantic similarity.
    assert enum_similarity("Severe", "severe") == 0.0


# ---------------------------------------------------------------------------
# factor_overlap dispatch
# ---------------------------------------------------------------------------


def test_factor_overlap_different_value_types_returns_zero():
    """If a is BOOLEAN and b is ENUM, return 0.0 (no cross-type comparison)."""
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.ENUM, enum="severe"),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 0.0


def test_factor_overlap_boolean_dispatch_match():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 1.0


def test_factor_overlap_boolean_dispatch_mismatch():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=False),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 0.0


def test_factor_overlap_enum_dispatch():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.ENUM, enum="severe"),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.ENUM, enum="severe"),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 1.0


def test_factor_overlap_money_dispatch_same_bucket():
    """Two money factors in same bucket -> 1.0 with the real housing pack edges."""
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=5000,
            money_currency="GBP",
        ),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=9999,
            money_currency="GBP",
        ),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 1.0


def test_factor_overlap_money_dispatch_adjacent_bucket():
    """Two money factors in adjacent buckets -> 0.5."""
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=5000,
            money_currency="GBP",
        ),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=10000,
            money_currency="GBP",
        ),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 0.5


def test_factor_overlap_duration_dispatch_same_bucket():
    """Two duration factors in same bucket -> 1.0."""
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.DURATION, duration_days=3),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.DURATION, duration_days=5),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 1.0


def test_factor_overlap_duration_dispatch_distant():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.DURATION, duration_days=5),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.DURATION, duration_days=200),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 0.0


def test_factor_overlap_date_dispatch_same_month():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.DATE, date=date(2026, 1, 5)),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.DATE, date=date(2026, 1, 28)),
    )
    # Housing pack has same_month_score=1.0
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 1.0


def test_factor_overlap_date_dispatch_different_year():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.DATE, date=date(2026, 1, 5)),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.DATE, date=date(2024, 1, 5)),
    )
    # Housing pack has other_score=0.0
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 0.0


def test_factor_overlap_number_dispatch_equal():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.NUMBER, number=42.0),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.NUMBER, number=42.0),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 1.0


def test_factor_overlap_number_dispatch_unequal():
    pack = get_domain_pack("housing.repairs_social.v1")
    a = _make_fa(
        "factor_a",
        FactorValue(value_type=FactorValueType.NUMBER, number=42.0),
    )
    b = _make_fa(
        "factor_b",
        FactorValue(value_type=FactorValueType.NUMBER, number=43.0),
    )
    assert factor_overlap(a, b, pack.retrieval_profile.bucket_definitions) == 0.0
