"""Tests for housing.deposit.v1 factor card renderer.

Per Stream C plan PR 4 Task 4.2:
- The renderer must be byte-equivalent to the legacy
  IssuePredictor._format_kg_fact_card output for every input shape.
- The renderer is invoked via DomainPack.render_factor_card().

Spec: docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md §19 PR 4
"""

from __future__ import annotations

import pytest

from domain_packs.registry import get_domain_pack


# ---------------------------------------------------------------------------
# Fixture helpers — KGFacts is in llm_orchestrator; importing it inside tests
# is fine (test files are not part of the leaf-package boundary check).
# ---------------------------------------------------------------------------


@pytest.fixture
def pack():
    return get_domain_pack("housing.deposit.v1")


def _kg_facts(**kwargs):
    """Build a KGFacts instance — imported lazily to keep the suite skippable
    if llm_orchestrator is unavailable (it is required, but lazy is cleaner)."""
    from llm_orchestrator.pipeline.kg_facts import KGFacts

    return KGFacts(**kwargs)


def _legacy_format(facts):
    from llm_orchestrator.pipeline.issue_predictor import IssuePredictor

    return IssuePredictor._format_kg_fact_card(facts)


# ---------------------------------------------------------------------------
# 1. Renderer module loads via the pack.
# ---------------------------------------------------------------------------


def test_renderer_loads_via_pack(pack):
    """The DomainPack.render_factor_card method should resolve the deposit
    renderer module without raising."""
    facts = _kg_facts()
    # Even an all-unknown call must not raise — empty string is OK.
    out = pack.render_factor_card(facts)
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# 2. Empty / abstaining inputs return the empty string.
# ---------------------------------------------------------------------------


def test_renderer_returns_empty_for_all_unknown(pack):
    """All-unknown KGFacts -> "" (no card rendered)."""
    out = pack.render_factor_card(_kg_facts())
    assert out == ""


def test_renderer_returns_empty_for_none(pack):
    """case_graph=None -> "" (matches legacy guard)."""
    out = pack.render_factor_card(None)
    assert out == ""


# ---------------------------------------------------------------------------
# 3. Per-factor rendering tests.
# ---------------------------------------------------------------------------


def test_renderer_renders_late_protection_with_days(pack):
    """protected_late + scheme + days renders all three pieces of info."""
    facts = _kg_facts(
        deposit_protection_status="protected_late",
        deposit_scheme="DPS",
        deposit_late_by_days=90,
    )
    out = pack.render_factor_card(facts)
    assert "KEY KG FACTS" in out
    assert "deposit_protection_status: protected_late" in out
    assert "DPS" in out
    assert "90" in out


def test_renderer_renders_not_protected(pack):
    """not_protected omits scheme/late suffix."""
    facts = _kg_facts(deposit_protection_status="not_protected")
    out = pack.render_factor_card(facts)
    assert "deposit_protection_status: not_protected" in out
    assert "scheme:" not in out
    assert "late by" not in out


def test_renderer_renders_prescribed_info_late(pack):
    """provided_late + days adds the day count suffix."""
    facts = _kg_facts(
        prescribed_information_status="provided_late",
        prescribed_late_by_days=45,
    )
    out = pack.render_factor_card(facts)
    assert "prescribed_information_status: provided_late" in out
    assert "45" in out


def test_renderer_renders_inventory_absent(pack):
    """check_in_inventory_baseline=absent renders without scheme/days noise."""
    facts = _kg_facts(check_in_inventory_baseline="absent")
    out = pack.render_factor_card(facts)
    assert "check_in_inventory_baseline: absent" in out


# ---------------------------------------------------------------------------
# 4. Byte-equivalence with the legacy IssuePredictor._format_kg_fact_card.
# ---------------------------------------------------------------------------


def test_renderer_byte_equivalent_to_legacy_format(pack):
    """For every realistic input, pack.render_factor_card(facts) must produce
    the exact same bytes as IssuePredictor._format_kg_fact_card(facts).

    Hard Constraint #6: deposit regression suite is preserved by byte-identical
    rendering.
    """
    test_cases = [
        # 1. All-unknown — both return "".
        _kg_facts(),
        # 2. not_protected only.
        _kg_facts(deposit_protection_status="not_protected"),
        # 3. protected_late + scheme + days.
        _kg_facts(
            deposit_protection_status="protected_late",
            deposit_scheme="DPS",
            deposit_late_by_days=90,
        ),
        # 4. All three factors set with various sub-fields.
        _kg_facts(
            deposit_protection_status="protected_late",
            deposit_scheme="MyDeposits",
            deposit_late_by_days=14,
            prescribed_information_status="provided_late",
            prescribed_late_by_days=30,
            check_in_inventory_baseline="present",
        ),
    ]
    for facts in test_cases:
        ours = pack.render_factor_card(facts)
        legacy = _legacy_format(facts)
        assert ours == legacy, (
            f"Byte mismatch for facts={facts!r}\n"
            f"ours   = {ours!r}\n"
            f"legacy = {legacy!r}"
        )
