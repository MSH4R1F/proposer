"""Tests for `_extract_order_amounts` — recover the Ombudsman ordered TOTAL,
not incidental £ figures (RQ2 grounding fix)."""
from llm_orchestrator.pipeline.issue_predictor import _extract_order_amounts


def test_total_not_breakdown():
    # The grand total, not the sub-components it is "made up of".
    t = "The landlord must pay the resident £1000 made up as follows: £500 for distress, £300 for repairs delay, £200 for complaint handling."
    assert _extract_order_amounts(t) == [1000.0]


def test_ocr_split_total():
    # OCR one-token-per-line corruption: the total must survive.
    t = "The landlord must pay the resident £\n1\n07\n5\nmade up as follows:\n£\n700\n£\n150"
    assert _extract_order_amounts(t) == [1075.0]


def test_ocr_spaced_digits():
    t = "must pay the resident £ 1, 01 0 in total"
    assert _extract_order_amounts(t) == [1010.0]


def test_order_context_amount_when_no_total_phrase():
    t = "The Ombudsman ordered the landlord to pay compensation of £800 in recognition of the failures."
    assert _extract_order_amounts(t) == [800.0]


def test_incidental_figures_filtered():
    t = "The monthly rent was £450 and arrears of £1,200 accrued. The landlord had offered compensation of £900."
    assert _extract_order_amounts(t) == []


def test_high_value_total():
    t = "the landlord must pay the resident £3,818 in total compensation"
    assert _extract_order_amounts(t) == [3818.0]


def test_empty():
    assert _extract_order_amounts("no money ordered here") == []
