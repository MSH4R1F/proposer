"""Phase 8 — Authority/Statute lookup Protocol + in-memory stubs.

Tests pin the exact contract the grounder consumes:

* ``AuthorityLookup`` Protocol with ``KNOWN``/``UNKNOWN``/``AMBIGUOUS`` verdicts.
* ``StatuteLookup`` Protocol with ``KNOWN``/``UNKNOWN``/``WRONG_SECTION`` verdicts.
* In-memory stubs canonicalise the lookup key so casing/whitespace drift
  doesn't drop a known entry into UNKNOWN.
* Both stubs expose ``index_id`` (stable string) and ``index_hash`` (sha256
  hex) for ``LabelingProvenance.authority_index_hash`` /
  ``LabelingProvenance.statute_index_hash``.
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from eval.auto_label.lookups.authorities import (
    AuthorityLookup,
    AuthorityVerdict,
    InMemoryAuthorityStub,
)
from eval.auto_label.lookups.statutes import (
    InMemoryStatuteStub,
    StatuteLookup,
    StatuteVerdict,
)


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Authority lookup
# ---------------------------------------------------------------------------


class TestAuthorityLookup:
    def test_known_entry_returns_known(self):
        stub = InMemoryAuthorityStub(
            entries={
                ("howard de walden estates ltd", "2008-06-25"): "KNOWN",
            },
        )
        assert stub.lookup(
            name="Howard de Walden Estates Ltd",
            cited_date=date(2008, 6, 25),
        ) == "KNOWN"

    def test_missing_entry_returns_unknown(self):
        stub = InMemoryAuthorityStub(entries={})
        assert stub.lookup(
            name="Some Made-Up Case",
            cited_date=date(2010, 1, 1),
        ) == "UNKNOWN"

    def test_ambiguous_entry_returns_ambiguous(self):
        stub = InMemoryAuthorityStub(
            entries={
                ("smith v jones", "2015-03-04"): "AMBIGUOUS",
            },
        )
        assert stub.lookup(
            name="Smith v Jones",
            cited_date=date(2015, 3, 4),
        ) == "AMBIGUOUS"

    def test_canonicalisation_collapses_whitespace_and_casing(self):
        stub = InMemoryAuthorityStub(
            entries={
                ("howard de walden estates ltd", "2008-06-25"): "KNOWN",
            },
        )
        # Same canonical form via casing + double-spacing.
        assert stub.lookup(
            name="Howard de Walden Estates Ltd",
            cited_date=date(2008, 6, 25),
        ) == "KNOWN"
        assert stub.lookup(
            name="howard  de walden  estates ltd",
            cited_date=date(2008, 6, 25),
        ) == "KNOWN"

    def test_index_id_and_hash_exposed(self):
        stub = InMemoryAuthorityStub(
            entries={
                ("a v b", "2020-01-01"): "KNOWN",
            },
            index_id="auth-stub-v1",
        )
        assert stub.index_id == "auth-stub-v1"
        assert _HEX64.match(stub.index_hash), stub.index_hash

    def test_index_hash_stable_for_same_dict(self):
        a = InMemoryAuthorityStub(entries={("x", "2020-01-01"): "KNOWN"})
        b = InMemoryAuthorityStub(entries={("x", "2020-01-01"): "KNOWN"})
        assert a.index_hash == b.index_hash

    def test_index_hash_differs_for_different_dict(self):
        a = InMemoryAuthorityStub(entries={("x", "2020-01-01"): "KNOWN"})
        b = InMemoryAuthorityStub(entries={("y", "2020-01-01"): "KNOWN"})
        assert a.index_hash != b.index_hash

    def test_protocol_runtime_checkable(self):
        stub = InMemoryAuthorityStub(entries={})
        assert isinstance(stub, AuthorityLookup)

    def test_verdict_literal_values(self):
        # AuthorityVerdict is a Literal["KNOWN", "UNKNOWN", "AMBIGUOUS"];
        # we can't introspect Literal at runtime cleanly across Pythons,
        # but we can assert the stub returns one of these three strings.
        stub = InMemoryAuthorityStub(entries={("x", "2020-01-01"): "KNOWN"})
        assert stub.lookup(name="x", cited_date=date(2020, 1, 1)) in (
            "KNOWN",
            "UNKNOWN",
            "AMBIGUOUS",
        )


# ---------------------------------------------------------------------------
# Statute lookup
# ---------------------------------------------------------------------------


class TestStatuteLookup:
    def test_known_section_returns_known(self):
        stub = InMemoryStatuteStub(
            statutes={
                "housing act 2004": {"s.213", "s.214"},
            },
        )
        assert stub.lookup(statute="Housing Act 2004", section="s.213") == "KNOWN"

    def test_unknown_statute_returns_unknown(self):
        stub = InMemoryStatuteStub(
            statutes={
                "housing act 2004": {"s.213"},
            },
        )
        assert stub.lookup(statute="Made-up Act 2099", section="s.1") == "UNKNOWN"

    def test_known_statute_unknown_section_returns_wrong_section(self):
        stub = InMemoryStatuteStub(
            statutes={
                "housing act 2004": {"s.213", "s.214"},
            },
        )
        assert stub.lookup(
            statute="Housing Act 2004",
            section="s.999",
        ) == "WRONG_SECTION"

    def test_section_failing_regex_returns_wrong_section(self):
        stub = InMemoryStatuteStub(
            statutes={
                "housing act 2004": {"s.213"},
            },
        )
        # "Section 213" does not match r"s\.\d+[A-Z]?" after canonicalisation.
        assert stub.lookup(
            statute="Housing Act 2004",
            section="Section 213",
        ) == "WRONG_SECTION"

    def test_canonicalised_statute_name(self):
        stub = InMemoryStatuteStub(
            statutes={"housing act 2004": {"s.213"}},
        )
        assert stub.lookup(
            statute="Housing  Act 2004",
            section="s.213",
        ) == "KNOWN"

    def test_index_id_and_hash_exposed(self):
        stub = InMemoryStatuteStub(
            statutes={"housing act 2004": {"s.213"}},
            index_id="stat-stub-v1",
        )
        assert stub.index_id == "stat-stub-v1"
        assert _HEX64.match(stub.index_hash), stub.index_hash

    def test_index_hash_stable_for_same_table(self):
        a = InMemoryStatuteStub(statutes={"x": {"s.1"}})
        b = InMemoryStatuteStub(statutes={"x": {"s.1"}})
        assert a.index_hash == b.index_hash

    def test_index_hash_differs_for_different_table(self):
        a = InMemoryStatuteStub(statutes={"x": {"s.1"}})
        b = InMemoryStatuteStub(statutes={"x": {"s.2"}})
        assert a.index_hash != b.index_hash

    def test_protocol_runtime_checkable(self):
        stub = InMemoryStatuteStub(statutes={})
        assert isinstance(stub, StatuteLookup)

    def test_section_letter_suffix_accepted(self):
        # "s.213A" is a real form (e.g. Housing Act 2004 inserted sections).
        stub = InMemoryStatuteStub(
            statutes={"housing act 2004": {"s.213a"}},
        )
        assert stub.lookup(
            statute="Housing Act 2004",
            section="s.213A",
        ) == "KNOWN"


@pytest.mark.parametrize(
    "verdict",
    ["KNOWN", "UNKNOWN", "AMBIGUOUS"],
)
def test_authority_verdict_literal_values(verdict: AuthorityVerdict):
    # Compile-time / runtime assertion that the literal type accepts these.
    v: AuthorityVerdict = verdict  # noqa: F841 - type-check sentinel
    assert verdict in ("KNOWN", "UNKNOWN", "AMBIGUOUS")


@pytest.mark.parametrize(
    "verdict",
    ["KNOWN", "UNKNOWN", "WRONG_SECTION"],
)
def test_statute_verdict_literal_values(verdict: StatuteVerdict):
    v: StatuteVerdict = verdict  # noqa: F841
    assert verdict in ("KNOWN", "UNKNOWN", "WRONG_SECTION")
