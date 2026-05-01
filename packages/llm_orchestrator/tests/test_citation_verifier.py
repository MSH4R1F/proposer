from llm_orchestrator.models.case_file import DisputeIssue
from llm_orchestrator.models.prediction_v2 import (
    Citation,
    IssuePrediction,
    IssueRetrievalResult,
    IssueOutcome,
)
from llm_orchestrator.pipeline.citation_verifier import CitationVerifier


def _prediction(citation: Citation) -> IssuePrediction:
    return IssuePrediction(
        issue_type=DisputeIssue.CLEANING,
        issue_description="Cleaning",
        outcome=IssueOutcome.SPLIT,
        raw_confidence=0.7,
        supporting_cases=[citation],
    )


def test_verifier_accepts_matching_proposition_id_and_quote() -> None:
    citation = Citation(
        case_reference="LON_TEST_2024_0001",
        year=2024,
        paragraph="12",
        proposition_id="prop-1",
        quote="The tribunal allowed part of the cleaning deduction.",
        relevance="Similar cleaning deduction.",
    )
    retrieval = IssueRetrievalResult(
        issue_type=DisputeIssue.CLEANING,
        results=[
            {
                "kind": "proposition",
                "proposition_id": "prop-1",
                "case_reference": "LON_TEST_2024_0001",
                "paragraph_ref": "12",
                "quote": "The tribunal allowed part of the cleaning deduction.",
            }
        ],
    )

    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        {DisputeIssue.CLEANING: retrieval},
    )

    assert verification.all_citations_valid is True
    assert predictions[0].supporting_cases[0].verified is True


def test_verifier_rejects_invented_proposition_id_even_same_case() -> None:
    citation = Citation(
        case_reference="LON_TEST_2024_0001",
        year=2024,
        paragraph="12",
        proposition_id="invented-prop",
        quote="The tribunal allowed part of the cleaning deduction.",
        relevance="Similar cleaning deduction.",
    )
    retrieval = IssueRetrievalResult(
        issue_type=DisputeIssue.CLEANING,
        results=[
            {
                "case_reference": "LON_TEST_2024_0001",
                "year": 2024,
                "chunk_text": "Fallback chunk for same case.",
            },
            {
                "kind": "proposition",
                "proposition_id": "prop-1",
                "case_reference": "LON_TEST_2024_0001",
                "paragraph_ref": "12",
                "quote": "The tribunal allowed part of the cleaning deduction.",
            }
        ],
    )

    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        {DisputeIssue.CLEANING: retrieval},
    )

    assert verification.all_citations_valid is False
    assert predictions[0].supporting_cases == []


def test_verifier_rejects_padded_proposition_quote() -> None:
    citation = Citation(
        case_reference="LON_TEST_2024_0001",
        year=2024,
        paragraph="12",
        proposition_id="prop-1",
        quote=(
            "The tribunal allowed part of the cleaning deduction, and then "
            "ordered an extra unsupported penalty."
        ),
        relevance="Padded citation should not verify.",
    )
    retrieval = IssueRetrievalResult(
        issue_type=DisputeIssue.CLEANING,
        results=[
            {
                "kind": "proposition",
                "proposition_id": "prop-1",
                "case_reference": "LON_TEST_2024_0001",
                "paragraph_ref": "12",
                "quote": "The tribunal allowed part of the cleaning deduction.",
            }
        ],
    )

    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        {DisputeIssue.CLEANING: retrieval},
    )

    assert verification.all_citations_valid is False
    assert predictions[0].supporting_cases == []


def test_verifier_accepts_chunk_case_reference_without_proposition_id() -> None:
    citation = Citation(
        case_reference="CHI/0007/2023",
        year=2023,
        quote="A chunk quote.",
        relevance="Retrieved chunk case.",
    )
    retrieval = IssueRetrievalResult(
        issue_type=DisputeIssue.CLEANING,
        results=[
            {
                "case_reference": "CHI/0007/2023",
                "year": 2023,
                "chunk_text": "A normal RAG chunk.",
            }
        ],
    )

    predictions, verification = CitationVerifier().verify(
        [_prediction(citation)],
        {DisputeIssue.CLEANING: retrieval},
    )

    assert verification.all_citations_valid is True
    assert predictions[0].supporting_cases[0].verified is True
