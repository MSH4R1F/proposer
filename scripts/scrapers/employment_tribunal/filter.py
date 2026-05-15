"""Two-stage filter for GOV.UK Employment Tribunal decisions.

Stage 1 is *discovery*: a URL-level filter that narrows the listing page to
decisions tagged ``unfair-dismissal``. That happens implicitly via the listing
URL query parameter in ``config.ScraperConfig`` — there is no Python logic for
Stage 1 because GOV.UK does the slicing for us.

Stage 2 is *merits-quality* and is what this module implements. It scans the
parsed metadata plus the body text and rejects:

* preliminary-only, strike-out, withdrawal, reconsideration, or
  jurisdiction-only decisions
* default judgments / no-response decisions with too little reasoning
* remedy-only decisions without liability reasoning
* decisions where unfair dismissal is not the lead merits issue
  (e.g. discrimination-led claims that happen to mention dismissal)

Rejected rows are kept (per spec §5.2) so they can be used later for
abstention/routing tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .models import ETCaseMetadata


# ---------------------------------------------------------------------------
# Reject signals — case-management / non-merits decisions
# ---------------------------------------------------------------------------

# Each (regex, reason_code) pair. Reason codes are stable strings that the
# Stage-2 manifest persists into excluded.jsonl.
_NON_MERITS_PATTERNS: List[tuple] = [
    (re.compile(r"\bstr[au]ck[\- ]out\b", re.IGNORECASE), "strike_out"),
    (re.compile(r"\bstrike[\- ]out\b", re.IGNORECASE), "strike_out"),
    (re.compile(r"\bwithdrawn\b", re.IGNORECASE), "withdrawal"),
    (re.compile(r"\bwithdrawal\b", re.IGNORECASE), "withdrawal"),
    (re.compile(r"\breconsideration\b", re.IGNORECASE), "reconsideration"),
    (re.compile(r"\bdefault judgment\b", re.IGNORECASE), "default_judgment"),
    (re.compile(r"\bremedy\s+hearing\b", re.IGNORECASE), "remedy_only"),
    (re.compile(r"\bremedy[\- ]only\b", re.IGNORECASE), "remedy_only"),
    (re.compile(r"\bcase[\- ]management\b", re.IGNORECASE), "preliminary_only"),
    (re.compile(r"\bpreliminary hearing\b", re.IGNORECASE), "preliminary_only"),
    (re.compile(r"\bpreliminary issue\b", re.IGNORECASE), "preliminary_only"),
    (re.compile(r"\bjurisdiction (?:only|hearing|decision)\b", re.IGNORECASE), "jurisdiction_only"),
]

# Outcome-level rejects (parser already labelled the decision).
_NON_MERITS_OUTCOMES = {
    "withdrawn",
    "struck-out",
    "preliminary",
    "default-judgment",
    "remedy-only",
    "reconsideration",
    "jurisdiction-only",
}


# ---------------------------------------------------------------------------
# Merits-quality require signals — lead-issue is unfair dismissal
# ---------------------------------------------------------------------------

# The decision must demonstrably engage the unfair-dismissal merits framework.
# We require at least one of:
_REQUIRE_MERITS_PATTERNS = [
    re.compile(r"\bunfair(?:ly)? dismiss(?:al|ed|ing)\b", re.IGNORECASE),
    re.compile(r"\bsection\s*98\b", re.IGNORECASE),
    re.compile(r"\bs\.?\s*98\b", re.IGNORECASE),
    re.compile(r"Employment Rights Act 1996", re.IGNORECASE),
    re.compile(r"\bERA\s*1996\b", re.IGNORECASE),
    re.compile(r"band of reasonable responses", re.IGNORECASE),
    re.compile(r"\bPolkey\b", re.IGNORECASE),
    re.compile(r"\bpotentially fair reason\b", re.IGNORECASE),
]

# Lead-issue diversion signals: when these dominate the body, unfair-dismissal
# is unlikely to be the lead merits issue. Used in combination with the
# merits-require signals (we accept only when both fire).
_LEAD_ISSUE_DIVERSION_PATTERNS = [
    # Discrimination / equality
    re.compile(r"\bEquality Act 2010\b", re.IGNORECASE),
    re.compile(r"\bdirect discrimination\b", re.IGNORECASE),
    re.compile(r"\bindirect discrimination\b", re.IGNORECASE),
    re.compile(r"\bharassment\b", re.IGNORECASE),
    re.compile(r"\bvictimisation\b", re.IGNORECASE),
    # Whistleblowing
    re.compile(r"\bprotected disclosure\b", re.IGNORECASE),
    re.compile(r"\bwhistle[\- ]?blow", re.IGNORECASE),
    # Wages / working time
    re.compile(r"\bunlawful deduction\b", re.IGNORECASE),
    re.compile(r"\bworking time\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class FilterResult:
    """Decision returned by :func:`keep_unfair_dismissal_merits_only`.

    ``matched_signals`` records the patterns that fired (kept or rejected),
    so excluded.jsonl can audit why a row landed where it did. ``excerpt``
    is an 80-char-wide window around the first matched signal — useful for
    eyeballing borderline cases in the pilot review.
    """

    keep: bool
    matter_types: List[str] = field(default_factory=list)
    reject_reason: Optional[str] = None
    matched_signals: List[str] = field(default_factory=list)
    excerpt: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _excerpt_for(text: str, pattern: re.Pattern, span: int = 80) -> Optional[str]:
    if not text:
        return None
    m = pattern.search(text)
    if not m:
        return None
    start = max(0, m.start() - span)
    end = min(len(text), m.end() + span)
    return text[start:end].strip()


def _scan_patterns(text: str, patterns) -> List[re.Pattern]:
    hits = []
    if not text:
        return hits
    for p in patterns:
        if p.search(text):
            hits.append(p)
    return hits


# ---------------------------------------------------------------------------
# Stage 2 implementation
# ---------------------------------------------------------------------------


def keep_unfair_dismissal_merits_only(
    metadata: ETCaseMetadata, raw_text: str
) -> FilterResult:
    """Decide whether to keep an ET decision in the unfair-dismissal corpus.

    KEEP iff:

    1. The decision engages the unfair-dismissal merits framework (one of
       the ERA-1996-s98 / Polkey / band-of-reasonable-responses signals).
    2. No non-merits reject pattern (strike-out / withdrawal / preliminary /
       reconsideration / default judgment / remedy-only / jurisdiction-only)
       fires.
    3. The decision is not lead-by-diversion (Equality Act 2010,
       whistleblowing, unlawful-deduction-of-wages, working-time as the
       dominant framework with only an incidental unfair-dismissal mention).
       We approximate "dominant" as ``diversion_hits > merits_hits``.
    4. The outcome (if normalised) is not in the non-merits outcome set.

    REJECT (with reason code) otherwise. The reason code is one of:

    * ``strike_out`` / ``withdrawal`` / ``reconsideration``
    * ``default_judgment`` / ``preliminary_only`` / ``remedy_only``
    * ``jurisdiction_only``
    * ``no_unfair_dismissal_merits_signal``
    * ``unfair_dismissal_not_lead_issue``
    """
    body = raw_text or ""

    # Rule 1 — non-merits regex over body text. First match wins so excerpts
    # are explainable.
    for pattern, reason in _NON_MERITS_PATTERNS:
        if pattern.search(body):
            return FilterResult(
                keep=False,
                reject_reason=reason,
                matched_signals=[pattern.pattern],
                excerpt=_excerpt_for(body, pattern),
            )

    # Rule 2 — outcome-level rejection (parser already normalised).
    if metadata.outcome_normalized and metadata.outcome_normalized in _NON_MERITS_OUTCOMES:
        return FilterResult(
            keep=False,
            reject_reason=metadata.outcome_normalized.replace("-", "_"),
            matched_signals=[f"outcome_normalized={metadata.outcome_normalized}"],
            excerpt=None,
        )

    # Rule 3 — must engage unfair-dismissal merits.
    merits_hits = _scan_patterns(body, _REQUIRE_MERITS_PATTERNS)
    if not merits_hits:
        return FilterResult(
            keep=False,
            reject_reason="no_unfair_dismissal_merits_signal",
            matched_signals=[],
            excerpt=None,
        )

    # Rule 4 — not lead-by-diversion.
    diversion_hits = _scan_patterns(body, _LEAD_ISSUE_DIVERSION_PATTERNS)
    if len(diversion_hits) > len(merits_hits):
        return FilterResult(
            keep=False,
            reject_reason="unfair_dismissal_not_lead_issue",
            matched_signals=[p.pattern for p in diversion_hits],
            excerpt=_excerpt_for(body, diversion_hits[0]),
        )

    # KEEP.
    return FilterResult(
        keep=True,
        matter_types=["unfair_dismissal"],
        matched_signals=[p.pattern for p in merits_hits],
        excerpt=_excerpt_for(body, merits_hits[0]),
    )


__all__ = ["FilterResult", "keep_unfair_dismissal_merits_only"]
