"""SHA-20 Phase 9: Deterministic-first domain router.

This package provides a small, dependency-light router that decides which
domain spec a free-form intake message belongs to. It is built around
five rules drawn from the SHA-20 Phase 9 plan:

1. Deterministic safety / out-of-scope checks come first
   (:mod:`safety`).
2. Enabled-domain + per-stage allowlist filters happen before any
   classification — the classifier never sees disabled domains.
3. High-precision keyword/rule routes (:mod:`rules`) fire for the
   common deposit / repairs / RRO / unfair-dismissal phrasings that we
   know we cover today.
4. An LLM classifier (:mod:`llm_classifier`) is invoked **only** when
   the rules are inconclusive. It is wrapped in a small ``Protocol`` so
   tests can pass a stub.
5. Deterministic post-checks re-apply safety + enabled-domain filtering
   to whatever the LLM produced; the LLM cannot override those gates.
6. If neither rules nor the LLM clear the
   ``confidence >= 0.80, margin >= 0.15`` bar the router asks one
   clarifying question.

The router output is a :class:`RouteDecision` dataclass; callers in
``apps/api`` map the four ``outcome`` values onto chat / API responses.

Wage disputes and broad Property Chamber non-RRO matters are routed to
``unsupported`` (with ``capture_in="research"``) per audit decisions D4
and D5 — this happens deterministically in :mod:`rules`, not in the
LLM. The LLM cannot reverse that.
"""

from .domain_router import (
    DomainRouter,
    RouteDecision,
    RouteOutcome,
    build_default_router,
)
from .llm_classifier import LLMClassification, LLMClassifierClient
from .rules import RuleHit, RuleSet
from .safety import SafetyHit, run_safety_checks

__all__ = [
    "DomainRouter",
    "LLMClassification",
    "LLMClassifierClient",
    "RouteDecision",
    "RouteOutcome",
    "RuleHit",
    "RuleSet",
    "SafetyHit",
    "build_default_router",
    "run_safety_checks",
]
