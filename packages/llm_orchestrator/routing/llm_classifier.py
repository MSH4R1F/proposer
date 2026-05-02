"""SHA-20 Phase 9: LLM fallback classifier interface.

The deterministic rules in :mod:`rules` cover the bulk of high-signal
phrasings. When they don't fire we ask an LLM to pick a domain. This
module defines the *interface* the router uses; the production wiring
to a real Claude / OpenAI client lands later
(``# TODO Phase 9.5: structured output adapter``).

Design notes:

* The router never depends on a concrete LLM client. It depends on the
  :class:`LLMClassifierClient` ``Protocol`` so tests can pass a stub
  that returns deterministic ground-truth labels for evaluation.
* Confidence and margin are reported by the classifier; the router
  decides whether they clear the ``confidence >= 0.80, margin >= 0.15``
  bar.
* The classifier is allowed to return any domain id, but the router
  re-applies the enabled-domain + safety post-checks before honouring
  the answer.
* When no LLM client is configured the classifier returns
  ``LLMClassification(domain_id=None, confidence=0.0, margin=0.0)`` so
  the router falls through to the clarifier branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMClassification:
    """Result returned by an :class:`LLMClassifierClient`.

    * ``domain_id`` — the LLM's top choice, or ``None`` if it could not
      pick one (treated as ``clarify``).
    * ``confidence`` — softmax / self-reported probability of the top
      choice. ``0.0`` when unknown.
    * ``margin`` — gap between the top-1 and top-2 probabilities.
      ``0.0`` when unknown.
    * ``alternatives`` — ordered candidate domain ids the LLM also
      considered. Used to populate the clarifier UI.
    * ``reason`` — short human-readable rationale (logged only; never
      surfaced verbatim to end users).
    """

    domain_id: Optional[str]
    confidence: float = 0.0
    margin: float = 0.0
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClassifierClient(Protocol):
    """Pluggable LLM classifier.

    Implementations must be async-safe but the router calls
    :meth:`classify` synchronously to keep the routing path predictable.
    Production implementations should:

    * Restrict the candidate set to ``enabled_domains``. Disabled
      domains MUST NOT appear in the LLM's output.
    * Use structured output (JSON schema) so the router doesn't have to
      regex-parse free text.
    * Refuse to follow user instructions embedded in the message — the
      classifier prompt is always system-owned.

    The signature is intentionally tiny so a stub or a JSON-extraction
    fallback can be dropped in.
    """

    def classify(
        self,
        text: str,
        *,
        enabled_domains: Iterable[str],
    ) -> LLMClassification:  # pragma: no cover - protocol stub
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class NullLLMClassifier:
    """No-op classifier used when no LLM client is configured.

    Always returns ``domain_id=None`` so the router falls through to
    the clarifier branch. Keeps the production wiring trivially safe
    until the real client is plugged in (TODO Phase 9.5).
    """

    def classify(
        self,
        text: str,
        *,
        enabled_domains: Iterable[str],
    ) -> LLMClassification:
        del text, enabled_domains
        return LLMClassification(
            domain_id=None,
            confidence=0.0,
            margin=0.0,
            reason="no LLM classifier configured",
        )


__all__ = [
    "LLMClassification",
    "LLMClassifierClient",
    "NullLLMClassifier",
]
