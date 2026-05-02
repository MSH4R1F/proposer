"""SHA-20 Phase 7 — eval-time leakage controls.

Three classes of control live here:

1. **Target-source exclusion** — the document the gold case was derived
   from must NEVER be retrievable while predicting that case. Same for
   any explicit ``excluded_source_ids``.
2. **Temporal validity** — retrieved/cited authorities must satisfy
   ``cited_date <= gold.decision_date`` and (where set)
   ``effective_date <= gold.law_effective_date``.
3. **Namespace match + cross-domain guard** — the gold case's
   ``retrieval_namespace_id`` must match a namespace declared by the
   chosen domain. Cross-domain retrieval requires BOTH ``--cross-domain``
   AND ``--eval-only`` at the call site.

These controls are enforced before the prediction engine runs — they
shape the :class:`RetrievalFilterEnvelope` that the engine receives.

See ``docs/eval/leakage_controls.md`` for a human-readable summary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Iterable, List, Optional

from eval.schema import GoldCase

if TYPE_CHECKING:
    from domain_core.spec import DomainSpec
    from rag_engine.config import RetrievalFilterEnvelope


# ---------------------------------------------------------------------------
# Custom errors
# ---------------------------------------------------------------------------


class EvalLeakageError(RuntimeError):
    """Base class for eval-time leakage violations.

    Always fail-closed: if any leakage control would be skipped, the
    runner aborts the case rather than silently emitting a leaky result.
    """


class TargetSourceExclusionError(EvalLeakageError):
    """Raised when a retrieval result included the gold case's target
    source. Should be unreachable; a sanity check after retrieval."""


class TemporalLeakageError(EvalLeakageError):
    """Raised when a cited authority post-dates the gold case decision."""


class NamespaceMismatchError(EvalLeakageError):
    """Raised when the gold case's namespace_id is not declared by the
    selected domain spec."""


class CrossDomainEvalRefused(EvalLeakageError):
    """Raised when a cross-domain eval call lacks both ``--cross-domain``
    AND ``--eval-only``."""


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------


def build_eval_filter_envelope(
    gold_case: GoldCase,
    *,
    retrospective: bool = False,
    cross_domain: bool = False,
    eval_only: bool = True,
) -> "RetrievalFilterEnvelope":
    """Produce the strict eval-time :class:`RetrievalFilterEnvelope`.

    * ``excluded_source_ids = [target_source_id, *gold_case.excluded_source_ids]``
    * ``max_decision_date = gold_case.decision_date`` unless retrospective
    * ``as_of_date = gold_case.law_effective_date``
    * ``cross_domain_allowed = cross_domain`` (default False)
    * ``eval_only = True``

    The envelope's ``forum`` / ``source_kind`` / ``source_publisher`` /
    ``matter_type`` are set from the gold case when available.

    The envelope is unconditionally ``eval_only=True``: even with
    ``cross_domain=True``, eval cannot disable that flag. (If you want a
    production-style retrieval, run that path in production code paths,
    not in eval.)
    """
    # Lazy import to avoid module-load order issues.
    from rag_engine.config import RetrievalFilterEnvelope
    from domain_core.spec import Forum, SourceKind, SourcePublisher

    excluded: List[str] = []
    if gold_case.target_source_id:
        excluded.append(gold_case.target_source_id)
    for sid in gold_case.excluded_source_ids:
        if sid and sid not in excluded:
            excluded.append(sid)

    forum_enum: Optional[Forum] = None
    if gold_case.forum:
        try:
            forum_enum = Forum(gold_case.forum)
        except ValueError:
            forum_enum = None

    source_kind_enum: Optional[SourceKind] = None
    if gold_case.source_kind:
        try:
            source_kind_enum = SourceKind(gold_case.source_kind)
        except ValueError:
            source_kind_enum = None

    source_publisher_enum: Optional[SourcePublisher] = None
    if gold_case.source_publisher:
        try:
            source_publisher_enum = SourcePublisher(gold_case.source_publisher)
        except ValueError:
            source_publisher_enum = None

    return RetrievalFilterEnvelope(
        excluded_source_ids=excluded,
        max_decision_date=None if retrospective else gold_case.decision_date,
        as_of_date=gold_case.law_effective_date,
        forum=forum_enum,
        source_kind=source_kind_enum,
        source_publisher=source_publisher_enum,
        matter_type=gold_case.matter_type,
        cross_domain_allowed=bool(cross_domain),
        eval_only=True,
    )


# ---------------------------------------------------------------------------
# Per-control validators
# ---------------------------------------------------------------------------


@dataclass
class TemporalViolation:
    """A single temporal-leakage finding."""

    case_id: str
    authority_name: str
    authority_cited_date: date
    cutoff: date
    reason: str = "cited_date_after_decision_date"


def enforce_temporal_validity(
    citations: Iterable, gold_case: GoldCase, *, raise_on_violation: bool = True
) -> List[TemporalViolation]:
    """Validate that every cited authority pre-dates the gold decision.

    ``citations`` is any iterable of objects with ``.cited_date`` and
    ``.name`` attributes (the eval ``Authority`` shape) — duck typed so
    runtime structures like prediction payloads can also be passed.
    Returns the list of violations; raises :class:`TemporalLeakageError`
    by default if any are found.
    """
    cutoff = gold_case.decision_date
    violations: List[TemporalViolation] = []
    for cit in citations or []:
        cited = getattr(cit, "cited_date", None)
        if cited is None and isinstance(cit, dict):
            cited = cit.get("cited_date")
            if isinstance(cited, str):
                try:
                    cited = date.fromisoformat(cited)
                except ValueError:
                    cited = None
        if cited is None:
            continue
        if cited > cutoff:
            violations.append(
                TemporalViolation(
                    case_id=gold_case.case_id,
                    authority_name=getattr(cit, "name", None)
                    or (cit.get("name") if isinstance(cit, dict) else "unknown"),
                    authority_cited_date=cited,
                    cutoff=cutoff,
                )
            )
    if violations and raise_on_violation:
        v = violations[0]
        raise TemporalLeakageError(
            f"Temporal leakage in case {v.case_id!r}: cited authority "
            f"{v.authority_name!r} dated {v.authority_cited_date} "
            f"post-dates decision_date {v.cutoff}. "
            f"Total violations: {len(violations)}."
        )
    return violations


def enforce_namespace_match(domain_spec: "DomainSpec", gold_case: GoldCase) -> None:
    """Assert the gold case's ``retrieval_namespace_id`` is declared by
    the chosen domain spec.

    No-op when the gold case has no ``retrieval_namespace_id`` (legacy
    rows pre-domain). When set, the registry MUST contain a matching
    :class:`RetrievalNamespace`; otherwise raises
    :class:`NamespaceMismatchError`.
    """
    if not gold_case.retrieval_namespace_id:
        return
    declared = {ns.namespace_id for ns in domain_spec.retrieval_namespaces}
    if gold_case.retrieval_namespace_id not in declared:
        raise NamespaceMismatchError(
            f"Gold case {gold_case.case_id!r} declares "
            f"retrieval_namespace_id={gold_case.retrieval_namespace_id!r} "
            f"but domain {str(domain_spec.id)!r} declares only "
            f"{sorted(declared)}"
        )


@dataclass
class CrossDomainArgs:
    """Minimal contract for the args object passed to
    :func:`require_eval_only_for_cross_domain`. Tests can pass any
    dataclass / argparse Namespace with these attributes.
    """

    cross_domain: bool = False
    eval_only: bool = False


def require_eval_only_for_cross_domain(args) -> None:
    """Raise :class:`CrossDomainEvalRefused` unless the call set BOTH
    ``--cross-domain`` AND ``--eval-only``.

    Eval *always* runs eval_only; this guard exists so that a future
    code path that copies eval flags into runtime cannot accidentally
    disable the safeguard. The contract: cross-domain retrieval in eval
    requires the caller to acknowledge it explicitly with both flags.
    """
    cross = bool(getattr(args, "cross_domain", False))
    eval_only = bool(getattr(args, "eval_only", False))
    if cross and not eval_only:
        raise CrossDomainEvalRefused(
            "cross-domain eval requires --cross-domain AND --eval-only; "
            "got --cross-domain without --eval-only. Refusing."
        )
    if not cross and not eval_only:
        # Default eval mode: implicit eval_only=True is fine, but cross is off.
        return


# ---------------------------------------------------------------------------
# Post-retrieval verification
# ---------------------------------------------------------------------------


@dataclass
class TargetSourceLeakReport:
    case_id: str
    target_source_id: Optional[str]
    excluded_source_ids: List[str]
    leaked_source_ids: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.leaked_source_ids


def assert_no_target_source_in_results(
    results: Iterable, gold_case: GoldCase
) -> TargetSourceLeakReport:
    """After retrieval, sanity-check that the excluded source ids do
    not appear in the result set. Raises :class:`TargetSourceExclusionError`
    on violation; otherwise returns a clean report.
    """
    excluded = set(filter(None, [gold_case.target_source_id, *gold_case.excluded_source_ids]))
    leaked: List[str] = []
    for r in results or []:
        sid = (
            getattr(r, "source_id", None)
            or getattr(r, "case_reference", None)
            or (r.get("source_id") if isinstance(r, dict) else None)
            or (r.get("case_reference") if isinstance(r, dict) else None)
        )
        if sid and sid in excluded:
            leaked.append(sid)

    report = TargetSourceLeakReport(
        case_id=gold_case.case_id,
        target_source_id=gold_case.target_source_id,
        excluded_source_ids=list(gold_case.excluded_source_ids),
        leaked_source_ids=leaked,
    )
    if not report.is_clean:
        raise TargetSourceExclusionError(
            f"Target-source leak in case {gold_case.case_id!r}: retrieval "
            f"returned excluded sources {sorted(set(leaked))}. This is a "
            "bug in the retrieval filter pipeline; eval must abort."
        )
    return report


__all__ = [
    "EvalLeakageError",
    "TargetSourceExclusionError",
    "TemporalLeakageError",
    "NamespaceMismatchError",
    "CrossDomainEvalRefused",
    "TemporalViolation",
    "CrossDomainArgs",
    "TargetSourceLeakReport",
    "build_eval_filter_envelope",
    "enforce_temporal_validity",
    "enforce_namespace_match",
    "require_eval_only_for_cross_domain",
    "assert_no_target_source_in_results",
]
