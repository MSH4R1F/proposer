"""Proposition-grained precedent retrieval for SHA-36 Phase 2.

This module turns the Phase 1 proposition KG substrate into a deterministic
retriever. It deliberately does not call an LLM: the prediction LLM can now be
OpenAI or Anthropic via SHA-114, while retrieval remains cheap and auditable.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Union
from uuid import UUID

import numpy as np
from pydantic import BaseModel, Field

from ..models.case_file import CaseFile, DisputeIssue
from ..models.prediction_v2 import IssueContext, IssueRetrievalResult, IssueType

try:  # package-style imports in the normal PYTHONPATH=packages runtime
    from kg_builder.propositions import (
        DecisionDocument,
        Proposition,
        PropositionEdge,
        PropositionEdgeType,
        PropositionType,
        normalize_for_matching,
    )
except ModuleNotFoundError:  # repository-root imports used by some API tests
    from packages.kg_builder.propositions import (
        DecisionDocument,
        Proposition,
        PropositionEdge,
        PropositionEdgeType,
        PropositionType,
        normalize_for_matching,
    )


ISSUE_TAG_ALIASES: dict[DisputeIssue, set[str]] = {
    DisputeIssue.CLEANING: {"cleaning", "professional_cleaning"},
    DisputeIssue.DAMAGE: {"damage", "repair", "property_condition"},
    DisputeIssue.INVENTORY: {
        "inventory",
        "check_in_inventory",
        "check_out_inventory",
    },
    DisputeIssue.REDECORATION: {"redecoration", "decoration", "painting"},
    DisputeIssue.FAIR_WEAR_AND_TEAR: {
        "fair_wear_and_tear",
        "wear_and_tear",
    },
    DisputeIssue.DEPOSIT_PROTECTION: {
        "deposit_protection",
        "tenancy_deposit_scheme",
        "prescribed_information",
    },
    DisputeIssue.GARDEN: {"garden", "gardening", "grounds"},
    DisputeIssue.KEYS: {"keys", "lock", "fob"},
    DisputeIssue.MISSING_ITEMS: {"missing_items", "contents", "furnishings"},
    DisputeIssue.UTILITIES: {"utilities", "bills", "council_tax"},
}


EDGE_WEIGHTS: dict[PropositionEdgeType, float] = {
    PropositionEdgeType.supports: 1.0,
    PropositionEdgeType.applies_rule_to_fact: 1.10,
    PropositionEdgeType.contradicts: 0.65,
    PropositionEdgeType.temporal_before: 0.45,
    PropositionEdgeType.cites: 0.75,
}

REVERSE_EDGE_WEIGHTS: dict[PropositionEdgeType, float] = {
    PropositionEdgeType.supports: 0.45,
    PropositionEdgeType.applies_rule_to_fact: 0.50,
}

TEXT_STOPWORDS = {
    "and",
    "case",
    "deposit",
    "dispute",
    "for",
    "from",
    "landlord",
    "tenant",
    "tenancy",
    "the",
    "this",
    "tribunal",
    "with",
}


class PropositionGraphRepository(Protocol):
    async def search_by_issue_tags(
        self, tags: Sequence[str], *, limit: int = 50
    ) -> list[Proposition]:
        ...

    async def search_by_entities(
        self, entities: Sequence[str], *, limit: int = 50
    ) -> list[Proposition]:
        ...

    async def search_text(self, query: str, *, limit: int = 50) -> list[Proposition]:
        ...

    async def load_edges_for_documents(
        self, document_ids: Sequence[UUID]
    ) -> list[PropositionEdge]:
        ...

    async def load_propositions_by_ids(
        self, proposition_ids: Sequence[UUID]
    ) -> list[Proposition]:
        ...

    async def load_propositions_for_documents(
        self, document_ids: Sequence[UUID], *, limit_per_document: int = 25
    ) -> list[Proposition]:
        ...

    async def load_document_metadata(
        self, document_ids: Sequence[UUID]
    ) -> dict[UUID, DecisionDocument]:
        ...


class PropositionRetrieverConfig(BaseModel):
    seed_limit_per_source: int = Field(default=50, gt=0)
    same_document_limit: int = Field(default=25, gt=0)
    max_nodes: int = Field(default=1500, gt=0)
    max_per_document: int = Field(default=4, gt=0)
    alpha: float = Field(default=0.15, gt=0.0, lt=1.0)
    tolerance: float = Field(default=1e-6, gt=0.0)
    max_iterations: int = Field(default=50, gt=0)
    reference_year: int = Field(default_factory=lambda: date.today().year, ge=2000)


class PropositionSeed(BaseModel):
    proposition_id: UUID
    seed_weight: float = Field(ge=0.0)
    seed_reasons: list[str] = Field(default_factory=list)


class PropositionScoreBreakdown(BaseModel):
    pagerank_score: float = 0.0
    issue_match_score: float = 0.0
    text_match_score: float = 0.0
    temporal_relevance: float = 0.0
    proposition_confidence: float = 0.0
    proposition_type_bonus: float = 0.0
    final_score: float = 0.0


class RankedProposition(BaseModel):
    proposition: Proposition
    document: Optional[DecisionDocument] = None
    seed: Optional[PropositionSeed] = None
    score_breakdown: PropositionScoreBreakdown

    model_config = {"arbitrary_types_allowed": True}


class PersonalizedPageRank:
    """Deterministic in-memory PPR over typed proposition edges."""

    def __init__(
        self,
        *,
        alpha: float = 0.15,
        tolerance: float = 1e-6,
        max_iterations: int = 50,
    ) -> None:
        self.alpha = alpha
        self.tolerance = tolerance
        self.max_iterations = max_iterations

    def rank(
        self,
        node_ids: Sequence[UUID],
        edges: Sequence[PropositionEdge],
        seeds: dict[UUID, PropositionSeed],
    ) -> dict[UUID, float]:
        if not node_ids:
            return {}

        ordered = sorted(dict.fromkeys(node_ids), key=str)
        index = {node_id: i for i, node_id in enumerate(ordered)}
        n = len(ordered)

        personalization = np.zeros(n, dtype=float)
        for proposition_id, seed in seeds.items():
            idx = index.get(proposition_id)
            if idx is not None:
                personalization[idx] = max(personalization[idx], seed.seed_weight)
        if personalization.sum() <= 0:
            personalization[:] = 1.0 / n
        else:
            personalization = personalization / personalization.sum()

        transition = np.zeros((n, n), dtype=float)
        for edge in edges:
            source_idx = index.get(edge.from_proposition_id)
            target_idx = index.get(edge.to_proposition_id)
            if source_idx is None or target_idx is None:
                continue
            base = EDGE_WEIGHTS.get(edge.edge_type, 0.50) * float(edge.confidence)
            if base > 0:
                transition[source_idx, target_idx] += base
            reverse = REVERSE_EDGE_WEIGHTS.get(edge.edge_type)
            if reverse:
                transition[target_idx, source_idx] += reverse * float(edge.confidence)

        row_sums = transition.sum(axis=1)
        for row_idx, total in enumerate(row_sums):
            if total > 0:
                transition[row_idx, :] = transition[row_idx, :] / total
            else:
                transition[row_idx, :] = personalization

        rank = personalization.copy()
        for _ in range(self.max_iterations):
            next_rank = self.alpha * personalization + (1 - self.alpha) * (
                rank @ transition
            )
            if float(np.abs(next_rank - rank).sum()) < self.tolerance:
                rank = next_rank
                break
            rank = next_rank

        max_rank = float(rank.max()) if rank.size else 0.0
        if max_rank <= 0:
            return {node_id: 0.0 for node_id in ordered}
        return {node_id: float(rank[index[node_id]] / max_rank) for node_id in ordered}


class PropositionRetriever:
    """DB-backed proposition retrieval with direct and PageRank modes."""

    def __init__(
        self,
        repository: PropositionGraphRepository,
        *,
        config: Optional[PropositionRetrieverConfig] = None,
    ) -> None:
        self.repository = repository
        self.config = config or PropositionRetrieverConfig()
        self.pagerank = PersonalizedPageRank(
            alpha=self.config.alpha,
            tolerance=self.config.tolerance,
            max_iterations=self.config.max_iterations,
        )

    async def retrieve(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        *,
        top_k: int = 10,
        use_pagerank: bool = True,
        query: Optional[str] = None,
        min_cases_required: int = 3,
    ) -> IssueRetrievalResult:
        query_used = query or build_proposition_query(issue, case_file)
        seeds, seed_props = await self._select_seeds(issue, case_file, query_used)
        if not seed_props:
            return IssueRetrievalResult(
                issue_type=issue.issue_type,
                query_used=query_used,
                results=[],
                rag_confidence=0.0,
                is_sufficient=False,
            )

        graph_props, graph_edges, documents = await self._load_graph(seed_props)
        if not graph_props:
            return IssueRetrievalResult(
                issue_type=issue.issue_type,
                query_used=query_used,
                results=[],
                rag_confidence=0.0,
                is_sufficient=False,
            )

        if use_pagerank:
            pagerank_scores = self.pagerank.rank(
                [p.proposition_id for p in graph_props],
                graph_edges,
                seeds,
            )
        else:
            max_seed = max((s.seed_weight for s in seeds.values()), default=1.0)
            pagerank_scores = {
                p.proposition_id: (
                    seeds[p.proposition_id].seed_weight / max_seed
                    if p.proposition_id in seeds and max_seed > 0
                    else 0.0
                )
                for p in graph_props
            }

        ranked = self._score(
            graph_props,
            documents,
            seeds,
            pagerank_scores,
            issue=issue,
            query=query_used,
        )
        selected = self._apply_diversity(ranked, top_k=top_k)
        result_cards = [self._to_result_card(item) for item in selected]

        temporal_distribution: dict[int, int] = {}
        for card in result_cards:
            year = card.get("year")
            if isinstance(year, int):
                temporal_distribution[year] = temporal_distribution.get(year, 0) + 1

        confidence = (
            sum(float(card.get("combined_score", 0.0)) for card in result_cards)
            / len(result_cards)
            if result_cards
            else 0.0
        )

        return IssueRetrievalResult(
            issue_type=issue.issue_type,
            query_used=query_used,
            results=result_cards,
            rag_confidence=min(max(confidence, 0.0), 1.0),
            temporal_distribution=temporal_distribution,
            legislative_regime=self._legislative_regime(result_cards, issue),
            is_sufficient=len(result_cards) >= min_cases_required,
        )

    async def _select_seeds(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        query: str,
    ) -> tuple[dict[UUID, PropositionSeed], list[Proposition]]:
        seeds: dict[UUID, PropositionSeed] = {}
        props: dict[UUID, Proposition] = {}

        exact_tag = issue.issue_type.value
        aliases = canonical_issue_tags(issue.issue_type)
        by_issue = await self.repository.search_by_issue_tags(
            sorted({exact_tag, *aliases}),
            limit=self.config.seed_limit_per_source,
        )
        for prop in by_issue:
            prop_tags = {tag.lower() for tag in prop.issue_tags}
            if exact_tag in prop_tags:
                self._record_seed(
                    seeds,
                    prop,
                    1.00,
                    f"issue_exact:{exact_tag}",
                )
            elif prop_tags & aliases:
                matched = sorted(prop_tags & aliases)[0]
                self._record_seed(seeds, prop, 0.85, f"issue_alias:{matched}")
            props[prop.proposition_id] = prop

        entities = collect_case_entities(issue, case_file)
        if entities:
            by_entity = await self.repository.search_by_entities(
                entities,
                limit=self.config.seed_limit_per_source,
            )
            for prop in by_entity:
                self._record_seed(seeds, prop, 0.75, "entity_match")
                props[prop.proposition_id] = prop

        amount_date_terms = collect_amount_date_terms(issue, case_file)
        if amount_date_terms:
            by_amount_date = await self.repository.search_text(
                " ".join(amount_date_terms),
                limit=self.config.seed_limit_per_source,
            )
            for prop in by_amount_date:
                self._record_seed(seeds, prop, 0.65, "amount_or_date_match")
                props[prop.proposition_id] = prop

        by_text = await self.repository.search_text(
            query,
            limit=self.config.seed_limit_per_source,
        )
        for prop in by_text:
            self._record_seed(seeds, prop, 0.60, "text_match")
            props[prop.proposition_id] = prop

        return seeds, list(props.values())

    async def _load_graph(
        self,
        seed_props: Sequence[Proposition],
    ) -> tuple[list[Proposition], list[PropositionEdge], dict[UUID, DecisionDocument]]:
        doc_ids = sorted({p.document_id for p in seed_props}, key=str)
        same_doc = await self.repository.load_propositions_for_documents(
            doc_ids,
            limit_per_document=self.config.same_document_limit,
        )
        props_by_id: dict[UUID, Proposition] = {}
        for prop in [*seed_props, *same_doc]:
            if is_citable_proposition(prop):
                props_by_id.setdefault(prop.proposition_id, prop)
            if len(props_by_id) >= self.config.max_nodes:
                break

        edges = await self.repository.load_edges_for_documents(doc_ids)
        node_ids = set(props_by_id)
        edges = [
            edge
            for edge in edges
            if edge.from_proposition_id in node_ids and edge.to_proposition_id in node_ids
        ]
        documents = await self.repository.load_document_metadata(
            sorted({p.document_id for p in props_by_id.values()}, key=str)
        )
        return list(props_by_id.values()), edges, documents

    def _score(
        self,
        props: Sequence[Proposition],
        documents: dict[UUID, DecisionDocument],
        seeds: dict[UUID, PropositionSeed],
        pagerank_scores: dict[UUID, float],
        *,
        issue: IssueContext,
        query: str,
    ) -> list[RankedProposition]:
        ranked: list[RankedProposition] = []
        query_tokens = tokenize(query)
        issue_tags = canonical_issue_tags(issue.issue_type) | {issue.issue_type.value}

        for prop in props:
            document = documents.get(prop.document_id)
            pagerank_score = pagerank_scores.get(prop.proposition_id, 0.0)
            prop_tags = {tag.lower() for tag in prop.issue_tags}
            if issue.issue_type.value in prop_tags:
                issue_match = 1.0
            elif prop_tags & issue_tags:
                issue_match = 0.85
            else:
                issue_match = 0.15 if prop_tags else 0.0
            text_match = text_overlap_score(
                query_tokens,
                [prop.text, prop.source_passage, " ".join(prop.entities)],
            )
            temporal = temporal_relevance(
                document.year if document else None,
                reference_year=self.config.reference_year,
            )
            type_bonus = proposition_type_bonus(prop.proposition_type)
            final = (
                0.35 * pagerank_score
                + 0.25 * issue_match
                + 0.15 * text_match
                + 0.10 * temporal
                + 0.10 * float(prop.confidence)
                + 0.05 * type_bonus
            )
            ranked.append(
                RankedProposition(
                    proposition=prop,
                    document=document,
                    seed=seeds.get(prop.proposition_id),
                    score_breakdown=PropositionScoreBreakdown(
                        pagerank_score=pagerank_score,
                        issue_match_score=issue_match,
                        text_match_score=text_match,
                        temporal_relevance=temporal,
                        proposition_confidence=float(prop.confidence),
                        proposition_type_bonus=type_bonus,
                        final_score=final,
                    ),
                )
            )
        ranked.sort(
            key=lambda item: (
                item.score_breakdown.final_score,
                item.score_breakdown.pagerank_score,
                str(item.proposition.proposition_id),
            ),
            reverse=True,
        )
        return ranked

    def _apply_diversity(
        self,
        ranked: Sequence[RankedProposition],
        *,
        top_k: int,
    ) -> list[RankedProposition]:
        selected: list[RankedProposition] = []
        selected_ids: set[UUID] = set()
        per_doc: dict[UUID, int] = defaultdict(int)
        seen_quotes: set[str] = set()

        def can_add(item: RankedProposition) -> bool:
            prop = item.proposition
            if prop.proposition_id in selected_ids:
                return False
            if per_doc[prop.document_id] >= self.config.max_per_document:
                return False
            normalized_quote = normalize_for_matching(prop.source_passage).lower()
            if normalized_quote in seen_quotes:
                return False
            return True

        def add(item: RankedProposition) -> bool:
            if len(selected) >= top_k or not can_add(item):
                return False
            selected.append(item)
            selected_ids.add(item.proposition.proposition_id)
            per_doc[item.proposition.document_id] += 1
            seen_quotes.add(
                normalize_for_matching(item.proposition.source_passage).lower()
            )
            return True

        for required_types in (
            {PropositionType.rule, PropositionType.authority},
            {PropositionType.outcome},
        ):
            for item in ranked:
                if item.proposition.proposition_type in required_types and add(item):
                    break

        for item in ranked:
            add(item)
            if len(selected) >= top_k:
                break

        selected.sort(
            key=lambda item: (
                item.score_breakdown.final_score,
                str(item.proposition.proposition_id),
            ),
            reverse=True,
        )
        return selected

    def _to_result_card(self, item: RankedProposition) -> dict[str, Any]:
        prop = item.proposition
        doc = item.document
        score = item.score_breakdown
        seed = item.seed
        paragraph = prop.paragraph_ref or "N/A"
        year = doc.year if doc else None
        region = doc.region_code if doc else None
        card_text = (
            f"PROPOSITION {prop.proposition_id}\n"
            f"Case: {prop.case_reference}"
            f"{f' ({year})' if year else ''}\n"
            f"Paragraph: {paragraph}\n"
            f"Type: {prop.proposition_type.value}\n"
            f"Claim: {prop.text}\n"
            f"Quote: {prop.source_passage}"
        )
        return {
            "kind": "proposition",
            "proposition_id": str(prop.proposition_id),
            "case_reference": prop.case_reference,
            "year": year,
            "region": region,
            "paragraph_ref": prop.paragraph_ref,
            "paragraph": prop.paragraph_ref,
            "proposition_type": prop.proposition_type.value,
            "text": prop.text,
            "quote": prop.source_passage,
            "chunk_text": card_text,
            "source_passage": prop.source_passage,
            "combined_score": score.final_score,
            "final_score": score.final_score,
            "rerank_score": score.final_score,
            "score_breakdown": score.model_dump(),
            "seed_trace": seed.model_dump(mode="json") if seed else None,
            "source": {
                "document_id": str(prop.document_id),
                "source_start_char": prop.source_start_char,
                "source_end_char": prop.source_end_char,
                "source_url": doc.source_url if doc else None,
            },
            "metadata": {
                "document_id": str(prop.document_id),
                "issue_tags": list(prop.issue_tags),
                "entities": list(prop.entities),
                "has_source_offsets": (
                    prop.source_start_char is not None
                    and prop.source_end_char is not None
                ),
            },
        }

    @staticmethod
    def _record_seed(
        seeds: dict[UUID, PropositionSeed],
        prop: Proposition,
        weight: float,
        reason: str,
    ) -> None:
        existing = seeds.get(prop.proposition_id)
        if existing is None:
            seeds[prop.proposition_id] = PropositionSeed(
                proposition_id=prop.proposition_id,
                seed_weight=weight,
                seed_reasons=[reason],
            )
            return
        if weight > existing.seed_weight:
            existing.seed_weight = weight
        if reason not in existing.seed_reasons:
            existing.seed_reasons.append(reason)

    @staticmethod
    def _legislative_regime(
        cards: Sequence[dict[str, Any]],
        issue: IssueContext,
    ) -> str:
        if issue.issue_type != IssueType.DEPOSIT_PROTECTION:
            return "current"
        years = [card.get("year") for card in cards if isinstance(card.get("year"), int)]
        if not years:
            return "current"
        post_2019 = sum(1 for year in years if year > 2019)
        between_2015_2019 = sum(1 for year in years if 2015 <= year <= 2019)
        if post_2019 > len(years) / 2:
            return "post_tenant_fees_act_2019"
        if between_2015_2019 > len(years) / 2:
            return "post_deregulation_act_2015"
        return "current"


def canonical_issue_tags(issue_type: Union[IssueType, DisputeIssue, str]) -> set[str]:
    issue_value = getattr(issue_type, "value", str(issue_type))
    for key, tags in ISSUE_TAG_ALIASES.items():
        if key.value == issue_value:
            return {tag.lower() for tag in tags}
    return set()


def build_proposition_query(issue: IssueContext, case_file: CaseFile) -> str:
    parts = [
        f"Tenancy deposit dispute: {issue.issue_type.value}",
        f"Deposit amount: {case_file.tenancy.deposit_amount or 'unknown'}",
    ]
    if issue.issue_description:
        parts.append(issue.issue_description)
    if issue.tenant_claim:
        parts.append(issue.tenant_claim.description)
    if issue.landlord_claim:
        parts.append(issue.landlord_claim.description)
    if issue.kg_constraints:
        parts.extend(issue.kg_constraints)
    for evidence in issue.supporting_evidence:
        description = getattr(evidence, "description", None)
        if description:
            parts.append(str(description))
    return " | ".join(str(part) for part in parts if part)


def collect_case_entities(issue: IssueContext, case_file: CaseFile) -> list[str]:
    values: list[str] = []
    tenancy = case_file.tenancy
    prop = case_file.property
    for value in (
        tenancy.deposit_scheme,
        tenancy.tenancy_type,
        prop.region,
        prop.property_type,
        prop.postcode,
    ):
        if value:
            values.append(str(value))
    for evidence in issue.supporting_evidence:
        evidence_type = getattr(evidence, "type", None) or getattr(
            evidence, "evidence_type", None
        )
        if hasattr(evidence_type, "value"):
            values.append(str(evidence_type.value))
        elif evidence_type:
            values.append(str(evidence_type))
    for constraint in issue.kg_constraints:
        values.extend(extract_entity_like_terms(constraint))
    return unique_normalized(values)


def collect_amount_date_terms(issue: IssueContext, case_file: CaseFile) -> list[str]:
    raw_values: list[str] = []
    for amount in (
        case_file.tenancy.deposit_amount,
        case_file.dispute_amount,
        issue.claimed_amount,
    ):
        if amount is not None:
            raw_values.append(str(int(amount)) if float(amount).is_integer() else str(amount))
    for claim in [issue.tenant_claim, issue.landlord_claim]:
        if claim and claim.claimed_amount is not None:
            amount = claim.claimed_amount
            raw_values.append(str(int(amount)) if float(amount).is_integer() else str(amount))
    for dt in (case_file.tenancy.start_date, case_file.tenancy.end_date):
        if dt is not None:
            raw_values.append(str(dt))
            raw_values.append(str(dt.year))
    for event in issue.timeline_events:
        if event.date is not None:
            raw_values.append(str(event.date))
            raw_values.append(str(event.date.year))
    for constraint in issue.kg_constraints:
        raw_values.extend(re.findall(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{4}\b|\b\d+(?:\.\d+)?\b", constraint))
    return unique_normalized(raw_values)


def extract_entity_like_terms(text: str) -> list[str]:
    terms = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text):
        lowered = token.lower()
        if lowered not in TEXT_STOPWORDS:
            terms.append(lowered)
    return terms[:8]


def unique_normalized(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = str(value).strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def tokenize(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-zA-Z0-9_'-]+", text.lower()):
        if len(token) >= 3 and token not in TEXT_STOPWORDS:
            tokens.add(token)
    return tokens


def text_overlap_score(query_tokens: set[str], texts: Sequence[str]) -> float:
    if not query_tokens:
        return 0.0
    haystack = tokenize(" ".join(texts))
    if not haystack:
        return 0.0
    overlap = len(query_tokens & haystack)
    return min(1.0, overlap / max(1, math.sqrt(len(query_tokens))))


def temporal_relevance(
    case_year: Optional[int],
    *,
    reference_year: int = 2026,
    half_life: float = 3.0,
) -> float:
    if case_year is None:
        return 0.0
    if case_year > reference_year:
        return 0.0
    age = reference_year - case_year
    return 0.5 ** (age / half_life)


def proposition_type_bonus(prop_type: PropositionType) -> float:
    if prop_type in (PropositionType.rule, PropositionType.authority):
        return 1.0
    if prop_type == PropositionType.outcome:
        return 0.85
    return 0.65


def is_citable_proposition(prop: Proposition) -> bool:
    return bool(prop.source_passage and prop.case_reference)


__all__ = [
    "ISSUE_TAG_ALIASES",
    "PersonalizedPageRank",
    "PropositionGraphRepository",
    "PropositionRetriever",
    "PropositionRetrieverConfig",
    "PropositionScoreBreakdown",
    "PropositionSeed",
    "RankedProposition",
    "build_proposition_query",
    "canonical_issue_tags",
]
