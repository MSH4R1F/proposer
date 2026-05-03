"""SHA-126: citation verifier integration test (slow).

Builds a tiny IssuePrediction with one valid citation (matches a chunk
in the synthetic retrieval results) and one invalid citation (case
reference that does not appear in retrieval). Asserts the verifier
keeps the valid citation and removes the invalid one.

Marked slow because it imports the full llm_orchestrator stack.
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.slow


def test_citation_verifier_accepts_valid_rejects_invalid():
    from llm_orchestrator.models.case_file import DisputeIssue
    from llm_orchestrator.models.prediction_v2 import (
        Citation,
        IssueOutcome,
        IssuePrediction,
        IssueRetrievalResult,
    )
    from llm_orchestrator.pipeline.citation_verifier import CitationVerifier

    valid_citation = Citation(
        case_reference="LON/00AG/HMF/2023/0001",
        year=2023,
        paragraph="12",
        quote="Section 72(1) of the Housing Act 2004 was made out.",
        relevance="Establishes the offence basis for the RRO.",
    )
    invalid_citation = Citation(
        case_reference="FAKE/REF/9999/0000",
        year=2023,
        quote="Imaginary supporting passage.",
        relevance="Invented case reference.",
    )

    pred = IssuePrediction(
        issue_type=DisputeIssue.OTHER,
        issue_description="RRO unlicensed HMO",
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
        supporting_cases=[valid_citation, invalid_citation],
    )

    retrieval_result = IssueRetrievalResult(
        issue_type=DisputeIssue.OTHER,
        query_used="unlicensed HMO rent repayment",
        results=[
            {
                "case_reference": "LON/00AG/HMF/2023/0001",
                "source_id": "LON/00AG/HMF/2023/0001",
                "source_kind": "case_decision",
                "paragraph": "12",
            }
        ],
        rag_confidence=0.8,
        is_sufficient=True,
    )

    verifier = CitationVerifier()
    [updated_pred], result = verifier.verify(
        [pred], {DisputeIssue.OTHER: retrieval_result}
    )

    refs = [c.case_reference for c in result.verified_citations]
    removed_refs = [c.case_reference for c in result.removed_citations]
    assert "LON/00AG/HMF/2023/0001" in refs
    assert "FAKE/REF/9999/0000" in removed_refs
    # The kept citation list on the prediction is now just the valid one.
    assert [c.case_reference for c in updated_pred.supporting_cases] == [
        "LON/00AG/HMF/2023/0001"
    ]
