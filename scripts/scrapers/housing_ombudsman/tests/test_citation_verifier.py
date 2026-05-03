"""Citation verifier sanity check (slow / optional).

Builds one valid + one invalid citation and asserts the verifier rejects
the invalid one. The retrieval result schema is the deposit-pipeline's
``IssueRetrievalResult`` (re-used here as the test for cross-domain
verification on Ombudsman case-refs).
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.slow


def _have_runtime_deps() -> bool:
    try:
        import llm_orchestrator.pipeline.citation_verifier  # noqa: F401
        import llm_orchestrator.models.prediction_v2  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _have_runtime_deps(), reason="llm_orchestrator deps missing")
def test_invalid_citation_rejected():
    from llm_orchestrator.models.prediction_v2 import (
        Citation,
        IssueOutcome,
        IssuePrediction,
        IssueRetrievalResult,
        IssueType,
    )
    from llm_orchestrator.pipeline.citation_verifier import CitationVerifier

    valid_citation = Citation(
        case_reference="202300042",
        year=2024,
        paragraph="3",
        quote="The landlord failed to inspect for 14 weeks.",
        relevance="Establishes maladministration in repair handling.",
        similarity_score=0.8,
    )
    invalid_citation = Citation(
        case_reference="999999999",  # never retrieved
        year=2024,
        paragraph="1",
        quote="Fabricated quote.",
        relevance="Fabricated relevance.",
        similarity_score=0.5,
    )

    issue = IssuePrediction(
        issue_type=IssueType.OTHER,
        outcome=IssueOutcome.TENANT_WINS,
        raw_confidence=0.7,
        supporting_cases=[valid_citation, invalid_citation],
    )

    retrieval = IssueRetrievalResult(
        issue_type=IssueType.OTHER,
        query_used="damp and mould landlord obligations",
        results=[
            {
                "case_reference": "202300042",
                "source_id": "202300042",
                "source_kind": "ombudsman_determination",
                "paragraph": "1-10",
            }
        ],
    )

    verifier = CitationVerifier()
    predictions, verification = verifier.verify(
        [issue],
        {IssueType.OTHER: retrieval},
    )

    refs = {c.case_reference for c in predictions[0].supporting_cases}
    assert "202300042" in refs
    assert "999999999" not in refs
    removed_refs = {c.case_reference for c in verification.removed_citations}
    assert "999999999" in removed_refs
    assert verification.removal_rate > 0.0
