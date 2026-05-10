"""Tests for STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD behaviour (recovery T2).

When the {kg_fact_card} or {abstention_warning} placeholders resolve to an
empty string, the IRAC prompt is left with orphan blank-line gaps. These
gaps appear to confuse the LLM (33% abstention vs 12.5% in rag_only on the
2026-05-07 ablation). The suppressor collapses runs of 3+ newlines down to
2, making the empty-KG case behaviourally closer to rag_only.
"""

from __future__ import annotations

import pytest

from llm_orchestrator.pipeline.issue_predictor import _suppress_empty_factor_card


@pytest.fixture(autouse=True)
def _clean_suppress_env(monkeypatch):
    monkeypatch.delenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", raising=False)
    yield


def test_suppression_collapses_orphan_blank_lines(monkeypatch):
    """Input with 4 consecutive newlines (3 blank lines) collapses to 2 (one
    blank line)."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    raw = "a\n\n\n\nb"
    cleaned = _suppress_empty_factor_card(raw)
    assert "\n\n\n" not in cleaned
    # The single intentional paragraph break (\n\n) is preserved.
    assert cleaned == "a\n\nb"


def test_suppression_preserves_non_empty_content(monkeypatch):
    """A prompt with real KG card content (no orphan blank-line runs) must
    pass through unchanged."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    sample = (
        "ISSUE: repairs_disrepair - Boiler\n\n"
        "KEY KG FACTS (typed):\n"
        "- damp_reported = true\n"
        "- inspection_delayed = true\n\n"
        "EVIDENCE AVAILABLE:\n"
        "Photos, complaint correspondence.\n"
    )
    assert _suppress_empty_factor_card(sample) == sample


def test_suppression_disabled_when_flag_zero(monkeypatch):
    """STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=0 is a no-op (legacy)."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "0")
    raw = "KEY FACTS:\nfoo\n\n\nEVIDENCE:\n"
    assert _suppress_empty_factor_card(raw) == raw


def test_suppression_idempotent(monkeypatch):
    """Applying the suppressor twice produces the same result as once."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    raw = "section_a\n\n\n\n\nsection_b\n\n\n\nsection_c"
    once = _suppress_empty_factor_card(raw)
    twice = _suppress_empty_factor_card(once)
    assert once == twice
    assert "\n\n\n" not in once


def test_suppression_default_on(monkeypatch):
    """Default behaviour (no env set) must be suppression-on per recovery
    plan Hard Constraint 2."""
    monkeypatch.delenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", raising=False)
    raw = "a\n\n\n\nb"
    assert _suppress_empty_factor_card(raw) == "a\n\nb"


def test_suppression_handles_empty_string(monkeypatch):
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    assert _suppress_empty_factor_card("") == ""


def test_suppression_handles_irac_prompt_with_empty_card(monkeypatch):
    """When the IRAC prompt is formatted with empty kg_fact_card and
    abstention_warning, the output prompt must not contain triple newlines
    around where those placeholders sat."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    from llm_orchestrator.prompts.prediction_v2 import IRAC_USER_PROMPT

    raw = IRAC_USER_PROMPT.format(
        issue_type="repairs_disrepair",
        issue_description="x",
        deposit_amount="0",
        claimed_amount="0",
        tenancy_duration="6m",
        tenancy_type="ast",
        region="london",
        data_completeness=0.5,
        deposit_protection_summary="",
        tenant_claim="",
        landlord_claim="",
        evidence_conflicts="",
        kg_constraints="",
        kg_fact_card="",
        abstention_warning="",
        evidence_summary="",
        timeline_summary="",
        num_retrieved_cases=0,
        retrieved_cases="",
    )
    cleaned = _suppress_empty_factor_card(raw)
    assert "\n\n\n" not in cleaned
    # Section headers still present.
    assert "KEY FACTS FROM CASE ANALYSIS:" in cleaned
    assert "EVIDENCE AVAILABLE:" in cleaned
