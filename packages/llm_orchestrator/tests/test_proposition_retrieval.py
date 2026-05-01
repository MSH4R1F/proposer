from __future__ import annotations

from datetime import date
from typing import Sequence
from uuid import UUID

import pytest

from llm_orchestrator.models.case_file import CaseFile, DisputeIssue, PartyRole
from llm_orchestrator.models.prediction_v2 import (
    IssueContext,
    IssueRetrievalResult,
    RetrievalStrategy,
)
from llm_orchestrator.pipeline.issue_retrieval import IssueRetriever
from llm_orchestrator.pipeline.proposition_retrieval import (
    PersonalizedPageRank,
    PropositionRetriever,
    PropositionRetrieverConfig,
    PropositionSeed,
    canonical_issue_tags,
)

try:
    from kg_builder.propositions import (
        DecisionDocument,
        Proposition,
        PropositionEdge,
        PropositionEdgeType,
        PropositionType,
        deterministic_document_id,
        deterministic_edge_id,
        deterministic_proposition_id,
        sha256_hex,
    )
except ModuleNotFoundError:
    from packages.kg_builder.propositions import (
        DecisionDocument,
        Proposition,
        PropositionEdge,
        PropositionEdgeType,
        PropositionType,
        deterministic_document_id,
        deterministic_edge_id,
        deterministic_proposition_id,
        sha256_hex,
    )


def _doc(case_ref: str, *, year: int = 2024) -> DecisionDocument:
    content_sha = sha256_hex(f"content::{case_ref}")
    return DecisionDocument(
        document_id=deterministic_document_id(case_ref, content_sha),
        case_reference=case_ref,
        year=year,
        region_code="LON",
        decision_date=date(year, 5, 1),
        content_sha256=content_sha,
        text_sha256=sha256_hex(f"text::{case_ref}"),
        char_count=2000,
        extraction_method="fixture",
    )


def _prop(
    doc: DecisionDocument,
    text: str,
    *,
    paragraph_ref: str,
    ptype: PropositionType = PropositionType.fact,
    source_passage: str | None = None,
    issue_tags: list[str] | None = None,
    entities: list[str] | None = None,
) -> Proposition:
    quote = source_passage or text
    return Proposition(
        proposition_id=deterministic_proposition_id(
            doc.document_id,
            paragraph_ref,
            quote,
            ptype,
            text,
        ),
        document_id=doc.document_id,
        case_reference=doc.case_reference,
        text=text,
        source_passage=quote,
        paragraph_ref=paragraph_ref,
        source_start_char=10,
        source_end_char=10 + len(quote),
        proposition_type=ptype,
        issue_tags=issue_tags or [],
        entities=entities or [],
        confidence=0.9,
    )


def _edge(
    source: Proposition,
    target: Proposition,
    edge_type: PropositionEdgeType = PropositionEdgeType.supports,
) -> PropositionEdge:
    return PropositionEdge(
        edge_id=deterministic_edge_id(
            source.proposition_id,
            target.proposition_id,
            edge_type,
        ),
        from_proposition_id=source.proposition_id,
        to_proposition_id=target.proposition_id,
        document_id=source.document_id,
        edge_type=edge_type,
        confidence=0.9,
    )


class FakePropositionRepo:
    def __init__(
        self,
        docs: Sequence[DecisionDocument],
        props: Sequence[Proposition],
        edges: Sequence[PropositionEdge],
    ) -> None:
        self.docs = {doc.document_id: doc for doc in docs}
        self.props = list(props)
        self.edges = list(edges)

    async def search_by_issue_tags(
        self,
        tags: Sequence[str],
        *,
        limit: int = 50,
    ) -> list[Proposition]:
        wanted = {tag.lower() for tag in tags}
        return [
            prop
            for prop in self.props
            if wanted & {tag.lower() for tag in prop.issue_tags}
        ][:limit]

    async def search_by_entities(
        self,
        entities: Sequence[str],
        *,
        limit: int = 50,
    ) -> list[Proposition]:
        wanted = {entity.lower() for entity in entities}
        return [
            prop
            for prop in self.props
            if wanted & {entity.lower() for entity in prop.entities}
        ][:limit]

    async def search_text(self, query: str, *, limit: int = 50) -> list[Proposition]:
        tokens = [token.lower() for token in query.split() if len(token) >= 3]
        found = []
        for prop in self.props:
            text = f"{prop.text} {prop.source_passage} {prop.case_reference}".lower()
            if any(token.strip("|:,.-") in text for token in tokens):
                found.append(prop)
        return found[:limit]

    async def load_edges_for_documents(
        self,
        document_ids: Sequence[UUID],
    ) -> list[PropositionEdge]:
        wanted = set(document_ids)
        return [edge for edge in self.edges if edge.document_id in wanted]

    async def load_propositions_by_ids(
        self,
        proposition_ids: Sequence[UUID],
    ) -> list[Proposition]:
        wanted = set(proposition_ids)
        return [prop for prop in self.props if prop.proposition_id in wanted]

    async def load_propositions_for_documents(
        self,
        document_ids: Sequence[UUID],
        *,
        limit_per_document: int = 25,
    ) -> list[Proposition]:
        wanted = set(document_ids)
        out = []
        for document_id in wanted:
            out.extend(
                [prop for prop in self.props if prop.document_id == document_id][
                    :limit_per_document
                ]
            )
        return out

    async def load_document_metadata(
        self,
        document_ids: Sequence[UUID],
    ) -> dict[UUID, DecisionDocument]:
        return {
            document_id: self.docs[document_id]
            for document_id in document_ids
            if document_id in self.docs
        }


