"""Bucketed similarity helpers for factor-overlap scoring (Task 5.2).

Pure functions used by the comparator pass (FactorRetriever, Task 5.3) to
score candidate cases against the asserted factors of a query case. All
public helpers return floats in [0, 1].

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §9.2.1

Bucket semantics
----------------
For money / duration, ``edges`` is a strictly increasing list ``[e0, e1,
..., e_{n-1}]`` defining ``n`` buckets:
  - bucket ``i`` for ``0 <= i < n-1``  ->  ``[edges[i], edges[i+1])``
  - bucket ``n-1``                      ->  ``[edges[-1], inf)`` (open-ended top)

Values strictly below ``edges[0]`` are clamped to bucket 0 (the simplest
interpretation; the housing pack's lowest edge is 0 anyway, so this only
matters for negative inputs that should never occur).

Same-bucket pairs return 1.0, adjacent-bucket pairs return 0.5, all others
return 0.0 — per spec §9.2.1.
"""

from __future__ import annotations

from datetime import date as _date
from typing import List

from legal_core.graph.factor_assertion import FactorAssertion
from legal_core.graph.factor_value import FactorValueType

from domain_packs.loaders import BucketDefinitions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bucket_index_for(value: int, edges: List[int]) -> int:
    """Return the bucket index for ``value`` given strictly-increasing ``edges``.

    Buckets are half-open intervals ``[edges[i], edges[i+1])`` for
    ``0 <= i < len(edges)-1``, and ``[edges[-1], +inf)`` for the final
    bucket. Values below ``edges[0]`` are clamped to bucket 0.
    """
    if value >= edges[-1]:
        return len(edges) - 1
    # Linear scan is fine here — edges are tiny (5–6 entries).
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return i
    # value < edges[0]: clamp to bucket 0.
    return 0


def _bucketed_similarity(a: int, b: int, edges: List[int]) -> float:
    """Same bucket -> 1.0, adjacent -> 0.5, else 0.0."""
    ia = _bucket_index_for(a, edges)
    ib = _bucket_index_for(b, edges)
    diff = abs(ia - ib)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.5
    return 0.0


# ---------------------------------------------------------------------------
# Public per-type helpers
# ---------------------------------------------------------------------------


def money_similarity(a_pence: int, b_pence: int, edges: List[int]) -> float:
    """Bucketed similarity for monetary amounts in GBP minor units (pence).

    Same bucket -> 1.0; adjacent bucket -> 0.5; otherwise 0.0. ``edges``
    are the strictly increasing bucket boundaries from
    ``BucketDefinitions.money.bucket_edges_pence``.
    """
    return _bucketed_similarity(a_pence, b_pence, edges)


def duration_similarity(a_days: int, b_days: int, edges: List[int]) -> float:
    """Bucketed similarity for durations measured in days.

    Same conventions as ``money_similarity``. ``edges`` come from
    ``BucketDefinitions.duration.bucket_edges_days``.
    """
    return _bucketed_similarity(a_days, b_days, edges)


def date_similarity(
    a: _date,
    b: _date,
    *,
    same_year: float,
    same_month: float,
    other: float,
) -> float:
    """Granularity-based date similarity (per spec §9.2.1).

    - Same year+month  -> ``same_month``
    - Same year only   -> ``same_year``
    - Different year   -> ``other``

    Caller must pass the per-pack scores from
    ``RetrievalProfile.bucket_definitions.date``.
    """
    if a.year == b.year:
        if a.month == b.month:
            return same_month
        return same_year
    return other


def boolean_similarity(a: bool, b: bool) -> float:
    """1.0 iff ``a == b``, else 0.0."""
    return 1.0 if a == b else 0.0


def enum_similarity(a: str, b: str) -> float:
    """1.0 iff ``a == b`` (case-sensitive), else 0.0.

    Per spec §9.2.1: equality only — no semantic similarity.
    """
    return 1.0 if a == b else 0.0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def factor_overlap(
    a: FactorAssertion,
    b: FactorAssertion,
    bucket_definitions: BucketDefinitions,
) -> float:
    """Per-spec §9.2.1 dispatch on ``a.value_type``.

    Returns 0.0 if the two assertions have different ``value_type``s
    (cross-type comparison is undefined). Otherwise returns the
    appropriate per-type similarity in [0, 1].
    """
    if a.value_type != b.value_type:
        return 0.0

    vt = a.value_type

    if vt is FactorValueType.BOOLEAN:
        return boolean_similarity(bool(a.value.boolean), bool(b.value.boolean))

    if vt is FactorValueType.ENUM:
        return enum_similarity(a.value.enum or "", b.value.enum or "")

    if vt is FactorValueType.NUMBER:
        # Spec §9.2.1 only specifies bucketing for money/duration and
        # equality for enum. Treat raw numbers as equality (string repr)
        # to avoid float-drift surprises; if a domain pack later wants
        # bucketed numerics it should declare a NUMBER bucket strategy.
        return enum_similarity(str(a.value.number), str(b.value.number))

    if vt is FactorValueType.MONEY:
        return money_similarity(
            a.value.money_minor_units or 0,
            b.value.money_minor_units or 0,
            bucket_definitions.money.bucket_edges_pence,
        )

    if vt is FactorValueType.DATE:
        # Both dates are guaranteed non-None by FactorValue's validator
        # whenever value_type=DATE, but mypy doesn't know that.
        a_date = a.value.date
        b_date = b.value.date
        if a_date is None or b_date is None:
            return 0.0
        return date_similarity(
            a_date,
            b_date,
            same_year=bucket_definitions.date.same_year_score,
            same_month=bucket_definitions.date.same_month_score,
            other=bucket_definitions.date.other_score,
        )

    if vt is FactorValueType.DURATION:
        return duration_similarity(
            a.value.duration_days or 0,
            b.value.duration_days or 0,
            bucket_definitions.duration.bucket_edges_days,
        )

    # Defensive: unknown value_type. FactorValueType is closed, so this
    # is unreachable today, but a future enum addition would land here.
    return 0.0
