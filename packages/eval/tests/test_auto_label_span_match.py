import pytest

from eval.auto_label.span_match import (
    MatchResult,
    MatchStrategy,
    match_quote_in_span,
)


PAGE_TEXT = (
    "1. The tribunal heard evidence on 12 March 2024.\n"
    "2. The respondent argued the deposit was protected within 30 days.\n"
    "3. We accept the applicant's evidence on the timing of the protection.\n"
    "4. Section 213 of the Housing Act 2004 applies."
)


class TestMatchQuoteInSpan:
    def test_exact_canonical_match(self) -> None:
        # text_span covers paragraph 2 in PAGE_TEXT.
        start = PAGE_TEXT.index("The respondent")
        end = PAGE_TEXT.index("days.") + len("days.")
        result = match_quote_in_span(
            quote="The respondent argued the deposit was protected within 30 days.",
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
        )
        assert result.matched is True
        assert result.strategy == MatchStrategy.CANONICAL_EXACT
        assert result.edit_distance == 0

    def test_canonical_normalisation_match(self) -> None:
        # OCR drift: ligature for "fi", curly quote, doubled whitespace.
        start = PAGE_TEXT.index("Section")
        end = len(PAGE_TEXT)
        result = match_quote_in_span(
            quote="“Section 213 of the Housing Act 2004 applies.”",
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
        )
        # Canonicalise both sides and re-check exact membership.
        assert result.matched is True
        assert result.strategy == MatchStrategy.CANONICAL_EXACT

    def test_bounded_edit_distance_inside_window(self) -> None:
        # Quote has a single OCR substitution ("0" -> "O"), span window is
        # large enough that fuzzy match within budget succeeds.
        start = PAGE_TEXT.index("Section")
        end = len(PAGE_TEXT)
        result = match_quote_in_span(
            quote="Section 213 of the Housing Act 2OO4 applies.",
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
            max_edit_distance=3,
        )
        assert result.matched is True
        assert result.strategy == MatchStrategy.BOUNDED_FUZZY
        assert 0 < result.edit_distance <= 3

    def test_outside_span_window_does_not_match(self) -> None:
        # Quote exists in the page, but caller pointed at a span that does
        # NOT contain it. The matcher must REFUSE — no whole-document
        # fallback (this is exactly the prompt-injection hardening rule).
        para1_start = 0
        para1_end = PAGE_TEXT.index("\n2.")
        result = match_quote_in_span(
            quote="Section 213 of the Housing Act 2004 applies.",
            page_text=PAGE_TEXT,
            char_start=para1_start,
            char_end=para1_end,
        )
        assert result.matched is False
        assert result.strategy == MatchStrategy.NO_MATCH

    def test_edit_distance_above_budget_rejects(self) -> None:
        start = PAGE_TEXT.index("Section")
        end = len(PAGE_TEXT)
        result = match_quote_in_span(
            quote="Section 999 of the Housing Act 1066 was repealed.",  # very different
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
            max_edit_distance=3,
        )
        assert result.matched is False

    def test_empty_quote_rejected(self) -> None:
        with pytest.raises(ValueError):
            match_quote_in_span(quote="", page_text=PAGE_TEXT, char_start=0, char_end=10)

    def test_invalid_span_rejected(self) -> None:
        with pytest.raises(ValueError):
            match_quote_in_span(
                quote="anything",
                page_text=PAGE_TEXT,
                char_start=10,
                char_end=5,
            )
