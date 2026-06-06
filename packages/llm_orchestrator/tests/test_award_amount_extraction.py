"""Tests for `_extract_award_amounts` (RQ2 grounded-award anchor, C1)."""
from llm_orchestrator.pipeline.issue_predictor import _extract_award_amounts


def test_simple_pound_amount():
    assert _extract_award_amounts("compensation of £500") == [500.0]


def test_thousands_separator_and_decimals():
    assert _extract_award_amounts("ordered to pay £1,200.50 to the resident") == [1200.5]


def test_pounds_word_form():
    assert _extract_award_amounts("an award of 1500 pounds was made") == [1500.0]


def test_multiple_amounts_order_preserved():
    assert _extract_award_amounts("£450 for distress and a further £75 in costs") == [450.0, 75.0]


def test_no_amount():
    assert _extract_award_amounts("no monetary remedy was ordered") == []


def test_bare_pound_sign_ignored():
    assert _extract_award_amounts("the £ symbol alone, and £0 nominal") == []


def test_dedupe_preserves_first():
    assert _extract_award_amounts("£500 ... and again £500") == [500.0]
