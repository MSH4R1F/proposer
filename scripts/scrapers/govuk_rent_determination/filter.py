"""SHA-138: MNR matter-code filter for the rent-determination scraper.

The FTT(PC) case reference embeds a matter-type slug (e.g.
``MAN/00BY/MNR/2024/0123``). We accept hits whose case reference contains
``/MNR/`` and reject everything else. No body-text statutory-ground
analysis is needed because the matter code is canonical for s.13
rent-increase referrals.

The filter is *pure* — no I/O, no side effects.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .config import MNR_MATTER_CODE
from .models import FilterDecision, GovUKSearchHit


# ---------------------------------------------------------------------------
# Case-reference patterns (case-insensitive). FTT(PC) refs are uppercase
# in the listings, but defensive matching avoids false rejects from
# whitespace or stray lowercase variants in title strings.
# ---------------------------------------------------------------------------

_CASE_REF_PATTERNS: List[re.Pattern] = [
    # Canonical: REGION/00CC/MNR/YYYY/NNNN with various separators.
    re.compile(
        r"\b[A-Z]{2,4}\s*/\s*[0-9A-Z]{3,5}\s*/\s*MNR\s*/\s*\d{2,4}\s*/\s*\d{1,5}\b",
        re.IGNORECASE,
    ),
    # Slug form on GOV.UK: man-slash-00cc-slash-mnr-slash-2024-slash-0123.
    re.compile(r"(^|[\-/])mnr([\-/])", re.IGNORECASE),
]


def _has_mnr_marker(text: str) -> bool:
    return any(p.search(text) for p in _CASE_REF_PATTERNS)


def classify_mnr(
    hit: GovUKSearchHit,
    body_text: str | None,
    case_reference: str | None = None,
) -> Tuple[FilterDecision, List[str]]:
    """Classify a GOV.UK search hit + optional body text against the MNR rule.

    Args:
        hit: The search-result row.
        body_text: Decoded body text from the content API or PDF.
        case_reference: Parsed case reference if already extracted.

    Returns:
        ``(decision, reject_reasons)``. ``reject_reasons`` is empty on
        ACCEPT.
    """
    reasons: List[str] = []

    if case_reference and _has_mnr_marker(case_reference):
        return FilterDecision.ACCEPT, []
    if hit.title and _has_mnr_marker(hit.title):
        return FilterDecision.ACCEPT, []
    if hit.link and _has_mnr_marker(hit.link):
        return FilterDecision.ACCEPT, []
    if body_text and _has_mnr_marker(body_text):
        return FilterDecision.ACCEPT, []

    reasons.append("not_mnr_matter_code")
    return FilterDecision.REJECT, reasons


__all__ = [
    "classify_mnr",
    "MNR_MATTER_CODE",
]
