"""SHA-126: RRO statutory-grounds filter.

Audit gate (D4) — RRO ONLY. The filter has three layers:

1. *Hard rejects* on terms that prove the document is out-of-scope
   (leasehold service charges, ground rent, Tenant Fees Act, park homes,
   building safety). These terms cause an immediate REJECT regardless of
   sub-category.
2. *Sub-category gate* — the GOV.UK search hit must have the RRO
   ``sub_categories`` slug (``RRO_SUB_CATEGORY``).
3. *Statutory ground allowlist* — body text must contain at least one of
   the offence sections that can ground an RRO. This protects against
   mis-tagged hits where the page has the RRO sub-category but the
   decision is actually a non-RRO Housing Act matter.

ACCEPT requires (1) no hard rejects, (2) sub-category match, AND (3) at
least one statutory ground hit.

Anything that passes (1)+(2) but not (3) -> UNCERTAIN with reason
``ground_not_recognised``. Anything that fails (1) or (2) -> REJECT with
the appropriate reason. Reject reasons are written verbatim to
``excluded.jsonl``.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from .config import RRO_SUB_CATEGORY
from .models import FilterDecision, GovUKSearchHit


# ---------------------------------------------------------------------------
# Statutory grounds for RRO offences (allowlist)
#
# Each entry maps a canonical label (persisted to SourceMetadata.extra
# ``statutory_grounds``) to one or more case-insensitive regexes. We keep
# the regexes deliberately permissive on punctuation/whitespace because
# tribunal decisions are inconsistent ("section 72(1)" vs "s.72(1)" vs
# "s 72").
# ---------------------------------------------------------------------------

_FLAGS = re.IGNORECASE | re.DOTALL

# Helper to allow "s.", "s ", "section ", "ss." between act and number.
_S = r"(?:s\.?\s*|section\s+|ss\.?\s*)"


STATUTORY_GROUND_PATTERNS: List[Tuple[str, List[re.Pattern]]] = [
    (
        "Housing Act 2004 s.72(1) (unlicensed HMO)",
        [
            re.compile(r"housing\s+act\s+2004[^.]{0,80}?" + _S + r"72\s*\(\s*1\s*\)", _FLAGS),
            re.compile(_S + r"72\s*\(\s*1\s*\)\s+of\s+the\s+housing\s+act\s+2004", _FLAGS),
        ],
    ),
    (
        "Housing Act 2004 s.72 (HMO licensing)",
        [
            re.compile(r"housing\s+act\s+2004[^.]{0,80}?" + _S + r"72\b(?!\s*\()", _FLAGS),
        ],
    ),
    (
        "Housing Act 2004 s.95 (selective licensing)",
        [
            re.compile(r"housing\s+act\s+2004[^.]{0,80}?" + _S + r"95\b", _FLAGS),
            re.compile(_S + r"95\s+of\s+the\s+housing\s+act\s+2004", _FLAGS),
        ],
    ),
    (
        "Housing Act 2004 s.30 (improvement notice failure)",
        [
            re.compile(r"housing\s+act\s+2004[^.]{0,80}?" + _S + r"30\b", _FLAGS),
            re.compile(_S + r"30\s+of\s+the\s+housing\s+act\s+2004", _FLAGS),
        ],
    ),
    (
        "Housing Act 2004 s.32 (prohibition order failure)",
        [
            re.compile(r"housing\s+act\s+2004[^.]{0,80}?" + _S + r"32\b", _FLAGS),
            re.compile(_S + r"32\s+of\s+the\s+housing\s+act\s+2004", _FLAGS),
        ],
    ),
    (
        "Protection from Eviction Act 1977 s.1(2)",
        [
            re.compile(
                r"protection\s+from\s+eviction\s+act\s+1977[^.]{0,80}?" + _S + r"1\s*\(\s*2\s*\)",
                _FLAGS,
            ),
            re.compile(_S + r"1\s*\(\s*2\s*\)\s+of\s+the\s+protection\s+from\s+eviction", _FLAGS),
        ],
    ),
    (
        "Protection from Eviction Act 1977 s.1(3)",
        [
            re.compile(
                r"protection\s+from\s+eviction\s+act\s+1977[^.]{0,80}?" + _S + r"1\s*\(\s*3\s*\)(?!\s*A)",
                _FLAGS,
            ),
            re.compile(
                _S + r"1\s*\(\s*3\s*\)(?!\s*A)\s+of\s+the\s+protection\s+from\s+eviction",
                _FLAGS,
            ),
        ],
    ),
    (
        "Protection from Eviction Act 1977 s.1(3A)",
        [
            re.compile(
                r"protection\s+from\s+eviction\s+act\s+1977[^.]{0,80}?" + _S + r"1\s*\(\s*3A\s*\)",
                _FLAGS,
            ),
            re.compile(_S + r"1\s*\(\s*3A\s*\)\s+of\s+the\s+protection\s+from\s+eviction", _FLAGS),
        ],
    ),
    (
        "Criminal Law Act 1977 s.6 (violence for securing entry)",
        [
            re.compile(r"criminal\s+law\s+act\s+1977[^.]{0,80}?" + _S + r"6\b", _FLAGS),
            re.compile(_S + r"6\s+of\s+the\s+criminal\s+law\s+act\s+1977", _FLAGS),
        ],
    ),
    (
        "Housing and Planning Act 2016 s.21 (banning order breach)",
        [
            re.compile(r"housing\s+and\s+planning\s+act\s+2016[^.]{0,80}?" + _S + r"21\b", _FLAGS),
            re.compile(_S + r"21\s+of\s+the\s+housing\s+and\s+planning\s+act\s+2016", _FLAGS),
            re.compile(r"banning\s+order[^.]{0,80}?" + _S + r"21", _FLAGS),
        ],
    ),
    (
        "Housing and Planning Act 2016 ss.40-52 (RRO regime)",
        [
            re.compile(
                r"housing\s+and\s+planning\s+act\s+2016[^.]{0,120}?"
                + _S
                + r"(?:40|41|42|43|44|45|46|47|48|49|50|51|52)\b",
                _FLAGS,
            ),
            re.compile(
                _S
                + r"(?:40|41|42|43|44|45|46|47|48|49|50|51|52)\s+of\s+the\s+housing\s+and\s+planning\s+act\s+2016",
                _FLAGS,
            ),
        ],
    ),
    (
        "Housing Act 1988 s.16J (Renters' Rights Act 2025)",
        [
            re.compile(r"housing\s+act\s+1988[^.]{0,80}?" + _S + r"16J", _FLAGS),
            re.compile(_S + r"16J\s+of\s+the\s+housing\s+act\s+1988", _FLAGS),
            re.compile(r"renters[’']?\s+rights\s+act\s+2025", _FLAGS),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Hard reject patterns (order matters: first hit wins for reason).
# ---------------------------------------------------------------------------

_HARD_REJECT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("hard_reject:service_charge", re.compile(r"\bservice\s+charge", _FLAGS)),
    ("hard_reject:ground_rent", re.compile(r"\bground\s+rent", _FLAGS)),
    ("hard_reject:tenant_fees_act", re.compile(r"tenant\s+fees\s+act", _FLAGS)),
    ("hard_reject:park_home", re.compile(r"\bpark\s+home", _FLAGS)),
    (
        "hard_reject:building_safety",
        re.compile(r"building\s+safety(?:\s+act)?", _FLAGS),
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _match_grounds(body_text: str) -> List[str]:
    """Return canonical labels of every statutory ground found in ``body_text``."""
    found: List[str] = []
    for label, patterns in STATUTORY_GROUND_PATTERNS:
        for pat in patterns:
            if pat.search(body_text):
                found.append(label)
                break  # one match per label is enough
    return found


def _match_hard_rejects(body_text: str) -> List[str]:
    """Return reject reasons for any hard-reject signals present."""
    reasons: List[str] = []
    for reason, pat in _HARD_REJECT_PATTERNS:
        if pat.search(body_text):
            reasons.append(reason)
    return reasons


def classify_rro(
    hit: GovUKSearchHit,
    body_text: str | None,
) -> Tuple[FilterDecision, List[str], List[str]]:
    """Classify a GOV.UK search hit + body text against the RRO allowlist.

    Returns:
        (decision, statutory_grounds, reject_reasons).
        ``statutory_grounds`` is non-empty only on ACCEPT.
        ``reject_reasons`` is empty on ACCEPT.

    The function is *pure* — no I/O, no side effects — so it is trivially
    testable and safe to call from inside the async scraper loop.
    """
    grounds: List[str] = []
    reasons: List[str] = []

    # 0. Sub-category gate ------------------------------------------------
    sub_cats = list(hit.sub_categories or [])
    if RRO_SUB_CATEGORY not in sub_cats:
        reasons.append("sub_category_not_rro")

    # 1. Body text required for any positive decision --------------------
    if not body_text or not body_text.strip():
        # No body to inspect. If the sub-category gate already failed,
        # call it a REJECT; otherwise UNCERTAIN with no_body reason.
        if reasons:
            return FilterDecision.REJECT, [], reasons
        return FilterDecision.UNCERTAIN, [], ["no_body_text"]

    # 2. Hard rejects always win -----------------------------------------
    hard = _match_hard_rejects(body_text)
    if hard:
        reasons.extend(hard)
        # Hard reject is fatal, regardless of sub-category match.
        return FilterDecision.REJECT, [], reasons

    # If the sub-category gate failed and there are no hard rejects we
    # still want a clean REJECT (the document is simply not in scope).
    if "sub_category_not_rro" in reasons:
        return FilterDecision.REJECT, [], reasons

    # 3. Statutory grounds allowlist -------------------------------------
    grounds = _match_grounds(body_text)
    if not grounds:
        return FilterDecision.UNCERTAIN, [], ["ground_not_recognised"]

    return FilterDecision.ACCEPT, grounds, []


__all__ = [
    "classify_rro",
    "STATUTORY_GROUND_PATTERNS",
]
