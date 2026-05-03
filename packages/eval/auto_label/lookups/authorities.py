"""Authority-index lookup Protocol + in-memory test stub.

The auto-grounder calls ``AuthorityLookup.lookup(name=..., cited_date=...)``
to decide whether an LLM-emitted ``Authority`` row maps to a known case in
the project's curated authorities index.

Verdict semantics
-----------------
* ``"KNOWN"`` — the (canonicalised name, ISO date) pair resolves to exactly
  one entry in the index.
* ``"UNKNOWN"`` — no entry matches; the grounder fails the cell.
* ``"AMBIGUOUS"`` — multiple entries match (e.g. several "Smith v Jones"
  decisions on the same date); the grounder fails the cell to force a
  human decision.

The grounder treats both UNKNOWN and AMBIGUOUS as UNGROUNDED, with
distinct reason strings so reviewers can tell a missing-from-index case
from a needs-disambiguation case.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal, Protocol, Tuple, runtime_checkable

from eval.auto_label.canonicalize import canonicalize_text


AuthorityVerdict = Literal["KNOWN", "UNKNOWN", "AMBIGUOUS"]


@runtime_checkable
class AuthorityLookup(Protocol):
    """Contract every authority-index backend must satisfy.

    ``index_id`` is a stable identifier (e.g. ``"bailii-housing-2026-04"``)
    copied into ``LabelingProvenance.authority_index_id``. ``index_hash``
    is a 64-char sha256 hex of a deterministic serialisation of the
    backing table, copied into ``LabelingProvenance.authority_index_hash``
    so a labeling decision can be replayed against the exact index
    revision that produced it.
    """

    index_id: str
    index_hash: str

    def lookup(self, *, name: str, cited_date: date) -> AuthorityVerdict: ...


def _canonical_key(name: str, cited_date: date) -> Tuple[str, str]:
    """Normalise a ``(name, cited_date)`` lookup key.

    Names are canonicalised + lower-cased; dates are stringified to ISO
    ``YYYY-MM-DD`` form for stable equality across ``date`` instances and
    JSON-roundtrip serialisations.
    """
    return (canonicalize_text(name or "").lower(), cited_date.isoformat())


@dataclass
class InMemoryAuthorityStub:
    """In-memory ``AuthorityLookup`` for tests.

    Two construction styles, both supported simultaneously so callers can
    pick the form that matches their test data:

        InMemoryAuthorityStub(
            entries={("howard de walden estates ltd", "2008-06-25"): "KNOWN"},
        )

        InMemoryAuthorityStub(
            known_pairs=[("Howard de Walden v Aggio", date(2008, 6, 26))],
            ambiguous_pairs=[("Smith v Jones", date(2010, 5, 1))],
        )

    Pairs not listed default to ``UNKNOWN``.
    """

    entries: dict[Tuple[str, str], AuthorityVerdict] = field(default_factory=dict)
    known_pairs: Iterable[Tuple[str, date]] = field(default_factory=list)
    ambiguous_pairs: Iterable[Tuple[str, date]] = field(default_factory=list)
    index_id: str = "auth-stub-v1"
    index_hash: str = field(init=False)
    _entries: dict[Tuple[str, str], AuthorityVerdict] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._entries = {}
        # `entries` keys are (canonical-already, "YYYY-MM-DD") per the lookup
        # tests' contract; canonicalise defensively in case a caller hands
        # raw strings.
        for (name, iso_date), verdict in self.entries.items():
            self._entries[(canonicalize_text(name or "").lower(), iso_date)] = verdict
        for name, cited in self.known_pairs:
            self._entries[_canonical_key(name, cited)] = "KNOWN"
        for name, cited in self.ambiguous_pairs:
            # Ambiguous wins over known if both listed (defensive for tests).
            self._entries[_canonical_key(name, cited)] = "AMBIGUOUS"
        self.index_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            sorted(
                ([k[0], k[1], v] for k, v in self._entries.items()),
                key=lambda r: (r[0], r[1]),
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def lookup(self, *, name: str, cited_date: date) -> AuthorityVerdict:
        return self._entries.get(_canonical_key(name, cited_date), "UNKNOWN")


# Backwards-compat alias — the grounder test file imports the longer name.
InMemoryAuthorityLookup = InMemoryAuthorityStub


__all__ = [
    "AuthorityLookup",
    "AuthorityVerdict",
    "InMemoryAuthorityLookup",
    "InMemoryAuthorityStub",
]
