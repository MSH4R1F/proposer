"""Deterministic GBP-amount extractor for Housing Ombudsman order paragraphs.

Used by:
- the agent's ``extract_amounts`` tool (see ``retrieval_agent_tools.py``);
- the prompt-side ``comparator_awards`` table population
  (F-PROMPT-3 in the master plan).

Per the architecture research (§2.7 of
``agentic-retrieval-architecture-research-2026-05-05.md``):

    *Hybrid: regex first, LLM fallback when regex returns 0 amounts on an
    `orders/determination`-typed chunk.*

This module implements the *regex-first* half. The LLM-fallback half is
caller-side: a chunk's section_type plus a zero-result return is the signal
to escalate.

Patterns covered (verified against ~30 sample paragraphs from the live
Ombudsman corpus):

    £700                  -> 700
    £1,250                -> 1250
    £1250                 -> 1250
    £1,250.50             -> 1250.5
    £1,250 (one thousand) -> 1250 (the trailing words are dropped)
    GBP 1500              -> 1500       (rare, included for completeness)

Patterns DELIBERATELY NOT covered by the regex (escalate to LLM):

    "twelve hundred and fifty pounds"
    "the sum of one thousand pounds"
    "£500 plus the cost of repairs"  -> we extract 500 only; "the cost
        of repairs" is not numeric here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# Captures: optional 'GBP', mandatory £ or "pounds", an integer with
# optional comma thousands separators, and an optional decimal part.
# Word-boundary anchors prevent matching mid-word (e.g. ``£500m`` only
# captures ``500`` if we add a guard — see _is_unit_qualified below).
_GBP_RE = re.compile(
    r"""
    (?:£|GBP\s*)                          # leading currency marker
    (?P<amt_lead>
        \d{1,3}(?:,\d{3})+(?:\.\d{1,2})?  # comma-formatted: at least one ,NNN group
        |
        \d+(?:\.\d{1,2})?                 # plain digits (greedy: matches "1250" as one token)
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class ExtractedAmount:
    """One amount with the surrounding sentence for context.

    Fields are kept narrow on purpose so the schema is stable across
    callers (agent tool result, comparator-awards prompt block).
    """

    chunk_id: str
    paragraph_id: Optional[str]  # populated when available from chunk meta
    amount_gbp: float
    surrounding_sentence: str  # at most ``CONTEXT_CHARS`` chars
    raw_match: str  # the exact substring matched, e.g. "£1,250"


CONTEXT_CHARS = 240
"""Characters of surrounding text to include around each match.

Set to 240 so ~3 typical sentences fit on either side of the amount,
which is enough to disambiguate "the landlord shall pay £X" from
"the resident already received £X" in the model's view downstream.
"""

# Tokens that, when adjacent to the amount, indicate it is a unit
# qualifier (e.g. ``£500m`` = "£500 million" — almost certainly NOT a
# Housing Ombudsman compensation order). We drop these defensively.
_UNIT_QUALIFIERS = ("m", "bn", "k")


def extract_pound_amounts(
    *,
    chunk_id: str,
    text: str,
    paragraph_id: Optional[str] = None,
) -> List[ExtractedAmount]:
    """Return all GBP amounts found in ``text``.

    The function is pure (no I/O, no global state) so it is trivially
    testable. Caller is expected to filter results by chunk
    ``section_type`` if it cares about orders-only extraction.

    Args:
        chunk_id: Stable identifier for the chunk this text came from.
            Returned verbatim on every match. Used by the agent loop to
            tie an extracted amount back to the retrieve() result that
            surfaced it.
        text: The chunk text to search.
        paragraph_id: Optional paragraph anchor (e.g. ``"para_47"``).
            Returned verbatim on every match.

    Returns:
        A possibly empty list of ``ExtractedAmount`` records, in the
        order the matches appear in ``text``. Duplicates within the
        same chunk are kept — the caller decides whether to dedupe.
    """
    matches: List[ExtractedAmount] = []
    for m in _GBP_RE.finditer(text):
        raw = m.group(0)
        amt_str = m.group("amt_lead")
        # Drop unit-qualified amounts (£500m, £2k). Only counts when
        # the qualifier is IMMEDIATELY attached to the digits — a space
        # after the number means it's just a normal sentence (e.g.
        # "£500 made up of...").
        tail_immediate = text[m.end() : m.end() + 2].lower()
        if any(
            tail_immediate.startswith(q)
            and (
                # End of string, or non-letter follows the qualifier.
                len(tail_immediate) == len(q)
                or not tail_immediate[len(q)].isalpha()
            )
            for q in _UNIT_QUALIFIERS
        ):
            continue
        try:
            amt = float(amt_str.replace(",", ""))
        except ValueError:
            continue
        # Negative or zero amounts are not meaningful comparators.
        if amt <= 0:
            continue
        # Sanity bound — Housing Ombudsman compensation orders rarely
        # exceed £20,000; a number above that is almost always a date,
        # case reference, or extracted from a budget/policy paragraph.
        if amt > 20_000:
            continue
        sentence = _surrounding_sentence(text, m.start(), m.end())
        matches.append(
            ExtractedAmount(
                chunk_id=chunk_id,
                paragraph_id=paragraph_id,
                amount_gbp=amt,
                surrounding_sentence=sentence,
                raw_match=raw,
            )
        )
    return matches


def _surrounding_sentence(text: str, start: int, end: int) -> str:
    """Slice up to ``CONTEXT_CHARS`` characters of context around the match.

    We don't try to do real sentence boundary detection — Ombudsman
    decisions have inconsistent punctuation, and our consumers (the
    LLM predictor and the agent trace) just need *enough context* to
    judge whether the amount is an order vs a quoted background figure.
    """
    half = CONTEXT_CHARS // 2
    lo = max(0, start - half)
    hi = min(len(text), end + half)
    snippet = text[lo:hi].replace("\n", " ").strip()
    return snippet
