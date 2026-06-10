"""Tests for CitationVerifier with factor-constrained (hybrid-mode) retrieval results.

Factor-constrained retrieval (_comparator_pack_to_issue_result in issue_retrieval.py)
sets ``proposition_id`` on EVERY result row.  Before the fix, this caused
``ref_to_chunks`` to be empty, leading to 100 % citation removal in hybrid mode.

Covers:
  (a) All retrieval results carry proposition_id + case_reference; citation has
      case_reference only (proposition_id=None) → VERIFIED via ref_to_chunks.
  (b) Same retrieval; citation has junk proposition_id ("comparator") + valid
      case_reference → VERIFIED via fallback to ref_to_chunks.
  (c) Same retrieval; citation references a case NOT in the retrieved set →
      REMOVED (anti-hallucination semantics preserved).
  (d) Genuine UUID proposition_id citation that matches the retrieved result's
      UUID, same case_reference and paragraph, with a valid quote substring →
      VERIFIED via the proposition path.
  (e) All pre-existing citation-verifier tests remain unaffected (run via
      regular pytest collection — this file does not import them but they share
      the same test run).
"""

from __future__ import annotations

import pytest

from llm_orchestrator.models.case_file import DisputeIssue
from llm_orchestrator.models.prediction_v2 import (
    Citation,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
)
from llm_orchestrator.pipeline.citation_verifier import CitationVerifier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RETRIEVED_CASE_REF = "housing-ombudsman-202451564"
_PROP_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _factor_constrained_result(
    *,
    case_reference: str = _RETRIEVED_CASE_REF,
    proposition_id: str = _PROP_UUID,
    paragraph: str = "15",
    quote: str = "The landlord failed to carry out repairs within a reasonable time.",
    source_id: str = "",
) -> dict:
    """Mimic a row emitted by _comparator_pack_to_issue_result.

    Every row carries a proposition_id (UUID) AND a case_reference.
    """
    return {
        "kind": "proposition",
        "proposition_id": proposition_id,
        "case_reference": case_reference,
        "paragraph_ref": paragraph,
        "paragraph": paragraph,
        "quote": quote,
        "source_id": source_id,
        "chunk_text": quote,
    }


def _retrieval(results: list) -> dict:
    issue = DisputeIssue.CLEANING
    return {
        issue: IssueRetrievalResult(
            issue_type=issue,
            query_used="",
            results=results,
        )
    }


def _prediction(citation: Citation) -> IssuePrediction:
    return IssuePrediction(
        issue_type=DisputeIssue.CLEANING,
        issue_description="Factor-constrained test",
        outcome=IssueOutcome.SPLIT,
        raw_confidence=0.7,
        supporting_cases=[citation],
    )


# ---------------------------------------------------------------------------
# (a) LLM emits citation with case_reference only, proposition_id=None
# ---------------------------------------------------------------------------

def test_a_case_reference_only_citation_verified_against_factor_constrained_results():
    """retrieval results all carry proposition_id; LLM citation has only case_reference."""
    retrieval = _retrieval([_factor_constrained_result()])
    citation = Citation(
        case_reference=_RETRIEVED_CASE_REF,
        year=2024,
        quote="The landlord failed to carry out repairs within a reasonable time.",
        relevance="Same repairs failure pattern.",
    )
    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        retrieval,
    )
    assert verification.all_citations_valid is True, (
        "Citation should be verified: case_reference matches a retrieved result"
    )
    assert predictions[0].supporting_cases[0].verified is True


# ---------------------------------------------------------------------------
# (b) Junk proposition_id ("comparator") + valid case_reference → fallback
# ---------------------------------------------------------------------------

def test_b_junk_proposition_id_falls_back_to_case_reference_match():
    """LLM emits placeholder proposition_id copied from schema example."""
    retrieval = _retrieval([_factor_constrained_result()])
    citation = Citation(
        case_reference=_RETRIEVED_CASE_REF,
        year=2024,
        proposition_id="comparator",  # junk placeholder
        quote="The landlord failed to carry out repairs within a reasonable time.",
        relevance="Same repairs failure pattern.",
    )
    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        retrieval,
    )
    assert verification.all_citations_valid is True, (
        "Junk proposition_id should fall back to case_reference lookup and verify"
    )
    assert predictions[0].supporting_cases[0].verified is True


# ---------------------------------------------------------------------------
# (c) case_reference not in retrieved set → REMOVED
# ---------------------------------------------------------------------------

def test_c_hallucinated_case_reference_is_removed():
    """Citation references a case that was never retrieved → must be removed."""
    retrieval = _retrieval([_factor_constrained_result()])
    citation = Citation(
        case_reference="housing-ombudsman-999999999",  # not retrieved
        year=2024,
        quote="Some fabricated quote.",
        relevance="Should be rejected.",
    )
    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        retrieval,
    )
    assert verification.removal_rate == 1.0, (
        "Citation whose case was not retrieved must be removed"
    )
    assert predictions[0].supporting_cases == []
    assert citation.verified is False


# ---------------------------------------------------------------------------
# (d) Genuine UUID proposition_id citation → verified via proposition path
# ---------------------------------------------------------------------------

def test_d_genuine_uuid_proposition_citation_verifies_via_proposition_path():
    """A citation carrying the exact proposition UUID, matching case_reference,
    paragraph, and a quote that is a substring of the retrieved quote must be
    accepted via _verify_proposition_citation (the strict path)."""
    retrieval = _retrieval([_factor_constrained_result()])
    citation = Citation(
        case_reference=_RETRIEVED_CASE_REF,
        year=2024,
        proposition_id=_PROP_UUID,
        paragraph="15",
        # _verify_proposition_citation checks citation_quote IN result_quote
        quote="The landlord failed to carry out repairs",
        relevance="Exact proposition match.",
    )
    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        retrieval,
    )
    assert verification.all_citations_valid is True, (
        "Citation with exact UUID, matching case_reference/paragraph/quote substring "
        "should be verified via the proposition path"
    )
    assert predictions[0].supporting_cases[0].verified is True


# ---------------------------------------------------------------------------
# (d2) Genuine UUID but WRONG paragraph → rejected even with correct case_reference
# ---------------------------------------------------------------------------

def test_d2_uuid_citation_with_wrong_paragraph_is_rejected():
    """Proposition path is strict: mismatched paragraph must reject the citation."""
    retrieval = _retrieval([_factor_constrained_result(paragraph="15")])
    citation = Citation(
        case_reference=_RETRIEVED_CASE_REF,
        year=2024,
        proposition_id=_PROP_UUID,
        paragraph="99",  # wrong paragraph
        quote="The landlord failed to carry out repairs",
        relevance="Wrong paragraph.",
    )
    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        retrieval,
    )
    # proposition path fails (wrong paragraph); fallback via case_reference also
    # runs but _citation_matches only checks source_kind/span — the paragraph span
    # for "99" does NOT overlap chunk paragraph 15, so it should be removed.
    assert citation.verified is False
    assert predictions[0].supporting_cases == []
