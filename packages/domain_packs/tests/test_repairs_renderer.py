"""Tests for housing.repairs_social.v1 renderer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import pytest

from domain_packs.housing.repairs_social.renderer import (
    _duration_bucket_label,
    _money_bucket_label,
)
from domain_packs.registry import get_domain_pack
from legal_core.graph.factor_assertion import (
    ExtractionMethod,
    FactorAssertion,
    FactorPolarity,
)
from legal_core.graph.factor_value import FactorValue, FactorValueType


@dataclass
class _FakeKG:
    """Minimal stand-in for KnowledgeGraph carrying factor_assertions."""
    factor_assertions: List[FactorAssertion]


def _make_fa(
    factor_id: str,
    value: FactorValue,
    *,
    confidence: float = 0.92,
    polarity: FactorPolarity = FactorPolarity.PRO_CLAIMANT,
    supported_by: list[str] | None = None,
    requires_human_review: bool = False,
    extraction_method: ExtractionMethod = ExtractionMethod.LLM_VERIFIED,
) -> FactorAssertion:
    return FactorAssertion(
        factor_assertion_id=f"fa_{factor_id}",
        factor_id=factor_id,
        domain_id="housing.repairs_social.v1",
        claim_head_id="claim_1",
        value=value,
        value_type=value.value_type,
        confidence=confidence,
        polarity=polarity,
        supported_by=supported_by or ["span_1"],
        requires_human_review=requires_human_review,
        extraction_method=extraction_method,
        extractor_version="test_extractor_v1",
        verifier_version="test_verifier_v1" if extraction_method == ExtractionMethod.LLM_VERIFIED else None,
    )


def test_renderer_returns_empty_when_no_factor_assertions():
    pack = get_domain_pack("housing.repairs_social.v1")
    kg = _FakeKG(factor_assertions=[])
    assert pack.render_factor_card(kg) == ""


def test_renderer_returns_empty_when_kg_none():
    pack = get_domain_pack("housing.repairs_social.v1")
    assert pack.render_factor_card(None) == ""


def test_renderer_renders_single_boolean_factor_with_evidence():
    pack = get_domain_pack("housing.repairs_social.v1")
    fa = _make_fa(
        "inspection_offered",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        confidence=0.92,
        supported_by=["span_1"],
    )
    kg = _FakeKG(factor_assertions=[fa])
    card = pack.render_factor_card(kg)
    assert "inspection_offered: True" in card
    assert "evidence: span_1" in card
    assert "confidence: 0.92" in card


def test_renderer_renders_duration_factor_with_bucket_label():
    """Duration factor (days) renders with bucket label drawn from
    retrieval_profile.bucket_definitions.duration."""
    pack = get_domain_pack("housing.repairs_social.v1")
    duration_factors = [
        f for f in pack.factors.factors if f.value_type == FactorValueType.DURATION
    ]
    assert duration_factors, "housing.repairs_social.v1 must have duration factors"
    fa = _make_fa(
        duration_factors[0].id,
        FactorValue(value_type=FactorValueType.DURATION, duration_days=45),
    )
    kg = _FakeKG(factor_assertions=[fa])
    card = pack.render_factor_card(kg)
    # 45 days lands in 30-90d bucket per [1, 7, 30, 90, 365] edges
    assert "45 days" in card
    assert "30-90d" in card


def test_renderer_renders_money_factor_with_pence_to_pounds():
    """Find any money-typed factor in the catalog and test it. If none, skip."""
    pack = get_domain_pack("housing.repairs_social.v1")
    money_factors = [f for f in pack.factors.factors if f.value_type == FactorValueType.MONEY]
    if not money_factors:
        pytest.skip("housing.repairs_social.v1 has no money-typed factors")
    fa = _make_fa(
        money_factors[0].id,
        FactorValue(
            value_type=FactorValueType.MONEY,
            money_minor_units=12345,
            money_currency="GBP",
        ),
    )
    kg = _FakeKG(factor_assertions=[fa])
    card = pack.render_factor_card(kg)
    assert "£123.45" in card


def test_renderer_renders_enum_factor():
    pack = get_domain_pack("housing.repairs_social.v1")
    enum_factors = [f for f in pack.factors.factors if f.value_type == FactorValueType.ENUM]
    if not enum_factors:
        pytest.skip("no enum factors in catalog")
    fe = enum_factors[0]
    enum_value = (fe.enum_values or ["unknown"])[0]
    fa = _make_fa(
        fe.id,
        FactorValue(value_type=FactorValueType.ENUM, enum=enum_value),
    )
    kg = _FakeKG(factor_assertions=[fa])
    card = pack.render_factor_card(kg)
    assert f"{fe.id}: {enum_value}" in card


def test_renderer_excludes_requires_human_review_factors_from_main_block():
    pack = get_domain_pack("housing.repairs_social.v1")
    # Pick any boolean factor for simplicity
    bool_factors = [f for f in pack.factors.factors if f.value_type == FactorValueType.BOOLEAN]
    if not bool_factors:
        pytest.skip("no boolean factors")
    main_fe = bool_factors[0]
    uncertain_fe = bool_factors[1] if len(bool_factors) > 1 else bool_factors[0]
    main_fa = _make_fa(
        main_fe.id,
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        requires_human_review=False,
    )
    uncertain_fa = _make_fa(
        uncertain_fe.id,
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
        requires_human_review=True,
    )
    kg = _FakeKG(factor_assertions=[main_fa, uncertain_fa])
    card = pack.render_factor_card(kg)
    assert "KEY FACTORS (factor-graph derived):" in card
    assert "Uncertain (excluded from gate):" in card
    main_idx = card.find("KEY FACTORS")
    uncertain_idx = card.find("Uncertain (excluded")
    assert main_idx < uncertain_idx, "main section must come before uncertain"


def test_renderer_omits_factors_not_in_pack_catalog(caplog):
    pack = get_domain_pack("housing.repairs_social.v1")
    fa = _make_fa(
        "this_factor_does_not_exist_in_catalog",
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    kg = _FakeKG(factor_assertions=[fa])
    with caplog.at_level(logging.WARNING):
        card = pack.render_factor_card(kg)
    assert card == ""  # only the unknown factor → empty
    assert any("factor_assertion_not_in_catalog" in m for m in caplog.messages)


def test_renderer_uses_pack_polarity_to_label():
    pack = get_domain_pack("housing.repairs_social.v1")
    # Find one pro_claimant factor and one pro_respondent factor (if any) in catalog
    pro_claimant = [f for f in pack.factors.factors if f.polarity == "pro_claimant"]
    pro_respondent = [f for f in pack.factors.factors if f.polarity == "pro_respondent"]

    if pro_claimant:
        bf = pro_claimant[0]
        if bf.value_type == FactorValueType.BOOLEAN:
            fa = _make_fa(bf.id, FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True))
            card = pack.render_factor_card(_FakeKG([fa]))
            assert "favours resident" in card

    if pro_respondent:
        bf = pro_respondent[0]
        if bf.value_type == FactorValueType.BOOLEAN:
            fa = _make_fa(bf.id, FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True))
            card = pack.render_factor_card(_FakeKG([fa]))
            assert "favours landlord" in card


def test_renderer_total_size_under_2000_chars_for_15_factor_case():
    """Construct a case with all 15 factors populated; rendered card must stay under 2000 chars."""
    pack = get_domain_pack("housing.repairs_social.v1")
    fas: list[FactorAssertion] = []
    for fe in pack.factors.factors:
        if fe.value_type == FactorValueType.BOOLEAN:
            v = FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True)
        elif fe.value_type == FactorValueType.ENUM:
            v = FactorValue(value_type=FactorValueType.ENUM, enum=(fe.enum_values or ["unknown"])[0])
        elif fe.value_type == FactorValueType.NUMBER:
            v = FactorValue(value_type=FactorValueType.NUMBER, number=42.0)
        elif fe.value_type == FactorValueType.MONEY:
            v = FactorValue(value_type=FactorValueType.MONEY, money_minor_units=12345, money_currency="GBP")
        elif fe.value_type == FactorValueType.DURATION:
            v = FactorValue(value_type=FactorValueType.DURATION, duration_days=45)
        elif fe.value_type == FactorValueType.DATE:
            from datetime import date
            v = FactorValue(value_type=FactorValueType.DATE, date=date(2026, 1, 1))
        else:
            continue
        fas.append(_make_fa(fe.id, v))

    card = pack.render_factor_card(_FakeKG(fas))
    assert len(card) < 2000, f"card too long: {len(card)}"


def test_renderer_emits_no_unresolved_format_placeholders():
    """The output must not contain literal `{` or `}` that would crash .format() downstream.

    Either it has no braces, or it has only doubled braces ({{ and }}).
    """
    pack = get_domain_pack("housing.repairs_social.v1")
    bool_factors = [f for f in pack.factors.factors if f.value_type == FactorValueType.BOOLEAN]
    if not bool_factors:
        pytest.skip("no boolean factors")
    fa = _make_fa(
        bool_factors[0].id,
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    card = pack.render_factor_card(_FakeKG([fa]))
    # Try to .format() it as if it were a prompt fragment with no kwargs:
    try:
        card.format()
    except (IndexError, KeyError, ValueError) as exc:
        pytest.fail(f"renderer output crashed .format(): {exc!r}")


def test_kill_switch_returns_empty_card(monkeypatch):
    pack = get_domain_pack("housing.repairs_social.v1")
    bool_factors = [f for f in pack.factors.factors if f.value_type == FactorValueType.BOOLEAN]
    if not bool_factors:
        pytest.skip("no boolean factors")
    fa = _make_fa(
        bool_factors[0].id,
        FactorValue(value_type=FactorValueType.BOOLEAN, boolean=True),
    )
    monkeypatch.setenv("STREAM_C_PR4_REPAIRS", "0")
    assert pack.render_factor_card(_FakeKG([fa])) == ""


@pytest.mark.parametrize(
    "pence,expected",
    [
        (0, "£0-£100"),
        (5000, "£0-£100"),       # 50p < £100
        (10000, "£100-£500"),    # exactly £100 → 100-500 bucket
        (49999, "£100-£500"),    # just under £500
        (50000, "£500-£2000"),   # exactly £500
        (199999, "£500-£2000"),
        (200000, "£2000-£10000"),
        (999999, "£2000-£10000"),
        (1000000, ">£10000"),    # exactly £10000 (the last edge) → > bucket
        (5000000, ">£10000"),    # well above
    ],
)
def test_money_bucket_label_edges(pence: int, expected: str):
    edges = [0, 10000, 50000, 200000, 1000000]
    assert _money_bucket_label(pence, edges) == expected


@pytest.mark.parametrize(
    "days,expected",
    [
        (0, "<1d"),               # below the first edge
        (1, "1-7d"),
        (6, "1-7d"),
        (7, "7-30d"),
        (29, "7-30d"),
        (30, "30-90d"),
        (89, "30-90d"),
        (90, "90-365d"),
        (364, "90-365d"),
        (365, ">365d"),           # exactly the last edge → >
        (1000, ">365d"),
    ],
)
def test_duration_bucket_label_edges(days: int, expected: str):
    edges = [1, 7, 30, 90, 365]
    assert _duration_bucket_label(days, edges) == expected
