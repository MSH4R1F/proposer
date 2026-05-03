"""Lookup Protocols + in-memory test stubs for the Phase 8 auto-grounder.

Two narrowly-typed Protocols, one per check site:

* :class:`AuthorityLookup` — verifies that ``cited_authorities[i]`` resolves
  to a known case in the curated authorities index. Verdicts:
  ``"KNOWN" | "UNKNOWN" | "AMBIGUOUS"``.
* :class:`StatuteLookup` — verifies that ``statutory_basis[i]`` resolves to
  a known section in the curated UK statutes index. Verdicts:
  ``"KNOWN" | "UNKNOWN" | "WRONG_SECTION"``.

Each Protocol is ``@runtime_checkable`` so the grounder (and downstream
runner) can ``isinstance``-guard against accidental wiring of a wrong-shape
backend.

Both Protocols also expose ``index_id`` (a stable string the runner copies
into ``LabelingProvenance.{authority,statute}_index_id``) and
``index_hash`` (a 64-char sha256 hex of a deterministic serialisation of
the underlying table, copied into the matching ``..._index_hash`` field)
so a labeling decision can be replayed against the exact index revision
that produced it.

Submodules export the concrete in-memory stubs used by the test suite:

* :class:`eval.auto_label.lookups.authorities.InMemoryAuthorityStub`
* :class:`eval.auto_label.lookups.statutes.InMemoryStatuteStub`
"""
from __future__ import annotations

__all__: list[str] = []
