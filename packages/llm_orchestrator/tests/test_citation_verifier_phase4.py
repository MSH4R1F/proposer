"""SHA-20 Phase 4: tests for CitationVerifier source_id / span / source_kind checks.

The legacy case-ref-only contract is preserved (existing tests in
``test_issue_predictor.py`` continue to pass). These tests verify the
new behaviour: citations are removed when source_id mismatches, when
the cited paragraph span does not overlap the retrieved chunk's span,
and when source_kind disagrees.
"""

from __future__ import annotations

from typing import List

import pytest

from llm_orchestrator.models.prediction_v2 import (
    Citation,
    IssueOutcome,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
)
from llm_orchestrator.pipeline.citation_verifier import CitationVerifier


def _retrieved(
    *,
    case_reference: str = "",
    source_id: str = "",
    source_kind: str | None = None,
    paragraph: int | str | None = None,
):
    return {
        "case_reference": case_reference,
        "source_id": source_id,
        "source_kind": source_kind,
        "paragraph": paragraph,
    }


def _wrap(retrieval_results) -> dict:
    issue = next(iter(IssueType))
    return {
        issue: IssueRetrievalResult(
            issue_type=issue, query_used="", results=retrieval_results
        )
    }


def _prediction_with(citations: List[Citation]) -> IssuePrediction:
    issue = next(iter(IssueType))
    return IssuePrediction(
        issue_type=issue,
        outcome=IssueOutcome.UNCERTAIN,
        raw_confidence=0.5,
        supporting_cases=citations,
    )


class TestSourceIdContract:
    def test_legacy_case_reference_match_still_works(self):
        retrieval = _wrap([_retrieved(case_reference="LON_X_2022")])
        cite = Citation(
            case_reference="LON_X_2022",
            year=2022,
            quote="q",
            relevance="r",
        )
        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert result.all_citations_valid is True
        assert cite.verified is True

    def test_unmatched_case_reference_is_removed(self):
        retrieval = _wrap([_retrieved(case_reference="LON_X_2022")])
        cite = Citation(
            case_reference="LON_DOES_NOT_EXIST",
            year=2022,
            quote="q",
            relevance="r",
        )
        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert result.removal_rate == 1.0
        assert cite.verified is False


class TestSourceKindContract:
    def test_mismatched_source_kind_removes_citation(self):
        # Retrieved chunk is a STATUTE; citation claims a tribunal CASE_DECISION.
        retrieval = _wrap(
            [_retrieved(case_reference="X", source_id="X", source_kind="statute")]
        )
        cite = Citation(case_reference="X", year=2022, quote="q", relevance="r")
        # We attach source_kind via model_extra (Citation has no first-class field).
        cite_dict = cite.model_dump()
        cite_dict["source_kind"] = "case_decision"
        # Build a citation that carries the extra; Pydantic v2 default is to
        # forbid extras, so we set it on the instance attribute that
        # CitationVerifier already inspects.
        cite.__pydantic_extra__ = {"source_kind": "case_decision"}

        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert result.all_citations_valid is False
        assert cite.verified is False

    def test_matching_source_kind_keeps_citation(self):
        retrieval = _wrap(
            [
                _retrieved(
                    case_reference="X",
                    source_id="X",
                    source_kind="case_decision",
                )
            ]
        )
        cite = Citation(case_reference="X", year=2022, quote="q", relevance="r")
        cite.__pydantic_extra__ = {"source_kind": "case_decision"}
        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert cite.verified is True


class TestSpanOverlapContract:
    def test_cited_paragraph_outside_chunk_span_removes_citation(self):
        # Retrieved chunk covers paragraph 5 only. Citation claims paragraph 99.
        retrieval = _wrap(
            [_retrieved(case_reference="X", source_id="X", paragraph=5)]
        )
        cite = Citation(
            case_reference="X",
            year=2022,
            quote="q",
            relevance="r",
            paragraph="99",
        )
        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert cite.verified is False

    def test_cited_range_overlapping_chunk_paragraph_keeps_citation(self):
        retrieval = _wrap(
            [_retrieved(case_reference="X", source_id="X", paragraph=7)]
        )
        cite = Citation(
            case_reference="X",
            year=2022,
            quote="q",
            relevance="r",
            paragraph="5-10",  # range that includes paragraph 7
        )
        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert cite.verified is True

    def test_chunk_without_paragraph_metadata_does_not_block_legacy_citation(self):
        # Legacy chunk has no ``paragraph`` field. We must not regress and
        # remove a citation that the case-ref-only path would have kept.
        retrieval = _wrap(
            [_retrieved(case_reference="X", source_id="X")]
        )
        cite = Citation(
            case_reference="X",
            year=2022,
            quote="q",
            relevance="r",
            paragraph="42",
        )
        verifier = CitationVerifier()
        _, result = verifier.verify([_prediction_with([cite])], retrieval)
        assert cite.verified is True
