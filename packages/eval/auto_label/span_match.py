"""Bounded-window quote/span matcher.

The auto-grounder rejects any LLM-emitted quote that does not appear
inside its declared ``(page, paragraph, text_span)`` window, even if the
text exists elsewhere in the PDF. This is the prompt-injection hardening
rule from the sparring plan §3: no whole-document fuzzy fallback.

Two strategies are accepted:

* ``CANONICAL_EXACT`` — after canonicalisation, the quote is a substring
  of the canonicalised span window. Always preferred.
* ``BOUNDED_FUZZY`` — Levenshtein distance to the best-scoring substring
  of the canonicalised span window is <= ``max_edit_distance``. Used only
  to recover from genuine OCR drift inside the claimed window.

Anything else is ``NO_MATCH``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .canonicalize import canonicalize_text


class MatchStrategy(str, Enum):
    CANONICAL_EXACT = "canonical_exact"
    BOUNDED_FUZZY = "bounded_fuzzy"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    strategy: MatchStrategy
    edit_distance: int  # 0 for exact; -1 for NO_MATCH.


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Standard DP, O(len(a)*len(b)) — fine for sentence-length spans.
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _best_window_distance(needle: str, haystack: str, budget: int) -> int:
    """Return the minimum Levenshtein distance between ``needle`` and any
    contiguous substring of ``haystack`` whose length is within
    ``[len(needle) - budget, len(needle) + budget]``. Returns ``budget + 1``
    if no candidate window beats the budget — callers treat that as
    no-match.
    """
    n = len(needle)
    h = len(haystack)
    if n == 0 or h == 0:
        return budget + 1

    best = budget + 1
    min_w = max(1, n - budget)
    max_w = min(h, n + budget)
    for w in range(min_w, max_w + 1):
        for i in range(0, h - w + 1):
            d = _levenshtein(needle, haystack[i : i + w])
            if d < best:
                best = d
                if best == 0:
                    return 0
    return best


def match_quote_in_span(
    *,
    quote: str,
    page_text: str,
    char_start: int,
    char_end: int,
    max_edit_distance: int = 0,
) -> MatchResult:
    """Determine whether ``quote`` is grounded in ``page_text[char_start:char_end]``.

    Args:
        quote: The string the LLM claims to be quoting.
        page_text: The full canonicalised-or-raw page text the labeler saw.
        char_start, char_end: The labeler's declared span window
            (half-open). Searching is restricted to this window.
        max_edit_distance: 0 disables fuzzy matching. >0 allows OCR-drift
            recovery inside the window only.

    Raises:
        ValueError: empty quote, or invalid (start >= end) span.
    """
    if not quote:
        raise ValueError("quote must be non-empty")
    if char_start < 0 or char_end <= char_start:
        raise ValueError(
            f"invalid span window: char_start={char_start}, char_end={char_end}"
        )

    canon_quote = canonicalize_text(quote)
    # LLMs frequently wrap a citation in straight quotes that aren't in the
    # source text (curly-quote canonicalisation collapses ``“…”`` to ``"…"``).
    # Strip a single layer of wrapping ASCII quote characters so a quoted
    # citation still matches its unquoted span. This is purely a matcher
    # concern; the canonicalizer keeps quotes faithful.
    canon_quote_stripped = canon_quote.strip("\"'")
    window = page_text[char_start:char_end]
    canon_window = canonicalize_text(window)

    if canon_quote_stripped and canon_quote_stripped in canon_window:
        return MatchResult(
            matched=True,
            strategy=MatchStrategy.CANONICAL_EXACT,
            edit_distance=0,
        )

    if max_edit_distance > 0:
        distance = _best_window_distance(
            canon_quote_stripped or canon_quote, canon_window, max_edit_distance
        )
        if distance <= max_edit_distance:
            return MatchResult(
                matched=True,
                strategy=MatchStrategy.BOUNDED_FUZZY,
                edit_distance=distance,
            )

    return MatchResult(
        matched=False,
        strategy=MatchStrategy.NO_MATCH,
        edit_distance=-1,
    )
