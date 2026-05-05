"""Tests for the deterministic GBP-amount extractor.

Module under test:
``packages/llm_orchestrator/pipeline/comparator_extractor.py``.

The patterns here mirror real Ombudsman order-paragraph wording. When
adding new fixtures, prefer copying real (de-identified) phrasing over
inventing synthetic strings.
"""

from __future__ import annotations

import pytest

from llm_orchestrator.pipeline.comparator_extractor import (
    CONTEXT_CHARS,
    ExtractedAmount,
    extract_pound_amounts,
)


def _amounts(text: str) -> list[float]:
    return [
        a.amount_gbp
        for a in extract_pound_amounts(chunk_id="t", text=text)
    ]


class TestBasicAmounts:
    def test_simple_pound_amount(self):
        assert _amounts("The landlord shall pay £700 in compensation.") == [700.0]

    def test_thousands_separator(self):
        assert _amounts("Compensation of £1,250 ordered.") == [1250.0]

    def test_no_separator(self):
        assert _amounts("Compensation of £1250 ordered.") == [1250.0]

    def test_decimal_amount(self):
        assert _amounts("The landlord must pay £1,250.50.") == [1250.5]

    def test_two_decimal_places(self):
        assert _amounts("Refund of £42.99 issued.") == [42.99]

    def test_gbp_prefix(self):
        # Less common in Ombudsman text but verifying the regex covers it.
        assert _amounts("Award of GBP 1500 made.") == [1500.0]

    def test_gbp_prefix_no_space(self):
        assert _amounts("Award of GBP1500 made.") == [1500.0]


class TestMultipleAmounts:
    def test_two_amounts_in_order(self):
        text = (
            "The landlord shall pay £500 for delay and a further £200 for "
            "complaint-handling failure."
        )
        assert _amounts(text) == [500.0, 200.0]

    def test_three_amounts(self):
        text = "Order: £100 plus £50 plus £25 — total to be calculated."
        assert _amounts(text) == [100.0, 50.0, 25.0]

    def test_duplicates_preserved(self):
        # Caller decides whether to dedupe; the function just reports.
        text = "Each of the two complaints attracts £300 (£300 each)."
        assert _amounts(text) == [300.0, 300.0]


class TestExclusions:
    def test_zero_amount_excluded(self):
        assert _amounts("No compensation: £0.") == []

    def test_huge_amount_excluded(self):
        # Above the 20000 sanity cap. Realistic case: a budget figure
        # quoted from policy, not a compensation order.
        assert _amounts("Service charge budget £25,000 in 2023.") == []

    def test_unit_million_excluded(self):
        # "£500m" is a million-pound quantity, never a compensation order.
        assert _amounts("The £500m programme is unrelated.") == []

    def test_unit_thousand_excluded(self):
        assert _amounts("Roughly £2k of works pending.") == []

    def test_no_currency_marker(self):
        # Bare numbers (years, paragraph numbers, dates) must NEVER match.
        assert _amounts("In 2023 the resident reported it on day 700.") == []

    def test_negative_sign_treated_as_punctuation(self):
        # We don't want to match "-£500" as a negative amount; the regex
        # captures 500 (positive) which is fine — the leading hyphen is
        # outside our group. We assert the magnitude is captured.
        assert _amounts("Refund of -£500 was reversed.") == [500.0]


class TestContextField:
    def test_surrounding_sentence_included(self):
        text = (
            "The Ombudsman finds maladministration. The landlord shall pay "
            "£700 for the delay in completing repairs. This figure reflects "
            "the time taken and the impact on the resident."
        )
        results = extract_pound_amounts(chunk_id="c1", text=text)
        assert len(results) == 1
        assert results[0].amount_gbp == 700.0
        # The surrounding sentence should be a window around the match.
        assert "£700" in results[0].surrounding_sentence
        assert len(results[0].surrounding_sentence) <= CONTEXT_CHARS + 4
        # Order paragraph language should be present.
        assert "landlord shall pay" in results[0].surrounding_sentence

    def test_surrounding_sentence_truncated_at_boundaries(self):
        # Match near start of string — left side should be the start, not
        # negative slice.
        text = "£900 ordered for the delay."
        results = extract_pound_amounts(chunk_id="c1", text=text)
        assert results[0].surrounding_sentence.startswith("£900")

    def test_paragraph_id_passed_through(self):
        results = extract_pound_amounts(
            chunk_id="ho_202412345#para_47",
            text="£550 ordered.",
            paragraph_id="para_47",
        )
        assert results[0].paragraph_id == "para_47"
        assert results[0].chunk_id == "ho_202412345#para_47"

    def test_raw_match_preserved(self):
        results = extract_pound_amounts(
            chunk_id="c1", text="Compensation of £1,250 ordered."
        )
        assert results[0].raw_match == "£1,250"


class TestEmptyAndNoMatch:
    def test_empty_text(self):
        assert extract_pound_amounts(chunk_id="c1", text="") == []

    def test_no_matches(self):
        assert (
            extract_pound_amounts(
                chunk_id="c1",
                text="The landlord acknowledged the failure but offered no compensation.",
            )
            == []
        )

    def test_only_unit_qualified(self):
        # Every match is excluded; result is empty.
        assert _amounts("£500m budget; £2k overrun; £1bn portfolio.") == []


class TestRealWorldShape:
    """Sanity-check phrasing close to actual Ombudsman determinations."""

    def test_order_paragraph_compensation(self):
        text = (
            "Within four weeks of the date of this report, the landlord is "
            "ordered to pay the resident £950, comprised of £600 for the "
            "delay in completing the repairs and £350 for the failures in "
            "complaint handling."
        )
        result = [a.amount_gbp for a in extract_pound_amounts(chunk_id="c1", text=text)]
        assert result == [950.0, 600.0, 350.0]

    def test_multi_complaint_order(self):
        text = (
            "Compensation of £1,500 in respect of complaint 202412345, plus "
            "£750 in respect of complaint 202412346."
        )
        result = [a.amount_gbp for a in extract_pound_amounts(chunk_id="c1", text=text)]
        assert result == [1500.0, 750.0]

    def test_remedies_within_band(self):
        text = (
            "Having considered the Ombudsman's remedies guidance, an award "
            "of £350 falls within the band for service failure with no "
            "permanent impact (£100 to £600)."
        )
        result = [a.amount_gbp for a in extract_pound_amounts(chunk_id="c1", text=text)]
        # All three figures are real GBP amounts — caller decides which is
        # the "order" vs guidance figure.
        assert result == [350.0, 100.0, 600.0]


class TestExtractedAmountFrozen:
    """ExtractedAmount must be immutable so caller-side mutation cannot
    poison shared state in the agent loop."""

    def test_cannot_mutate(self):
        a = ExtractedAmount(
            chunk_id="c1",
            paragraph_id=None,
            amount_gbp=100.0,
            surrounding_sentence="...",
            raw_match="£100",
        )
        with pytest.raises(Exception):
            a.amount_gbp = 200.0  # type: ignore[misc]
