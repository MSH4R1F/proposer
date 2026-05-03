"""Statute-index lookup Protocol + in-memory test stub.

The grounder calls ``StatuteLookup.lookup(statute=..., section=...)`` per
``StatutoryReference``. Verdicts:

* ``"KNOWN"``         — statute name resolves AND section is in its
                        section table.
* ``"UNKNOWN"``       — statute name does not resolve at all (e.g.
                        invented or misspelled).
* ``"WRONG_SECTION"`` — statute resolves but the section either fails the
                        ``s.\\d+[A-Z]?`` regex or is not in the statute's
                        section table.

WRONG_SECTION is distinct from UNKNOWN so reviewers can tell a fabricated
Act from a real Act with a wrong section number.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol, Set, runtime_checkable

from eval.auto_label.canonicalize import canonicalize_text


StatuteVerdict = Literal["KNOWN", "UNKNOWN", "WRONG_SECTION"]


# Section format: ``s.<digits>[<single uppercase letter>]`` after lower-casing.
# Matches s.213, s.213A (real Housing Act 2004 inserted section), etc.
_SECTION_RE = re.compile(r"^s\.\d+[a-z]?$")


@runtime_checkable
class StatuteLookup(Protocol):
    """Contract every statute-index backend must satisfy."""

    index_id: str
    index_hash: str

    def lookup(self, *, statute: str, section: str) -> StatuteVerdict: ...


def _canonical_statute(statute: str) -> str:
    return canonicalize_text(statute or "").lower()


def _canonical_section(section: str) -> str:
    return canonicalize_text(section or "").lower()


@dataclass
class InMemoryStatuteStub:
    """In-memory ``StatuteLookup`` implementation for tests.

    ``statutes`` maps a canonicalised statute name (lower-cased) to the set
    of canonicalised section strings it admits, e.g.::

        InMemoryStatuteStub(statutes={"housing act 2004": {"s.213", "s.214"}})

    The ``lookup`` method canonicalises both inputs before hitting the
    table. A section that fails ``_SECTION_RE`` after canonicalisation
    returns ``WRONG_SECTION`` — this catches forms like ``"Section 213"``
    that don't follow the ``s.<n>`` pattern.
    """

    statutes: Mapping[str, Set[str]] = field(default_factory=dict)
    index_id: str = "statute-stub-v1"
    index_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.index_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {k: sorted(v) for k, v in sorted(self.statutes.items())},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def lookup(self, *, statute: str, section: str) -> StatuteVerdict:
        canon_statute = _canonical_statute(statute)
        canon_section = _canonical_section(section)
        sections = self.statutes.get(canon_statute)
        if sections is None:
            return "UNKNOWN"
        if not _SECTION_RE.match(canon_section):
            return "WRONG_SECTION"
        if canon_section not in sections:
            return "WRONG_SECTION"
        return "KNOWN"


__all__ = ["StatuteLookup", "StatuteVerdict", "InMemoryStatuteStub"]
