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
from typing import Literal, Protocol, runtime_checkable

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


def _canonical_key(name: str, cited_date: date) -> tuple[str, str]:
    """Normalise a ``(name, cited_date)`` lookup key.

    Names are canonicalised + lower-cased so casing/curly-quote/whitespace
    drift cannot drop a known authority into UNKNOWN. Dates are stringified
    to ISO ``YYYY-MM-DD`` form for stable equality across ``date``
    instances and JSON-roundtrip serialisations.
    """
    return (canonicalize_text(name or "").lower(), cited_date.isoformat())


@dataclass
class InMemoryAuthorityStub:
    """In-memory ``AuthorityLookup`` implementation for tests.

    ``entries`` maps ``(canonical_name, iso_date_str)`` to a verdict
    string. The keys MUST be already canonicalised (lower-cased,
    whitespace-collapsed); the constructor does not re-canonicalise the
    incoming keys so test setup remains explicit. The ``lookup`` method
    canonicalises the *query* before hitting the table, matching how the
    grounder will pass un-normalised LLM output.

    A query that lands on no entry returns ``"UNKNOWN"`` — entries default
    to absent, not to KNOWN.
    """

    entries: dict[tuple[str, str], AuthorityVerdict] = field(default_factory=dict)
    index_id: str = "auth-stub-v1"
    index_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.index_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        # Sort keys for deterministic serialisation. tuple keys are
        # serialised as JSON arrays of [name, iso_date] pairs.
        payload = json.dumps(
            sorted(
                ([k[0], k[1], v] for k, v in self.entries.items()),
                key=lambda r: (r[0], r[1]),
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def lookup(self, *, name: str, cited_date: date) -> AuthorityVerdict:
        key = _canonical_key(name, cited_date)
        return self.entries.get(key, "UNKNOWN")


__all__ = ["AuthorityLookup", "AuthorityVerdict", "InMemoryAuthorityStub"]
