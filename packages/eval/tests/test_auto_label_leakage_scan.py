"""Tests for the facts leakage scanner (Phase 7, SHA-28).

The scanner is the firewall between LLM-summarised `GoldCase.facts` text
and `CaseFile.tenant_narrative` (which `case_file_adapter.py` populates
verbatim). If tribunal-finding language survives summarisation, the
verdict bleeds into the prediction prompt — a hard correctness failure.

Two checks under test:
  1. Phrase scan over `canonicalize_text(facts).lower()`.
  2. Span-section check: every source span must point at a paragraph whose
     section tag is "pre_decision_record".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.auto_label.leakage_scan import (
    LEAKAGE_PHRASES,
    LeakageFinding,
    scan_facts_for_leakage,
)
from eval.schema import Provenance


_FIXTURES = Path(__file__).parent / "fixtures"


def _pre_decision_sections(*pairs: tuple[int, int]) -> dict[tuple[int, int], str]:
    """Tag every (page, paragraph) in `pairs` as pre_decision_record."""
    return {pair: "pre_decision_record" for pair in pairs}


# ---------------------------------------------------------------------------
# Phrase positives — each representative phrase must trigger.
# ---------------------------------------------------------------------------


class TestPhrasePositive:
    def test_we_find_that_triggers(self) -> None:
        facts = "The tenancy ended in May. We find that the deposit was wrongly retained."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert len(findings) == 1
        assert findings[0].rule == "tribunal_finding_phrase"
        assert "we find that" in findings[0].detail.lower()

    def test_we_award_triggers(self) -> None:
        facts = "We award damages of 220 GBP to the tenant."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert len(findings) == 1
        assert findings[0].rule == "tribunal_finding_phrase"
        assert "we award" in findings[0].detail.lower()

    def test_we_order_triggers(self) -> None:
        facts = "We order the landlord to repay the disputed sum."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase" and "we order" in f.detail.lower()
                   for f in findings)

    def test_we_conclude_triggers(self) -> None:
        facts = "On the evidence, we conclude the cleaning charge was unjustified."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase" and "we conclude" in f.detail.lower()
                   for f in findings)

    def test_we_accept_the_applicant_triggers(self) -> None:
        facts = "We accept the applicant's account of the move-out inspection."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase"
                   and "we accept the applicant" in f.detail.lower()
                   for f in findings)

    def test_the_tribunal_finds_triggers(self) -> None:
        facts = "The tribunal finds the deposit was not protected within statutory time."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase"
                   and "the tribunal finds" in f.detail.lower()
                   for f in findings)

    def test_phrase_finding_carries_char_offset(self) -> None:
        prefix = "The tenancy began in 2022. "
        facts = prefix + "We award damages of 220 GBP."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        phrase_findings = [f for f in findings if f.rule == "tribunal_finding_phrase"]
        assert phrase_findings
        # offset is into canonical(facts).lower(); for ASCII input it equals
        # the raw index of the lowercased "we award".
        assert phrase_findings[0].char_offset == len(prefix)


# ---------------------------------------------------------------------------
# Phrase negatives — descriptive party submissions must NOT trigger.
# ---------------------------------------------------------------------------


class TestPhraseNegative:
    @pytest.mark.parametrize(
        "facts",
        [
            "The applicant submitted that the deposit was retained without cause.",
            "The respondent argued that cleaning costs were reasonable.",
            "The parties agreed the tenancy ended on 2023-05-31.",
            "The applicant claims 400 GBP in respect of the deposit.",
            "The respondent contends the carpets required deep cleaning.",
        ],
    )
    def test_descriptive_phrasing_clean(self, facts: str) -> None:
        assert scan_facts_for_leakage(facts, source_spans=[], page_sections={}) == []


# ---------------------------------------------------------------------------
# Canonicalisation must run before phrase matching (curly quotes, etc.).
# ---------------------------------------------------------------------------


class TestPhraseCanonicalisation:
    def test_curly_quotes_do_not_bypass_scanner(self) -> None:
        # Curly-quoted leakage phrase. Without canonicalisation this would
        # not match. canonicalize_text maps “/” -> "/'.
        facts = "“We award damages of 220 GBP.”"
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase" and "we award" in f.detail.lower()
                   for f in findings)

    def test_ligature_does_not_bypass_scanner(self) -> None:
        # "We ﬁnd that" with a fi-ligature — must canonicalise to "we find that".
        facts = "We ﬁnd that the deposit was wrongly retained."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase" and "we find that" in f.detail.lower()
                   for f in findings)


# ---------------------------------------------------------------------------
# Phrase matching is case-insensitive after canonicalisation.
# ---------------------------------------------------------------------------


class TestPhraseCaseInsensitive:
    def test_uppercase_we_find_that_triggers(self) -> None:
        facts = "WE FIND THAT THE DEPOSIT WAS WRONGLY RETAINED."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase" and "we find that" in f.detail.lower()
                   for f in findings)

    def test_mixed_case_we_award_triggers(self) -> None:
        facts = "We Award Damages."
        findings = scan_facts_for_leakage(facts, source_spans=[], page_sections={})
        assert any(f.rule == "tribunal_finding_phrase" and "we award" in f.detail.lower()
                   for f in findings)


# ---------------------------------------------------------------------------
# Span-section check.
# ---------------------------------------------------------------------------


class TestSpanSectionCheck:
    def test_all_spans_pre_decision_clean(self) -> None:
        spans = [
            Provenance(page=1, paragraph=3),
            Provenance(page=1, paragraph=7),
        ]
        sections = _pre_decision_sections((1, 3), (1, 7))
        facts = "Tenant occupied the flat from 2022-01-01 to 2023-05-31 paying 1200 GBP."
        assert scan_facts_for_leakage(facts, source_spans=spans, page_sections=sections) == []

    def test_span_in_tribunal_reasoning_flagged(self) -> None:
        bad = Provenance(page=2, paragraph=14)
        spans = [Provenance(page=1, paragraph=3), bad]
        sections = {
            (1, 3): "pre_decision_record",
            (2, 14): "tribunal_reasoning",
        }
        facts = "Tenant occupied the flat from 2022-01-01 to 2023-05-31 paying 1200 GBP."
        findings = scan_facts_for_leakage(facts, source_spans=spans, page_sections=sections)
        assert len(findings) == 1
        assert findings[0].rule == "span_outside_pre_decision"
        assert findings[0].provenance == bad
        assert "tribunal_reasoning" in findings[0].detail

    def test_span_in_order_outcome_flagged(self) -> None:
        bad = Provenance(page=3, paragraph=2)
        sections = {(3, 2): "order_outcome"}
        facts = "Tenant occupied the flat from 2022-01-01 to 2023-05-31 paying 1200 GBP."
        findings = scan_facts_for_leakage(facts, source_spans=[bad], page_sections=sections)
        assert len(findings) == 1
        assert findings[0].rule == "span_outside_pre_decision"
        assert findings[0].provenance == bad
        assert "order_outcome" in findings[0].detail

    def test_span_with_unknown_section_flagged(self) -> None:
        # A span whose (page, paragraph) is missing from the sections map is
        # also "outside pre_decision_record" — fail closed.
        bad = Provenance(page=9, paragraph=1)
        findings = scan_facts_for_leakage(
            "Tenant occupied the flat from 2022 to 2023 paying 1200 GBP and disputed the deduction.",
            source_spans=[bad],
            page_sections={},
        )
        assert len(findings) == 1
        assert findings[0].rule == "span_outside_pre_decision"
        assert findings[0].provenance == bad

    def test_mixed_phrase_and_bad_span(self) -> None:
        bad = Provenance(page=2, paragraph=14)
        sections = {(2, 14): "tribunal_reasoning"}
        facts = "We award damages. Tenant occupied the flat from 2022 to 2023."
        findings = scan_facts_for_leakage(facts, source_spans=[bad], page_sections=sections)
        rules = sorted(f.rule for f in findings)
        assert rules == ["span_outside_pre_decision", "tribunal_finding_phrase"]


# ---------------------------------------------------------------------------
# Round-trip: real fixture facts must scan clean; injecting a phrase trips it.
# ---------------------------------------------------------------------------


class TestRoundTripFixture:
    def test_minimal_fixture_facts_clean(self) -> None:
        gold = json.loads((_FIXTURES / "gold_case_minimal.json").read_text())
        facts = gold["facts"]
        # The fixture has no source_spans for facts; the phrase scan alone
        # must pass and the (empty) span list trivially passes the section check.
        assert scan_facts_for_leakage(facts, source_spans=[], page_sections={}) == []

    def test_fixture_facts_with_injected_finding_phrase_trips(self) -> None:
        gold = json.loads((_FIXTURES / "gold_case_minimal.json").read_text())
        injected = "The tribunal finds for the applicant. " + gold["facts"]
        findings = scan_facts_for_leakage(injected, source_spans=[], page_sections={})
        phrase_findings = [f for f in findings if f.rule == "tribunal_finding_phrase"]
        assert len(phrase_findings) == 1
        assert "the tribunal finds" in phrase_findings[0].detail.lower()


# ---------------------------------------------------------------------------
# Sanity: the constant exposes the documented set.
# ---------------------------------------------------------------------------


class TestLeakagePhraseSet:
    def test_all_required_phrases_present(self) -> None:
        # Pulled directly from sparring §3 / Phase 7 spec.
        required = {
            "the tribunal finds",
            "we find that",
            "we award",
            "we order",
            "we conclude",
            "we determine",
            "we accept the applicant",
            "we accept the respondent",
            "in our view",
            "judgment for the applicant",
            "judgment for the respondent",
            "the respondent is liable",
            "the applicant is liable",
            "we hold that",
        }
        shipped = {p.lower() for p in LEAKAGE_PHRASES}
        missing = required - shipped
        assert not missing, f"missing required leakage phrases: {missing}"
