"""SHA-20 Phase 9: deterministic safety / out-of-scope detection.

Phrase matching is substring-based for the common cases. A small set
of "must be word-bounded" phrases (e.g. ``section 21``, which would
otherwise match ``section 213`` and ``section 214``) is matched with a
word-boundary regex to avoid eating deposit-protection cases.


This module is intentionally tiny and string-based. It runs **before**
any LLM call so prompt-injection attempts and obviously out-of-scope
matters never reach the classifier. Three categories are detected:

* ``prompt_injection`` — patterns that try to override the system
  prompt or coerce roleplay (e.g. "ignore previous instructions",
  "system:", "disregard", "pretend you are a lawyer", "repeat after
  me", "reveal training data"). These trigger ``outcome="abstain"``.
* ``cross_domain`` — the user explicitly mixes housing AND employment
  matters in a single message. This is ambiguous-by-construction;
  we ask them to pick a side before any classifier runs.
* ``out_of_scope`` — explicit non-supported topics
  (immigration, divorce, will/probate, criminal/assault, vet/medical,
  small claims court, leasehold service charges, Section 21
  possession, freeholder, HMRC tax). These trigger ``outcome="abstain"``
  with a polite refusal reason.

A fourth signal — ``ambiguous`` — is detected here for very short
inputs that mention a domain hint but lack any concrete fact. The
caller is expected to surface a clarifier rather than route blindly.

All checks are case-insensitive substring matches with explicit
phrase lists. The implementation deliberately avoids regex
look-ahead so the cost stays predictable and the matches stay
auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Phrase lists
# ---------------------------------------------------------------------------


_PROMPT_INJECTION_PHRASES: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore prior instructions",
    "ignore your instructions",
    "disregard your instructions",
    "disregard previous",
    "disregard prior",
    "disregard all prior",
    "system: ",
    "system:",
    "respond as a lawyer",
    "respond as if you are a lawyer",
    "act as a lawyer",
    "pretend you are a lawyer",
    "pretend to be a lawyer",
    "you are now a lawyer",
    "i'm the system administrator",
    "i am the system administrator",
    "reveal training data",
    "reveal your training data",
    "show training data",
    "without all the disclaimers",
    "without the disclaimer",
    "skip the disclaimer",
    "repeat after me",
    "tenant always wins",
    "landlord always wins",
    "pass-through prompt",
    "tell me i'll win",
    "tell me i will win",
    "refuse to settle",
)


# Out-of-scope phrases. Hits here trigger abstain, NOT a clarifier.
_OUT_OF_SCOPE_PHRASES: tuple[str, ...] = (
    "buy a house",
    "buy a property",
    "mortgage",
    "divorce",
    "child custody",
    "immigration",
    "visa",
    "asylum",
    "small claims court",
    "sue someone",
    "criminal",
    "assault",
    "assaulted",
    "i need a will",
    "i need a will written",
    "wills and probate",
    "probate",
    "tax dispute",
    "hmrc",
    "vet",
    # NOTE: explicit "leasehold service charge" is handled by the
    # routing ``rules.py`` Property-Chamber-non-RRO branch (audit D4 —
    # research capture, not abstain). "freeholder" stays here because
    # it's a different forum (county court / FTT) entirely.
    "freeholder",
    # "section 21" is word-bounded to avoid eating "section 213"/"214"
    # (deposit-protection penalties under HA 2004). See
    # ``_OUT_OF_SCOPE_WORD_BOUNDED`` below.
    "possession proceedings",
    "possession order",
    "general legal advice",
    "general uk law",
    "asking generally about uk law",
    "give me legal advice",
    "are you actually a lawyer",
    "are you a lawyer",
)


# Phrases that need word-boundary matching to avoid false positives.
# Each entry is a regex pattern; the surrounding ``\b`` is added in
# the matcher.
_OUT_OF_SCOPE_WORD_BOUNDED: tuple[str, ...] = (
    r"section\s+21",  # NOT "section 213" / "section 214"
)
_OUT_OF_SCOPE_WORD_BOUNDED_RE = re.compile(
    r"\b(?:" + "|".join(_OUT_OF_SCOPE_WORD_BOUNDED) + r")\b",
    flags=re.IGNORECASE,
)


# Cross-domain markers. These are pairs that, if BOTH appear in the same
# input, indicate the user is mixing matters from two different domain
# families. The router can't safely pick one without a clarifier, so we
# abstain.
_CROSS_DOMAIN_PAIRS: tuple[tuple[str, str], ...] = (
    ("deposit", "dismissal"),
    ("deposit", "fired"),
    ("deposit", "unfair dismissal"),
    ("deposit", "wrongful dismissal"),
    ("landlord", "employer"),
    ("repairs", "dismissal"),
    ("repairs", "fired"),
    ("disrepair", "dismissal"),
    ("rent repayment", "dismissal"),
    ("rent repayment", "fired"),
    ("deposit", "repairs issue"),
    ("deposit", "repairs case"),
    ("repairs case", "deposit case"),
    ("deposit and a repairs", ""),
    ("housing repairs case and a deposit", ""),
)


# Phrases that mean "I have multiple matters" without naming a second
# domain. Used as a fallback for the abstain bucket.
_CROSS_DOMAIN_PHRASES: tuple[str, ...] = (
    "deposit issue and a repairs issue",
    "deposit case and a housing repairs case",
    "council housing repairs case and a deposit",
    "and a wrongful dismissal claim",
    "and a unfair dismissal claim",
    "deposit and a wrongful dismissal",
    "both a deposit and a wrongful dismissal",
)


# Phrases that look ambiguous (very general, no concrete domain commitment).
# These trigger a clarifier rather than abstain.
_AMBIGUOUS_PHRASES: tuple[str, ...] = (
    "i want compensation but",
    "tell me what the tenancy deposit law is",
    "what does the law say",
    "what are my rights",
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SafetyHit:
    """Outcome of :func:`run_safety_checks`.

    ``kind`` is one of:

    * ``"none"`` — input passed all deterministic safety checks.
    * ``"prompt_injection"`` — caller should ``abstain``.
    * ``"out_of_scope"`` — caller should ``abstain``.
    * ``"cross_domain"`` — caller should ``abstain`` (cannot route
      ambiguously).
    * ``"ambiguous"`` — caller should ``clarify``.
    """

    kind: str
    matched_phrase: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _contains_any(text: str, phrases: Iterable[str]) -> Optional[str]:
    for phrase in phrases:
        if not phrase:
            continue
        if phrase in text:
            return phrase
    return None


def run_safety_checks(text: str) -> SafetyHit:
    """Run the deterministic safety pipeline against an intake message.

    Order matters. Prompt-injection wins over everything else (we never
    look at semantics of an attempted injection). Out-of-scope wins over
    cross-domain (a divorce question that also mentions a deposit is
    still out of scope). Cross-domain wins over ambiguous (we don't
    silently pick a domain when both appear).

    Returns a :class:`SafetyHit` whose ``kind`` is ``"none"`` when no
    pattern fires.
    """
    if not text or not text.strip():
        return SafetyHit(kind="ambiguous", reason="empty message")

    lowered = text.lower()

    hit = _contains_any(lowered, _PROMPT_INJECTION_PHRASES)
    if hit is not None:
        return SafetyHit(
            kind="prompt_injection",
            matched_phrase=hit,
            reason="prompt-injection pattern detected",
        )

    hit = _contains_any(lowered, _OUT_OF_SCOPE_PHRASES)
    if hit is not None:
        return SafetyHit(
            kind="out_of_scope",
            matched_phrase=hit,
            reason="explicit out-of-scope topic",
        )

    wb = _OUT_OF_SCOPE_WORD_BOUNDED_RE.search(lowered)
    if wb is not None:
        return SafetyHit(
            kind="out_of_scope",
            matched_phrase=wb.group(0),
            reason="explicit out-of-scope topic",
        )

    # Cross-domain pair detection: BOTH halves of any pair must be in
    # the text.
    for left, right in _CROSS_DOMAIN_PAIRS:
        if not left:
            continue
        if right and left in lowered and right in lowered:
            return SafetyHit(
                kind="cross_domain",
                matched_phrase=f"{left} + {right}",
                reason="multiple matter families in one message",
            )
        if not right and left in lowered:
            return SafetyHit(
                kind="cross_domain",
                matched_phrase=left,
                reason="multiple matter families in one message",
            )

    hit = _contains_any(lowered, _CROSS_DOMAIN_PHRASES)
    if hit is not None:
        return SafetyHit(
            kind="cross_domain",
            matched_phrase=hit,
            reason="multiple matter families in one message",
        )

    hit = _contains_any(lowered, _AMBIGUOUS_PHRASES)
    if hit is not None:
        return SafetyHit(
            kind="ambiguous",
            matched_phrase=hit,
            reason="generic / non-specific request",
        )

    return SafetyHit(kind="none")


__all__ = ["SafetyHit", "run_safety_checks"]
