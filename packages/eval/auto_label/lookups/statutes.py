"""Statute-index lookup Protocol + in-memory test stub.

The grounder calls ``StatuteLookup.lookup(statute=..., section=...)`` per
``StatutoryReference``. Verdicts:

* ``"KNOWN"``         — statute name resolves AND section is in its
                        section table.
* ``"UNKNOWN"``       — statute name does not resolve at all.
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
from typing import Iterable, Literal, Mapping, Protocol, Set, Tuple, runtime_checkable

from eval.auto_label.canonicalize import canonicalize_text


StatuteVerdict = Literal["KNOWN", "UNKNOWN", "WRONG_SECTION"]


# Section format: ``s.<digits>[<single uppercase letter>]`` after lower-casing.
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
    """In-memory ``StatuteLookup`` for tests.

    Two construction styles, both supported simultaneously:

        InMemoryStatuteStub(statutes={"housing act 2004": {"s.213", "s.214"}})

        InMemoryStatuteStub(known_pairs=[("Housing Act 2004", "s.213")])

    Pairs not listed default to ``UNKNOWN``. A statute that resolves but
    is queried with a section not in its set returns ``WRONG_SECTION``.
    """

    statutes: Mapping[str, Set[str]] = field(default_factory=dict)
    known_pairs: Iterable[Tuple[str, str]] = field(default_factory=list)
    index_id: str = "statute-stub-v1"
    index_hash: str = field(init=False)
    _statutes: dict[str, set[str]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._statutes = {}
        # `statutes` keys are pre-canonicalised (per the lookup tests);
        # canonicalise defensively in case a caller hands a raw name.
        for raw_name, sections in self.statutes.items():
            key = _canonical_statute(raw_name)
            self._statutes.setdefault(key, set()).update(
                _canonical_section(s) for s in sections
            )
        for statute, section in self.known_pairs:
            key = _canonical_statute(statute)
            self._statutes.setdefault(key, set()).add(_canonical_section(section))
        self.index_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {k: sorted(v) for k, v in sorted(self._statutes.items())},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def lookup(self, *, statute: str, section: str) -> StatuteVerdict:
        canon_statute = _canonical_statute(statute)
        canon_section = _canonical_section(section)
        sections = self._statutes.get(canon_statute)
        if sections is None:
            return "UNKNOWN"
        if not _SECTION_RE.match(canon_section):
            return "WRONG_SECTION"
        if canon_section not in sections:
            return "WRONG_SECTION"
        return "KNOWN"


# Backwards-compat alias — the grounder test file imports the longer name.
InMemoryStatuteLookup = InMemoryStatuteStub


__all__ = [
    "StatuteLookup",
    "StatuteVerdict",
    "InMemoryStatuteLookup",
    "InMemoryStatuteStub",
]