def test_canonical_issue_tags_cover_core_deposit_aliases() -> None:
    assert "professional_cleaning" in canonical_issue_tags(DisputeIssue.CLEANING)
    assert "prescribed_information" in canonical_issue_tags(
        DisputeIssue.DEPOSIT_PROTECTION
    )


def test_personalized_pagerank_uses_typed_edges_and_restart_vector() -> None:
    doc = _doc("LON_TEST_2024_0001")
    a = _prop(doc, "A seed fact.", paragraph_ref="1")
    b = _prop(doc, "B supported rule.", paragraph_ref="2")
    c = _prop(doc, "C isolated outcome.", paragraph_ref="3")
    ranks = PersonalizedPageRank().rank(
        [a.proposition_id, b.proposition_id, c.proposition_id],
        [_edge(a, b, PropositionEdgeType.applies_rule_to_fact)],
        {
            a.proposition_id: PropositionSeed(
                proposition_id=a.proposition_id,
                seed_weight=1.0,
                seed_reasons=["issue_exact:cleaning"],
            )
        },
    )

    assert ranks[a.proposition_id] == pytest.approx(1.0)
    assert ranks[b.proposition_id] > ranks[c.proposition_id]


@pytest.mark.asyncio
async def test_proposition_retriever_returns_cited_pagerank_cards() -> None:
    doc = _doc("LON_TEST_2024_0002")
    fact = _prop(
        doc,
        "The landlord claimed cleaning costs.",
        paragraph_ref="10",
        issue_tags=["cleaning"],
        entities=["inventory"],
    )
    rule = _prop(
        doc,
        "Cleaning deductions require evidence beyond ordinary wear.",
        paragraph_ref="11",
        ptype=PropositionType.rule,
        issue_tags=["cleaning"],
    )
    outcome = _prop(
        doc,
        "The tribunal allowed only part of the cleaning deduction.",
        paragraph_ref="12",
        ptype=PropositionType.outcome,
        issue_tags=["cleaning"],
    )
    repo = FakePropositionRepo(
        [doc],
        [fact, rule, outcome],
        [
            _edge(rule, fact, PropositionEdgeType.applies_rule_to_fact),
            _edge(fact, outcome, PropositionEdgeType.supports),
        ],
    )
    retriever = PropositionRetriever(
        repo,
        config=PropositionRetrieverConfig(
            seed_limit_per_source=10,
            same_document_limit=10,
            max_per_document=4,
        ),
    )
    case_file = CaseFile(
        user_role=PartyRole.TENANT,
        issues=[DisputeIssue.CLEANING],
        tenant_narrative="The landlord wants professional cleaning.",
    )
    issue = IssueContext(
        issue_type=DisputeIssue.CLEANING,
        issue_description="Cleaning deduction",
        kg_constraints=["No professional cleaning invoice was supplied."],
    )

    result = await retriever.retrieve(
        issue,
        case_file,
        top_k=3,
        use_pagerank=True,
        min_cases_required=1,
    )

    assert result.is_sufficient is True
    assert len(result.results) == 3
    assert {item["proposition_type"] for item in result.results} >= {
        "rule",
        "outcome",
    }
    first = result.results[0]
    assert first["kind"] == "proposition"
    assert first["proposition_id"]
    assert first["case_reference"] == doc.case_reference
    assert first["quote"]
    assert first["score_breakdown"]["final_score"] > 0
    assert first["source"]["source_start_char"] == 10


@pytest.mark.asyncio
async def test_issue_retriever_dispatches_to_proposition_strategy_without_rag() -> None:
    class FakeRetriever:
        def __init__(self) -> None:
            self.calls = []

        async def retrieve(self, issue, case_file, **kwargs):
            self.calls.append((issue, case_file, kwargs))
            return IssueRetrievalResult(
                issue_type=issue.issue_type,
                query_used=kwargs["query"],
                results=[{"kind": "proposition", "case_reference": "LON_TEST"}],
                is_sufficient=True,
            )

    prop = FakeRetriever()
    retriever = IssueRetriever(
        rag_pipeline=None,
        min_cases_required=1,
        proposition_retriever=prop,
    )
    case_file = CaseFile(
        user_role=PartyRole.TENANT,
        issues=[DisputeIssue.CLEANING],
    )
    issue = IssueContext(issue_type=DisputeIssue.CLEANING)

    result = await retriever._retrieve_for_issue(
        issue,
        case_file,
        top_k=5,
        retrieval_strategy=RetrievalStrategy.PROPOSITION_PAGERANK,
    )

    assert result.is_sufficient is True
    assert prop.calls[0][2]["use_pagerank"] is True
