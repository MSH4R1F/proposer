"""Provenance utilities: locating quoted passages and paragraph references.

Used by the proposition extractor (Task 6) to verify that a quoted
`source_passage` actually appears inside the loaded decision text, and to
attach paragraph references when present.

Pure CPU work — no I/O, no LLM. The matching tolerates whitespace and
unicode differences via :func:`normalize_for_matching` so that LLM-emitted
quotes (which often re-flow whitespace) still verify against the raw
extracted text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import normalize_for_matching


# ---------------------------------------------------------------------------
# Source span lookup
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSpan:
    """A located source passage within a normalized decision text.

    Offsets are into ``normalize_for_matching(full_text)``, NOT into the raw
    text. Callers that need raw-text offsets must do their own mapping; for
    the proposition KG, normalized offsets are sufficient because both the
    quoted passage and the stored span are derived from the same normalized
    representation.
    """

    start_char: int
    end_char: int
    matched_text: str


def find_source_span(source_passage: str, full_text: str) -> Optional[SourceSpan]:
    """Locate ``source_passage`` inside ``full_text`` (whitespace-tolerant).

    Both inputs are run through :func:`normalize_for_matching` (NFKC + collapse
    whitespace) before substring search, so quotes that differ only in
    whitespace or unicode form still match.

    Returns ``None`` if the passage cannot be located. Callers decide how to
    treat that — typically by rejecting the proposition.
    """
    if not source_passage or not full_text:
        return None

    normalized_passage = normalize_for_matching(source_passage)
    normalized_full = normalize_for_matching(full_text)

    if not normalized_passage:
        return None

    start = normalized_full.find(normalized_passage)
    if start == -1:
        return None

    end = start + len(normalized_passage)
    return SourceSpan(
        start_char=start,
        end_char=end,
        matched_text=normalized_full[start:end],
    )


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParagraphIndex:
    """A discovered paragraph reference and its location in normalized text."""

    ref: str
    start_char: int
    end_char: int


# Match a paragraph-leading number, optionally with a parenthesised sub-id,
# followed by a dot and whitespace, e.g. "1.", "12.", "12(3).", "A1." (rare).
#
# Known future-work / not handled in Phase 1:
#   - "Schedule 1 paragraph 4" style cross-references
#   - Roman numeral lists ("(i)", "(ii)")
#   - Indented sub-lists without the leading dot
#
# The pattern is anchored against the start of the (normalized) string OR a
# preceding space — after ``normalize_for_matching`` collapses whitespace,
# every paragraph break becomes a single space, so this is the closest
# analogue to "line-leading" we have.
_PARAGRAPH_RE = re.compile(
    # Allow an optional alphabetic prefix so refs like "A1." and "AB12." match
    # alongside plain digits ("12.") and parenthesised sub-ids ("12(3).").
    r"(?:^|(?<=\s))((?:[A-Za-z]+\d+|\d+)(?:\([A-Za-z0-9]+\))?)\.\s"
)


def split_paragraphs(full_text: str) -> list[ParagraphIndex]:
    """Heuristically detect paragraph references in a tribunal decision.

    Scans :func:`normalize_for_matching`-ed text for tokens like ``"1."``,
    ``"12."``, or ``"12(3)."`` that look like paragraph numbers. Each match
    becomes a :class:`ParagraphIndex` whose ``start_char``/``end_char`` are
    offsets into the normalized text.

    For Phase 1 this is intentionally simple — no de-duplication, no scoring
    of "is this really a paragraph?". The caller is free to filter further
    (e.g. reject monotonically-decreasing numbers as page artefacts).
    """
    if not full_text:
        return []

    normalized = normalize_for_matching(full_text)
    if not normalized:
        return []

    results: list[ParagraphIndex] = []
    for match in _PARAGRAPH_RE.finditer(normalized):
        ref = match.group(1)
        # ``match.start(1)`` is the start of the captured ref inside the
        # normalized text; the full match (including the trailing ". ")
        # gives us the end.
        results.append(
            ParagraphIndex(
                ref=ref,
                start_char=match.start(1),
                end_char=match.end(),
            )
        )

    return results


__all__ = [
    "SourceSpan",
    "ParagraphIndex",
    "find_source_span",
    "split_paragraphs",
]
