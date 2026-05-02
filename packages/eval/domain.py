"""SHA-20 Phase 7 — per-domain helpers for the eval harness.

* :class:`DomainGoldFields` collects the optional per-domain fields on
  :class:`eval.schema.GoldCase` so adapters can read them in a typed way
  without re-implementing the optional-field dance everywhere.
* :func:`partition_by_domain` groups gold cases by ``domain_id`` so
  per-domain metrics can be rendered before macro aggregates.
* :func:`refuse_macro_if_unsafe` raises if any per-domain group is below
  ``min_case_count`` or fails citation/gate thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

from eval.schema import GoldCase

if TYPE_CHECKING:
    from datetime import date


_LEGACY_DOMAIN_ID = "housing.deposit.v1.legacy"


@dataclass(frozen=True)
class DomainGoldFields:
    """Typed view of the SHA-20 Phase 7 optional fields on a GoldCase.

    Reading these directly off the gold case works fine; the wrapper
    exists so that other modules can use a single contract instead of
    sprinkling ``getattr(gold, "domain_id", None)`` everywhere.
    """

    domain_id: Optional[str]
    forum: Optional[str]
    retrieval_namespace_id: Optional[str]
    target_source_id: Optional[str]
    excluded_source_ids: List[str]
    law_effective_date: Optional["date"]
    train_test_split: Optional[str]
    source_publisher: Optional[str]
    source_kind: Optional[str]
    corpus_version: Optional[str]
    matter_type: Optional[str]
    negative_kind: Optional[str]

    @classmethod
    def from_gold_case(cls, gold: GoldCase) -> "DomainGoldFields":
        return cls(
            domain_id=gold.domain_id,
            forum=gold.forum,
            retrieval_namespace_id=gold.retrieval_namespace_id,
            target_source_id=gold.target_source_id,
            excluded_source_ids=list(gold.excluded_source_ids),
            law_effective_date=gold.law_effective_date,
            train_test_split=gold.train_test_split,
            source_publisher=gold.source_publisher,
            source_kind=gold.source_kind,
            corpus_version=gold.corpus_version,
            matter_type=gold.matter_type,
            negative_kind=gold.negative_kind,
        )


def domain_id_or_legacy(gold: GoldCase) -> str:
    """Return the gold case's ``domain_id``, falling back to the legacy
    deposit domain marker for rows that pre-date Phase 7."""
    return gold.domain_id or _LEGACY_DOMAIN_ID


def partition_by_domain(cases: List[GoldCase]) -> Dict[str, List[GoldCase]]:
    """Group gold cases by ``domain_id`` (legacy rows under the legacy
    marker). The dict insertion order matches the order cases are listed
    so the report is reproducible."""
    out: Dict[str, List[GoldCase]] = {}
    for c in cases:
        key = domain_id_or_legacy(c)
        out.setdefault(key, []).append(c)
    return out


@dataclass
class MacroAggregateRefusal:
    """Why we refused to render macro metrics."""

    refused_for: List[str] = field(default_factory=list)
    reasons: Dict[str, str] = field(default_factory=dict)

    @property
    def is_refused(self) -> bool:
        return bool(self.refused_for)


class MacroAggregateNotSafe(RuntimeError):
    """Raised when macro aggregation would mask a per-domain gate failure."""


def refuse_macro_if_unsafe(
    per_domain_metrics: Dict[str, Dict[str, float]],
    *,
    min_case_count: int,
    cases_per_domain: Dict[str, int],
    min_citation_validity: float = 0.98,
    max_hallucination_rate: float = 0.02,
) -> None:
    """Raise :class:`MacroAggregateNotSafe` if any per-domain group is below
    ``min_case_count`` or fails citation/hallucination thresholds.

    The eval CLI MUST render per-domain metrics before macro and skip the
    macro aggregate when this check fails.
    """
    refusal = MacroAggregateRefusal()
    for dom, metrics in per_domain_metrics.items():
        n = cases_per_domain.get(dom, 0)
        if n < min_case_count:
            refusal.refused_for.append(dom)
            refusal.reasons[dom] = f"n_cases={n} below min_case_count={min_case_count}"
            continue
        cv = metrics.get("citation_validity")
        if cv is not None and cv < min_citation_validity:
            refusal.refused_for.append(dom)
            refusal.reasons[dom] = (
                f"citation_validity={cv} below floor {min_citation_validity}"
            )
            continue
        h = metrics.get("hallucination_rate")
        if h is not None and h > max_hallucination_rate:
            refusal.refused_for.append(dom)
            refusal.reasons[dom] = (
                f"hallucination_rate={h} above ceiling {max_hallucination_rate}"
            )
    if refusal.is_refused:
        raise MacroAggregateNotSafe(
            f"refusing to render macro aggregate; per-domain failures: "
            f"{refusal.reasons}"
        )


__all__ = [
    "DomainGoldFields",
    "domain_id_or_legacy",
    "partition_by_domain",
    "refuse_macro_if_unsafe",
    "MacroAggregateNotSafe",
    "MacroAggregateRefusal",
]
