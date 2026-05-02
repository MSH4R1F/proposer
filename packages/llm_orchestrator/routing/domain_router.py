"""SHA-20 Phase 9: deterministic-first domain router.

See ``packages/llm_orchestrator/routing/__init__.py`` for the high-level
pipeline. This module wires safety, rules, and the LLM fallback into a
single :class:`DomainRouter`. The four user-facing matter labels
(audit decision: do not surface internal domain ids) are kept here so
the API and the frontend can both reuse them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional, Sequence

from .llm_classifier import (
    LLMClassification,
    LLMClassifierClient,
    NullLLMClassifier,
)
from .rules import (
    DEPOSIT_ID,
    EMPLOYMENT_ID,
    REPAIRS_SOCIAL_ID,
    RRO_ID,
    RuleHit,
    RuleSet,
)
from .safety import SafetyHit, run_safety_checks


# ---------------------------------------------------------------------------
# Outcome model
# ---------------------------------------------------------------------------


RouteOutcome = Literal["route", "clarify", "unsupported", "abstain"]


# Confidence / margin gates (plan §9 acceptance criteria).
DEFAULT_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_MARGIN_THRESHOLD = 0.15


# Plain-English matter labels (no internal domain ids in user-facing UI).
USER_FACING_MATTER_LABELS: dict[str, str] = {
    DEPOSIT_ID: "Deposit deductions",
    REPAIRS_SOCIAL_ID: "Repairs, damp, mould, or safety",
    RRO_ID: "Rent repayment order issue",
    EMPLOYMENT_ID: "Work dismissal issue",
}


def matter_label_for(domain_id: str) -> str:
    """Return the plain-English matter label for ``domain_id``.

    Falls back to a generic "Legal matter" string for unknown ids so we
    never accidentally render a raw domain id in the UI.
    """
    return USER_FACING_MATTER_LABELS.get(domain_id, "Legal matter")


@dataclass(frozen=True)
class RouteDecision:
    """Outcome returned by :meth:`DomainRouter.route`.

    * ``outcome`` — one of ``route``, ``clarify``, ``unsupported``,
      ``abstain``.
    * ``domain_id`` — only set when ``outcome=="route"``.
    * ``confidence`` / ``margin`` — populated by the LLM fallback when
      it fires. ``None`` for rule-only routes (which are by construction
      "deterministic certainty").
    * ``clarifier_text`` — the question to ask the user when
      ``outcome=="clarify"``. Always plain English.
    * ``candidate_domains`` — list of domain ids the user can pick from
      when answering the clarifier.
    * ``reason`` — short rationale (logged, surfaced as debug info).
    * ``capture_in`` — for ``unsupported`` outcomes, where the matter
      should be logged ("research" / "log_only").
    * ``routing_metadata`` — free-form provenance (selected_via,
      rule_id, safety_hit, ...) carried through to traces.
    """

    outcome: RouteOutcome
    domain_id: Optional[str] = None
    confidence: Optional[float] = None
    margin: Optional[float] = None
    clarifier_text: Optional[str] = None
    candidate_domains: list[str] = field(default_factory=list)
    reason: Optional[str] = None
    capture_in: Optional[Literal["research", "log_only"]] = None
    routing_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_matter_labels(self) -> list[str]:
        """User-facing labels for ``candidate_domains``."""
        return [matter_label_for(d) for d in self.candidate_domains]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class DomainRouter:
    """Deterministic-first domain router.

    Pipeline (in order):

    1. Deterministic safety / out-of-scope (:func:`run_safety_checks`).
    2. Enabled-domain filter — disabled domains never reach the
       classifier.
    3. High-precision rules (:class:`RuleSet`).
    4. LLM fallback (:class:`LLMClassifierClient`) only if rules are
       inconclusive.
    5. Deterministic post-checks on the LLM output.
    6. Clarifier when no candidate clears the confidence/margin bar.
    """

    def __init__(
        self,
        *,
        enabled_domains: Iterable[str],
        rules: Optional[RuleSet] = None,
        llm_classifier: Optional[LLMClassifierClient] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
    ) -> None:
        self._enabled = tuple(enabled_domains)
        self._rules = rules or RuleSet()
        self._llm: LLMClassifierClient = llm_classifier or NullLLMClassifier()
        self._confidence_threshold = float(confidence_threshold)
        self._margin_threshold = float(margin_threshold)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def enabled_domains(self) -> tuple[str, ...]:
        return self._enabled

    def has_llm_classifier(self) -> bool:
        """True when a non-null LLM classifier is wired up.

        The :class:`NullLLMClassifier` always returns
        ``domain_id=None``; routes that rely on the LLM cannot pass.
        """
        return not isinstance(self._llm, NullLLMClassifier)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        text: str,
        *,
        user_id: Optional[str] = None,
        allowlisted_domains: Optional[Iterable[str]] = None,
    ) -> RouteDecision:
        """Run the full routing pipeline against ``text``.

        ``allowlisted_domains`` is an optional per-user filter applied
        on top of ``enabled_domains``. When the user is not on the
        allowlist for a beta/research domain the router treats it as
        disabled.
        """
        # Step 1: safety / out-of-scope.
        safety = run_safety_checks(text)
        if safety.kind == "prompt_injection":
            return RouteDecision(
                outcome="abstain",
                reason=safety.reason,
                routing_metadata={
                    "selected_via": "safety.prompt_injection",
                    "safety.matched_phrase": safety.matched_phrase,
                },
            )
        if safety.kind == "out_of_scope":
            return RouteDecision(
                outcome="abstain",
                reason=safety.reason,
                routing_metadata={
                    "selected_via": "safety.out_of_scope",
                    "safety.matched_phrase": safety.matched_phrase,
                },
            )
        if safety.kind == "cross_domain":
            return RouteDecision(
                outcome="abstain",
                reason=safety.reason,
                clarifier_text=(
                    "It looks like you're describing more than one matter. "
                    "Please pick the single issue you'd like help with first."
                ),
                routing_metadata={
                    "selected_via": "safety.cross_domain",
                    "safety.matched_phrase": safety.matched_phrase,
                },
            )

        # Step 2: figure out the candidate set the user can see.
        candidate_set = self._candidate_set(allowlisted_domains)
        if not candidate_set:
            return RouteDecision(
                outcome="unsupported",
                reason="no domains enabled for this caller",
                capture_in="log_only",
                routing_metadata={"selected_via": "no_enabled_domains"},
            )

        # If safety says the request is ambiguous (e.g. "what does the
        # law say?", "tell me about deposit law"), don't let an isolated
        # keyword match in ``rules.py`` silently route. Send to the
        # clarifier first.
        if safety.kind == "ambiguous":
            return self._build_clarifier(
                candidate_set,
                reason=safety.reason or "ambiguous request",
                selected_via="safety.ambiguous",
                extra_metadata={"safety.matched_phrase": safety.matched_phrase},
            )

        # Step 3: high-precision rules.
        rule_hit = self._rules.classify(text)
        if rule_hit.outcome == "route":
            return self._honour_rule_route(rule_hit, candidate_set)
        if rule_hit.outcome == "unsupported":
            return RouteDecision(
                outcome="unsupported",
                reason=rule_hit.reason,
                capture_in="research",
                routing_metadata={
                    "selected_via": "rule.unsupported",
                    "rule_id": rule_hit.rule_id,
                    "rule.matched_phrases": list(rule_hit.matched_phrases),
                },
            )

        # Step 4: LLM fallback.
        llm_result = self._llm.classify(text, enabled_domains=candidate_set)

        # Step 5: deterministic post-checks on the LLM output.
        post_check = self._post_check_llm(llm_result, candidate_set)
        if post_check is not None:
            return post_check

        # Step 6: clarifier if confidence / margin too low.
        if llm_result.confidence is None:
            llm_confidence = 0.0
        else:
            llm_confidence = float(llm_result.confidence)
        llm_margin = float(llm_result.margin or 0.0)
        if (
            llm_result.domain_id is None
            or llm_confidence < self._confidence_threshold
            or llm_margin < self._margin_threshold
        ):
            return self._build_clarifier(
                candidate_set,
                reason=(
                    f"low_confidence (conf={llm_confidence:.2f}, "
                    f"margin={llm_margin:.2f})"
                ),
                selected_via="llm.low_confidence",
                candidate_alternatives=list(llm_result.alternatives or ()),
                extra_metadata={
                    "llm.domain_id": llm_result.domain_id,
                    "llm.confidence": llm_confidence,
                    "llm.margin": llm_margin,
                },
            )

        return RouteDecision(
            outcome="route",
            domain_id=llm_result.domain_id,
            confidence=llm_confidence,
            margin=llm_margin,
            reason=llm_result.reason or "llm.routed",
            routing_metadata={
                "selected_via": "llm",
                "llm.confidence": llm_confidence,
                "llm.margin": llm_margin,
                "llm.alternatives": list(llm_result.alternatives or ()),
            },
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _candidate_set(
        self, allowlisted_domains: Optional[Iterable[str]]
    ) -> tuple[str, ...]:
        """Intersect ``enabled_domains`` with the per-user allowlist."""
        if allowlisted_domains is None:
            return self._enabled
        allow = set(allowlisted_domains)
        return tuple(d for d in self._enabled if d in allow)

    def _honour_rule_route(
        self, rule_hit: RuleHit, candidate_set: Sequence[str]
    ) -> RouteDecision:
        """Apply enabled-domain filter to a rule-routed decision."""
        domain_id = rule_hit.domain_id or ""
        if domain_id in candidate_set:
            return RouteDecision(
                outcome="route",
                domain_id=domain_id,
                confidence=1.0,
                margin=1.0,
                reason=rule_hit.reason,
                routing_metadata={
                    "selected_via": "rule",
                    "rule_id": rule_hit.rule_id,
                    "rule.matched_phrases": list(rule_hit.matched_phrases),
                },
            )
        # The rule pointed at a registered domain that this caller
        # cannot use. Treat as unsupported (research capture) so we keep
        # observability without crashing the request.
        return RouteDecision(
            outcome="unsupported",
            reason=(
                f"rule routed to {domain_id!r} but it is not enabled for "
                "this caller"
            ),
            capture_in="research",
            routing_metadata={
                "selected_via": "rule.disabled_target",
                "rule_id": rule_hit.rule_id,
                "rule.target_domain_id": domain_id,
            },
        )

    def _post_check_llm(
        self,
        llm_result: LLMClassification,
        candidate_set: Sequence[str],
    ) -> Optional[RouteDecision]:
        """Apply deterministic post-checks to LLM output.

        Returns a ready-to-go ``RouteDecision`` when the LLM output is
        unsafe (disabled domain, unknown id), else ``None`` to let the
        caller continue with confidence-bar checks.
        """
        if llm_result.domain_id is None:
            return None
        if llm_result.domain_id not in candidate_set:
            return RouteDecision(
                outcome="unsupported",
                reason=(
                    f"LLM proposed disabled domain {llm_result.domain_id!r}; "
                    "deterministic post-check rejected it"
                ),
                capture_in="research",
                routing_metadata={
                    "selected_via": "llm.post_check_rejected",
                    "llm.domain_id": llm_result.domain_id,
                    "llm.confidence": float(llm_result.confidence or 0.0),
                },
            )
        return None

    def _build_clarifier(
        self,
        candidate_set: Sequence[str],
        *,
        reason: str,
        selected_via: str,
        candidate_alternatives: Optional[list[str]] = None,
        extra_metadata: Optional[dict[str, Any]] = None,
    ) -> RouteDecision:
        candidates = (
            [c for c in candidate_alternatives if c in candidate_set]
            if candidate_alternatives
            else list(candidate_set)
        )
        if not candidates:
            candidates = list(candidate_set)
        labels = [matter_label_for(c) for c in candidates]
        if labels:
            joined = "; ".join(f"• {label}" for label in labels)
            clarifier = (
                "Could you tell me which of these matters you'd like help "
                f"with?\n{joined}"
            )
        else:
            clarifier = (
                "Could you tell me a bit more about your matter so I can help?"
            )
        meta: dict[str, Any] = {"selected_via": selected_via}
        if extra_metadata:
            meta.update(extra_metadata)
        return RouteDecision(
            outcome="clarify",
            clarifier_text=clarifier,
            candidate_domains=candidates,
            reason=reason,
            routing_metadata=meta,
        )


# ---------------------------------------------------------------------------
# Default factory used by the API
# ---------------------------------------------------------------------------


def build_default_router(
    enabled_domains: Iterable[str],
    *,
    llm_classifier: Optional[LLMClassifierClient] = None,
) -> DomainRouter:
    """Build a router suitable for the API's intake service.

    The default router uses the production rule tables and a
    :class:`NullLLMClassifier` until the structured-output adapter
    lands (TODO Phase 9.5).
    """
    return DomainRouter(
        enabled_domains=enabled_domains,
        rules=RuleSet(),
        llm_classifier=llm_classifier,
    )


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_MARGIN_THRESHOLD",
    "DomainRouter",
    "RouteDecision",
    "RouteOutcome",
    "USER_FACING_MATTER_LABELS",
    "build_default_router",
    "matter_label_for",
]
