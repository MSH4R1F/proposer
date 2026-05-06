import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

import structlog

from ..models.case_file import CaseFile
from ..models.prediction_v2 import (
    IssueContext,
    IssueRetrievalResult,
    IssueType,
    PredictionMode,
    RetrievalStrategy,
)
from .kg_facts import KGFacts


# Typed contradiction patterns: which retrieved-chunk text patterns contradict
# each typed KG fact. Kept small and grounded in UK tribunal vocabulary.
DEPOSIT_LATE_CONTRADICTORS = (
    "on time",
    "within 14 days",
    "within 30 days",
    "compliant protection",
)
DEPOSIT_NONE_CONTRADICTORS = (
    "protected within",
    "scheme certificate",
    "deposit was protected",
)
PRESCRIBED_LATE_CONTRADICTORS = (
    "prescribed information served on time",
    "served within 30 days",
)
INVENTORY_ABSENT_CONTRADICTORS = (
    "inventory at check-in",
    "check-in inventory",
    "baseline inventory",
)

# Penalty applied per matched contradiction pattern. Tuned so a single match
# pushes a precedent below temporally newer / on-point alternatives without
# eliminating it (soft demotion).
KG_CONTRADICTION_PENALTY = -0.35

logger = structlog.get_logger()


RagQueryPurpose = Literal[
    "liability",
    "remedy",
    "award_amount",
    "counterexample",
    "reasonable_redress",
    "severe_maladministration",
    "complaint_handling",
]


@dataclass(frozen=True)
class RagQuerySpec:
    """One deliberate retrieval pass for the hybrid Ombudsman pipeline."""

    purpose: RagQueryPurpose
    query: str
    filters: Dict[str, Any] = field(default_factory=dict)
    top_k: int = 8
    search_type: Literal["semantic", "lexical", "hybrid"] = "hybrid"
    require_amount: bool = False


@dataclass(frozen=True)
class RetrievalGapReport:
    enough_unique_cases: bool
    has_liability_cases: bool
    has_remedy_cases: bool
    has_award_amounts: bool
    has_counterexamples: bool
    has_quotes: bool


def temporal_relevance_score(
    case_year: int,
    query_year: int = 2026,
    half_life: float = 3.0,
    legislative_breaks: Optional[Dict[int, str]] = None,
) -> float:
    """Exponential decay with legislative regime penalties.

    Default half-life of 3 years means:
    - 2025 case: score ~= 0.79
    - 2023 case: score ~= 0.63
    - 2020 case: score ~= 0.40
    """
    age = query_year - case_year
    base_decay = 0.5 ** (age / half_life)

    regime_penalty = 1.0
    if legislative_breaks:
        for break_year in legislative_breaks:
            if case_year < break_year:
                regime_penalty *= 0.8

    return base_decay * regime_penalty


class IssueRetriever:
    def __init__(
        self,
        rag_pipeline: Any,
        min_cases_required: int = 3,
        proposition_retriever: Optional[Any] = None,
    ):
        self.rag = rag_pipeline
        self.min_cases_required = min_cases_required
        self.proposition_retriever = proposition_retriever

    async def retrieve_all(
        self,
        issues: List[IssueContext],
        case_file: CaseFile,
        top_k: int = 10,
        kg_facts_by_issue: Optional[Dict[IssueType, KGFacts]] = None,
        mode: PredictionMode = PredictionMode.HYBRID,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.CHUNK_RAG,
    ) -> Dict[IssueType, IssueRetrievalResult]:
        kg_facts_by_issue = kg_facts_by_issue or {}
        tasks = [
            self._retrieve_for_issue(
                issue,
                case_file,
                top_k,
                kg_facts=kg_facts_by_issue.get(issue.issue_type, KGFacts()),
                mode=mode,
                retrieval_strategy=retrieval_strategy,
            )
            for issue in issues
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        retrieval_by_issue: Dict[IssueType, IssueRetrievalResult] = {}
        for issue, result in zip(issues, results):
            if isinstance(result, BaseException):
                logger.error(
                    "issue_retrieval_failed",
                    issue_type=issue.issue_type.value,
                    error=str(result),
                )
                retrieval_by_issue[issue.issue_type] = IssueRetrievalResult(
                    issue_type=issue.issue_type,
                    is_sufficient=False,
                )
                continue
            retrieval_by_issue[issue.issue_type] = result

        return retrieval_by_issue

    async def _retrieve_for_issue(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        top_k: int,
        kg_facts: KGFacts = KGFacts(),
        mode: PredictionMode = PredictionMode.HYBRID,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.CHUNK_RAG,
    ) -> IssueRetrievalResult:
        query = self._build_issue_query(issue, case_file)
        if retrieval_strategy == RetrievalStrategy.PROPOSITION_DIRECT:
            try:
                prop_result = await self._retrieve_propositions(
                    issue,
                    case_file,
                    query=query,
                    top_k=top_k,
                    use_pagerank=False,
                )
            except Exception as exc:
                logger.warning(
                    "proposition_retrieval_failed_in_direct_strategy",
                    issue_type=issue.issue_type.value,
                    error=str(exc),
                )
                prop_result = None
            if prop_result is not None:
                return prop_result
            return await self._retrieve_chunk_rag(issue, case_file, top_k, kg_facts, mode)

        if retrieval_strategy == RetrievalStrategy.PROPOSITION_PAGERANK:
            try:
                prop_result = await self._retrieve_propositions(
                    issue,
                    case_file,
                    query=query,
                    top_k=top_k,
                    use_pagerank=True,
                )
            except Exception as exc:
                logger.warning(
                    "proposition_retrieval_failed_in_pagerank_strategy",
                    issue_type=issue.issue_type.value,
                    error=str(exc),
                )
                prop_result = None
            if prop_result is not None:
                return prop_result
            return await self._retrieve_chunk_rag(issue, case_file, top_k, kg_facts, mode)

        if retrieval_strategy == RetrievalStrategy.HYBRID_CHUNK_PROPOSITION:
            chunk_task = self._retrieve_chunk_rag(issue, case_file, top_k, kg_facts, mode)
            prop_task = self._retrieve_propositions(
                issue,
                case_file,
                query=query,
                top_k=top_k,
                use_pagerank=True,
            )
            chunk_result, prop_result = await asyncio.gather(
                chunk_task, prop_task, return_exceptions=True
            )
            if isinstance(chunk_result, BaseException):
                logger.warning(
                    "chunk_retrieval_failed_in_hybrid_strategy",
                    issue_type=issue.issue_type.value,
                    error=str(chunk_result),
                )
                chunk_result = IssueRetrievalResult(
                    issue_type=issue.issue_type,
                    query_used=query,
                    is_sufficient=False,
                )
            if isinstance(prop_result, BaseException):
                logger.warning(
                    "proposition_retrieval_failed_in_hybrid_strategy",
                    issue_type=issue.issue_type.value,
                    error=str(prop_result),
                )
                prop_result = None
            if prop_result is None:
                return chunk_result
            return self._merge_hybrid_results(
                issue,
                query=query,
                chunk_result=chunk_result,
                proposition_result=prop_result,
                top_k=top_k,
            )

        return await self._retrieve_chunk_rag(issue, case_file, top_k, kg_facts, mode)

    async def _retrieve_chunk_rag(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        top_k: int,
        kg_facts: KGFacts,
        mode: PredictionMode,
    ) -> IssueRetrievalResult:
        query = self._build_issue_query(issue, case_file)
        if self.rag is None:
            return IssueRetrievalResult(
                issue_type=issue.issue_type,
                query_used=query,
                is_sufficient=False,
            )
        is_repairs_case = self._is_repairs_case(issue, case_file)
        if is_repairs_case and mode == PredictionMode.HYBRID:
            return await self._retrieve_repairs_purposeful_hybrid(
                issue=issue,
                case_file=case_file,
                top_k=top_k,
                kg_facts=kg_facts,
            )

        retrieval_top_k = top_k + 5
        if is_repairs_case:
            # Repairs/Ombudsman predictions need enough candidate chunks to
            # choose both fact-similar and outcome-bearing passages. The
            # product asks for a small final top-k, but a slightly wider
            # retrieval pool lets the repairs reranker demote generic
            # background chunks without losing relevant determinations.
            retrieval_top_k = max(top_k + 10, top_k * 3)

        rag_result = await self.rag.retrieve(
            query=query,
            top_k=retrieval_top_k,
            query_region=case_file.property.region,
        )

        raw_results = self._extract_results(rag_result)
        rag_confidences = [self._extract_rag_confidence(rag_result)]
        if is_repairs_case:
            remedy_query = self._build_repairs_remedy_query(issue, case_file)
            remedy_result = await self.rag.retrieve(
                query=remedy_query,
                top_k=max(top_k + 5, top_k * 2),
                query_region=case_file.property.region,
            )
            raw_results = self._dedupe_results(
                [*raw_results, *self._extract_results(remedy_result)]
            )
            rag_confidences.append(self._extract_rag_confidence(remedy_result))

        if is_repairs_case:
            reranked = self._apply_repairs_ombudsman_rerank(raw_results, issue)
        else:
            reranked = self._apply_temporal_decay(raw_results, issue)
        if (
            mode in (PredictionMode.HYBRID, PredictionMode.KG_ONLY)
            and not kg_facts.is_empty()
        ):
            reranked = self._apply_kg_filter(reranked, kg_facts)
        trimmed_results = reranked[:top_k]

        temporal_distribution: Dict[int, int] = {}
        for result in trimmed_results:
            year = self._extract_year(result)
            if year is not None:
                temporal_distribution[year] = temporal_distribution.get(year, 0) + 1

        legislative_regime = self._determine_legislative_regime(trimmed_results, issue)
        nonzero_confidences = [c for c in rag_confidences if c > 0]
        rag_confidence = (
            sum(nonzero_confidences) / len(nonzero_confidences)
            if nonzero_confidences
            else 0.0
        )

        return IssueRetrievalResult(
            issue_type=issue.issue_type,
            query_used=query if not is_repairs_case else f"{query}\nREMEDY PASS: {remedy_query}",
            results=trimmed_results,
            rag_confidence=rag_confidence,
            temporal_distribution=temporal_distribution,
            legislative_regime=legislative_regime,
            is_sufficient=len(trimmed_results) >= self.min_cases_required,
        )

    async def _retrieve_repairs_purposeful_hybrid(
        self,
        *,
        issue: IssueContext,
        case_file: CaseFile,
        top_k: int,
        kg_facts: KGFacts,
    ) -> IssueRetrievalResult:
        """Run deterministic multi-query retrieval for repairs/social hybrid."""

        query_specs = self._build_repairs_query_specs(issue, case_file, top_k=top_k)
        first_wave = await self._run_rag_query_specs(query_specs, case_file)
        candidates = self._dedupe_results(first_wave["results"])

        gaps = self._assess_retrieval_gaps(candidates, top_k=top_k)
        second_wave_specs = self._build_repairs_second_wave_specs(
            issue,
            case_file,
            gaps,
            top_k=top_k,
            already_planned=len(query_specs),
        )
        if second_wave_specs:
            second_wave = await self._run_rag_query_specs(second_wave_specs, case_file)
            candidates = self._dedupe_results([*candidates, *second_wave["results"]])
            confidences = [*first_wave["confidences"], *second_wave["confidences"]]
            query_specs = [*query_specs, *second_wave_specs]
        else:
            confidences = first_wave["confidences"]

        reranked = self._apply_repairs_ombudsman_rerank(candidates, issue)
        if not kg_facts.is_empty():
            reranked = self._apply_kg_filter(reranked, kg_facts)
        trimmed_results = self._select_repairs_case_cards(reranked, max_cards=top_k)

        temporal_distribution: Dict[int, int] = {}
        for result in trimmed_results:
            year = self._extract_year(result)
            if year is not None:
                temporal_distribution[year] = temporal_distribution.get(year, 0) + 1

        nonzero_confidences = [c for c in confidences if c > 0]
        rag_confidence = (
            sum(nonzero_confidences) / len(nonzero_confidences)
            if nonzero_confidences
            else 0.0
        )

        return IssueRetrievalResult(
            issue_type=issue.issue_type,
            query_used=self._format_query_specs(query_specs),
            results=trimmed_results,
            rag_confidence=rag_confidence,
            temporal_distribution=temporal_distribution,
            legislative_regime=self._determine_legislative_regime(
                trimmed_results, issue
            ),
            is_sufficient=len(trimmed_results) >= self.min_cases_required,
        )

    async def _run_rag_query_specs(
        self,
        query_specs: List[RagQuerySpec],
        case_file: CaseFile,
    ) -> Dict[str, Any]:
        tasks = [self._retrieve_rag_query_spec(spec, case_file) for spec in query_specs]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[Any] = []
        confidences: List[float] = []
        for spec, response in zip(query_specs, responses):
            if isinstance(response, BaseException):
                logger.warning(
                    "repairs_purposeful_retrieval_failed",
                    purpose=spec.purpose,
                    error=str(response),
                )
                continue
            results.extend(response.get("results", []))
            confidences.append(self._extract_rag_confidence(response))
        return {"results": results, "confidences": confidences}

    async def _retrieve_rag_query_spec(
        self,
        spec: RagQuerySpec,
        case_file: CaseFile,
    ) -> Any:
        kwargs: Dict[str, Any] = {
            "query": spec.query,
            "top_k": spec.top_k,
            "query_region": getattr(case_file.property, "region", None),
        }
        filters = self._build_target_exclusion_filter(case_file, spec)
        if filters is not None:
            kwargs["filters"] = filters
        rag_result = await self.rag.retrieve(**kwargs)
        annotated_results = [
            self._annotated_retrieval_result(result, spec)
            for result in self._extract_results(rag_result)
        ]
        return {
            "results": annotated_results,
            "confidence": self._extract_rag_confidence(rag_result),
        }

    def _is_repairs_case(self, issue: IssueContext, case_file: CaseFile) -> bool:
        metadata = getattr(case_file, "metadata", None)
        return issue.issue_type.value in {
            "repairs_disrepair",
            "repairs_damp_mould",
            "complaint_handling_failure",
        } or (
            isinstance(metadata, dict)
            and metadata.get("domain_id") == "housing.repairs_social.v1"
        )

    def _apply_repairs_ombudsman_rerank(
        self,
        results: List[Any],
        issue: IssueContext,
    ) -> List[Any]:
        """Repairs/Ombudsman-specific rerank for prediction prompts.

        The generic deposit rerank is deliberately conservative and mostly
        score/rank based. For Ombudsman prediction we need the final prompt to
        include chunks that both match the issue and expose the determination's
        outcome/remedy. Otherwise the LLM sees lots of fact/background chunks
        and tends to hedge into ``split``/``uncertain``.
        """
        scored: List[tuple[float, Any]] = []
        for result in results:
            text = str(
                self._get_value(
                    result,
                    "text",
                    self._get_value(result, "chunk_text", ""),
                )
            )
            base = self._to_float(
                self._get_value(
                    result,
                    "rerank_score",
                    self._get_value(result, "combined_score", 0.0),
                )
            )
            if base <= 0:
                base = self._to_float(self._get_value(result, "combined_score", 0.0))
            semantic = self._to_float(self._get_value(result, "semantic_score", 0.0))
            issue_match = self._repairs_issue_match_score(text, issue)
            outcome_signal = self._ombudsman_outcome_signal_score(text)
            purpose_signal = self._repairs_purpose_signal_score(result, text)
            amount_signal = 1.0 if self._contains_award_amount(text) else 0.0

            final_score = (
                (0.25 * base)
                + (0.20 * semantic)
                + (0.20 * issue_match)
                + (0.18 * outcome_signal)
                + (0.12 * purpose_signal)
                + (0.05 * amount_signal)
            )
            self._set_value(result, "repairs_issue_match_score", issue_match)
            self._set_value(result, "ombudsman_outcome_signal_score", outcome_signal)
            self._set_value(result, "repairs_purpose_signal_score", purpose_signal)
            self._set_value(result, "has_award_amount", bool(amount_signal))
            if not self._get_value(result, "ombudsman_finding_signal", None):
                self._set_value(
                    result,
                    "ombudsman_finding_signal",
                    self._infer_ombudsman_finding(text),
                )
            self._set_value(result, "combined_score", final_score)
            self._set_value(result, "final_score", final_score)
            scored.append((final_score, result))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [result for _, result in scored]

    def _repairs_issue_match_score(self, text: str, issue: IssueContext) -> float:
        text_lower = text.lower()
        issue_value = issue.issue_type.value
        if issue_value == "repairs_damp_mould":
            terms = [
                "damp",
                "mould",
                "mold",
                "condensation",
                "ventilation",
                "black mould",
                "respiratory",
            ]
        elif issue_value == "complaint_handling_failure":
            terms = [
                "complaint handling",
                "stage 1",
                "stage 2",
                "complaint response",
                "complaints policy",
                "complaint handling code",
            ]
        else:
            terms = [
                "disrepair",
                "repair",
                "repairs",
                "leak",
                "flood",
                "roof",
                "boiler",
                "heating",
                "water ingress",
                "drain",
                "subsidence",
                "crack",
                "balcony",
            ]
        matches = sum(1 for term in terms if term in text_lower)
        if matches >= 3:
            return 1.0
        if matches == 2:
            return 0.75
        if matches == 1:
            return 0.45
        return 0.0

    @staticmethod
    def _ombudsman_outcome_signal_score(text: str) -> float:
        text_lower = text.lower()
        strong = [
            "severe maladministration",
            "maladministration",
            "service failure",
            "no maladministration",
            "reasonable redress",
            "finding",
            "we have found",
            "landlord must pay",
            "ordered the landlord",
            "compensation order",
            "what the landlord must do",
        ]
        soft = [
            "compensation",
            "apology",
            "case review",
            "policy review",
            "repair action",
            "remedies guidance",
        ]
        if any(term in text_lower for term in strong):
            return 1.0
        if any(term in text_lower for term in soft):
            return 0.6
        return 0.0

    def _repairs_purpose_signal_score(self, result: Any, text: str) -> float:
        purposes = self._result_purposes(result)
        finding = self._infer_ombudsman_finding(text)
        has_amount = self._contains_award_amount(text)
        if "award_amount" in purposes:
            return 1.0 if has_amount else 0.35
        if "remedy" in purposes:
            return 1.0 if has_amount or finding != "unknown" else 0.55
        if "counterexample" in purposes:
            return 1.0 if finding in {"no_maladministration", "reasonable_redress"} else 0.45
        if "reasonable_redress" in purposes:
            return 1.0 if finding == "reasonable_redress" else 0.45
        if "severe_maladministration" in purposes:
            return 1.0 if finding == "severe_maladministration" else 0.45
        if "complaint_handling" in purposes:
            return 0.8 if "complaint" in text.lower() else 0.35
        if "liability" in purposes:
            return 0.75 if finding != "unknown" else 0.4
        return 0.0

    async def _retrieve_propositions(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        *,
        query: str,
        top_k: int,
        use_pagerank: bool,
    ) -> Optional[IssueRetrievalResult]:
        if self.proposition_retriever is None:
            logger.warning(
                "proposition_retriever_not_configured",
                issue_type=issue.issue_type.value,
            )
            return None
        return await self.proposition_retriever.retrieve(
            issue,
            case_file,
            top_k=top_k,
            use_pagerank=use_pagerank,
            query=query,
            min_cases_required=self.min_cases_required,
        )

    def _merge_hybrid_results(
        self,
        issue: IssueContext,
        *,
        query: str,
        chunk_result: IssueRetrievalResult,
        proposition_result: IssueRetrievalResult,
        top_k: int,
    ) -> IssueRetrievalResult:
        combined = [
            *self._extract_results(chunk_result),
            *self._extract_results(proposition_result),
        ]
        scored = []
        seen: set[tuple[str, str, str]] = set()
        for result in combined:
            key = (
                str(self._get_value(result, "kind", "chunk")),
                str(self._get_value(result, "case_reference", "")),
                str(
                    self._get_value(
                        result,
                        "proposition_id",
                        self._get_value(result, "chunk_id", id(result)),
                    )
                ),
            )
            if key in seen:
                continue
            seen.add(key)
            score = self._to_float(
                self._get_value(
                    result,
                    "combined_score",
                    self._get_value(result, "final_score", 0.0),
                )
            )
            scored.append((score, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        trimmed = [result for _, result in scored[:top_k]]

        temporal_distribution: Dict[int, int] = {}
        for result in trimmed:
            year = self._extract_year(result)
            if year is not None:
                temporal_distribution[year] = temporal_distribution.get(year, 0) + 1

        confidences = [
            chunk_result.rag_confidence,
            proposition_result.rag_confidence,
        ]
        rag_confidence = sum(confidences) / len(confidences)

        return IssueRetrievalResult(
            issue_type=issue.issue_type,
            query_used=query,
            results=trimmed,
            rag_confidence=rag_confidence,
            temporal_distribution=temporal_distribution,
            legislative_regime=self._determine_legislative_regime(trimmed, issue),
            is_sufficient=len(trimmed) >= self.min_cases_required,
        )

    def _build_issue_query(self, issue: IssueContext, case_file: CaseFile) -> str:
        metadata = getattr(case_file, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        domain_id = metadata.get("domain_id")
        if domain_id == "housing.repairs_social.v1" or issue.issue_type.value in {
            "repairs_disrepair",
            "repairs_damp_mould",
            "complaint_handling_failure",
        }:
            return self._build_repairs_issue_query(issue, case_file, metadata)

        parts = [
            f"Tenancy deposit dispute: {issue.issue_type.value}",
            f"Deposit amount: \u00a3{case_file.tenancy.deposit_amount or 'unknown'}",
        ]
        if case_file.tenancy.start_date and case_file.tenancy.end_date:
            duration = (case_file.tenancy.end_date - case_file.tenancy.start_date).days
            parts.append(f"Tenancy duration: {duration} days")

        if issue.supporting_evidence:
            ev_types = set()
            for evidence in issue.supporting_evidence:
                if hasattr(evidence, "type"):
                    evidence_type = getattr(evidence, "type", None)
                    if evidence_type is not None and hasattr(evidence_type, "value"):
                        ev_types.add(
                            str(getattr(evidence_type, "value", evidence_type))
                        )
                    elif evidence_type is not None:
                        ev_types.add(str(evidence_type))
                elif hasattr(evidence, "evidence_type"):
                    ev_types.add(str(getattr(evidence, "evidence_type", "")))
            if ev_types:
                parts.append(f"Evidence available: {', '.join(sorted(ev_types))}")

        if issue.kg_constraints:
            parts.append(f"Key facts: {'; '.join(issue.kg_constraints)}")
        if issue.tenant_claim:
            parts.append(f"Tenant claims: {issue.tenant_claim.description}")
        if issue.landlord_claim:
            parts.append(f"Landlord claims: {issue.landlord_claim.description}")

        return " | ".join(parts)

    def _build_repairs_issue_query(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        metadata: Dict[str, Any],
    ) -> str:
        parts = [self._repairs_query_seed(issue)]
        matter_type = metadata.get("matter_type")
        if matter_type:
            parts.append(f"Matter type: {matter_type}")
        dispute_amount = self._to_optional_float(
            getattr(case_file, "dispute_amount", None)
        )
        if dispute_amount:
            parts.append(f"Compensation in dispute: \u00a3{dispute_amount:.2f}")

        narrative = (case_file.tenant_narrative or "").strip()
        if narrative:
            parts.append(f"Resident account: {narrative[:700]}")

        if issue.supporting_evidence:
            ev_types = set()
            for evidence in issue.supporting_evidence:
                evidence_type = getattr(evidence, "type", None)
                if evidence_type is not None and hasattr(evidence_type, "value"):
                    ev_types.add(str(evidence_type.value))
                elif evidence_type is not None:
                    ev_types.add(str(evidence_type))
            if ev_types:
                parts.append(f"Evidence available: {', '.join(sorted(ev_types))}")

        if issue.kg_constraints:
            parts.append(f"Key facts: {'; '.join(issue.kg_constraints)}")
        if issue.tenant_claim:
            parts.append(f"Resident claims: {issue.tenant_claim.description}")
        if issue.landlord_claim:
            parts.append(f"Landlord response: {issue.landlord_claim.description}")

        return " | ".join(parts)

    def _build_repairs_remedy_query(
        self,
        issue: IssueContext,
        case_file: CaseFile,
    ) -> str:
        """Build a second-pass query for Ombudsman outcome/remedy paragraphs."""
        metadata = getattr(case_file, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        parts = [
            self._repairs_query_seed(issue),
            "Housing Ombudsman remedy order compensation redress outcome finding",
            "ordered the landlord must pay what the landlord must do",
            "service failure maladministration severe maladministration reasonable redress",
            "distress inconvenience time and trouble apology repair action case review",
        ]
        matter_type = metadata.get("matter_type")
        if matter_type:
            parts.append(f"Matter type: {matter_type}")

        narrative = (getattr(case_file, "tenant_narrative", None) or "").strip()
        if narrative:
            parts.append(f"Resident account: {narrative[:350]}")
        if issue.tenant_claim:
            parts.append(f"Resident claim: {issue.tenant_claim.description[:350]}")
        if issue.landlord_claim:
            parts.append(f"Landlord response: {issue.landlord_claim.description[:350]}")
        if issue.kg_constraints:
            parts.append(f"Key facts: {'; '.join(issue.kg_constraints)}")
        return " | ".join(parts)

    def _build_repairs_query_specs(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        *,
        top_k: int,
    ) -> List[RagQuerySpec]:
        metadata = getattr(case_file, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        matter_type = metadata.get("matter_type") or issue.issue_type.value
        base_filters = {"matter_type": matter_type} if matter_type else {}
        per_query_top_k = max(8, top_k + 3)
        fact_text = self._build_retrieval_fact_text(issue, case_file)
        fact_suffix = f" | facts: {fact_text[:500]}" if fact_text else ""

        if issue.issue_type == IssueType.REPAIRS_DAMP_MOULD:
            specs = [
                RagQuerySpec(
                    purpose="liability",
                    query=(
                        "damp mould repairs landlord delayed inspection repair "
                        "service failure maladministration resident reports"
                        f"{fact_suffix}"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="liability",
                    query=(
                        "damp and mould leak condensation ventilation recurring "
                        "repair landlord response inspection works"
                        f"{fact_suffix}"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="remedy",
                    query=(
                        "damp mould maladministration compensation apology repair "
                        "action orders remedies distress inconvenience"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
                RagQuerySpec(
                    purpose="award_amount",
                    query=(
                        "damp mould compensation award GBP pounds repairs delay "
                        "distress inconvenience time and trouble"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
                RagQuerySpec(
                    purpose="reasonable_redress",
                    query=(
                        "damp mould reasonable redress landlord compensation "
                        "offered repairs completed"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="counterexample",
                    query=(
                        "damp mould no maladministration condensation resident "
                        "lifestyle landlord acted reasonably ventilation"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="severe_maladministration",
                    query=(
                        "severe maladministration damp mould long delay vulnerable "
                        "resident health children decant"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
                RagQuerySpec(
                    purpose="complaint_handling",
                    query=(
                        "damp mould complaint handling delayed response stage 1 "
                        "stage 2 poor communication time and trouble"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
            ]
        elif issue.issue_type == IssueType.COMPLAINT_HANDLING_FAILURE:
            specs = [
                RagQuerySpec(
                    purpose="liability",
                    query=(
                        "complaint handling delayed stage 1 stage 2 response "
                        "poor communication service failure maladministration"
                        f"{fact_suffix}"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="complaint_handling",
                    query=(
                        "Housing Ombudsman complaint handling code delay "
                        "escalation stage response maladministration"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="remedy",
                    query=(
                        "complaint handling compensation time and trouble "
                        "apology review remedy order"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
                RagQuerySpec(
                    purpose="counterexample",
                    query=(
                        "complaint handling no maladministration timely response "
                        "reasonable redress landlord complaint policy"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
            ]
        else:
            specs = [
                RagQuerySpec(
                    purpose="liability",
                    query=(
                        "disrepair repair delay leak heating water ingress "
                        "landlord failed repair service failure maladministration"
                        f"{fact_suffix}"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="remedy",
                    query=(
                        "disrepair repairs compensation award distress "
                        "inconvenience apology repair action order"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
                RagQuerySpec(
                    purpose="award_amount",
                    query=(
                        "repairs delay compensation award GBP pounds time and "
                        "trouble distress inconvenience"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
                RagQuerySpec(
                    purpose="reasonable_redress",
                    query=(
                        "repairs reasonable redress landlord compensation offered "
                        "works completed"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="counterexample",
                    query=(
                        "repairs no maladministration landlord acted reasonably "
                        "repair completed resident access issue"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                ),
                RagQuerySpec(
                    purpose="severe_maladministration",
                    query=(
                        "severe maladministration repairs long delay vulnerable "
                        "resident decant health safety"
                    ),
                    filters=base_filters,
                    top_k=per_query_top_k,
                    require_amount=True,
                ),
            ]
        return specs

    def _build_repairs_second_wave_specs(
        self,
        issue: IssueContext,
        case_file: CaseFile,
        gaps: RetrievalGapReport,
        *,
        top_k: int,
        already_planned: int,
    ) -> List[RagQuerySpec]:
        remaining = max(0, 12 - already_planned)
        if remaining == 0:
            return []

        metadata = getattr(case_file, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        matter_type = metadata.get("matter_type") or issue.issue_type.value
        base_filters = {"matter_type": matter_type} if matter_type else {}
        wave_top_k = max(10, top_k * 2)
        specs: List[RagQuerySpec] = []

        if not gaps.has_award_amounts:
            specs.append(
                RagQuerySpec(
                    purpose="award_amount",
                    query=(
                        f"{self._repairs_query_seed(issue)} compensation award "
                        "GBP pounds distress inconvenience repairs delay"
                    ),
                    filters=base_filters,
                    top_k=wave_top_k,
                    require_amount=True,
                )
            )
        if not gaps.has_counterexamples:
            specs.append(
                RagQuerySpec(
                    purpose="counterexample",
                    query=(
                        f"{self._repairs_query_seed(issue)} no maladministration "
                        "landlord reasonable response reasonable redress"
                    ),
                    filters=base_filters,
                    top_k=wave_top_k,
                )
            )
        if not gaps.has_liability_cases:
            specs.append(
                RagQuerySpec(
                    purpose="liability",
                    query=(
                        f"{self._repairs_query_seed(issue)} delayed inspection "
                        "landlord failed to act service failure"
                    ),
                    filters=base_filters,
                    top_k=wave_top_k,
                )
            )
        if not gaps.enough_unique_cases:
            specs.append(
                RagQuerySpec(
                    purpose="liability",
                    query=(
                        f"{self._repairs_query_seed(issue)} Housing Ombudsman "
                        "maladministration service failure comparator"
                    ),
                    filters=base_filters,
                    top_k=wave_top_k,
                )
            )
        return specs[:remaining]

    def _repairs_query_seed(self, issue: IssueContext) -> str:
        if issue.issue_type == IssueType.REPAIRS_DAMP_MOULD:
            return (
                "damp mould condensation ventilation repair delay health "
                "vulnerability compensation service failure"
            )
        if issue.issue_type == IssueType.COMPLAINT_HANDLING_FAILURE:
            return (
                "complaint handling stage 1 stage 2 delayed response poor "
                "communication complaint handling code compensation"
            )
        return (
            "disrepair repair delay leak flooding boiler heating hot water "
            "structural defect service failure compensation"
        )

    def _build_retrieval_fact_text(
        self,
        issue: IssueContext,
        case_file: CaseFile,
    ) -> str:
        parts: List[str] = []

        for value in (
            issue.issue_type.value,
            issue.issue_description,
            getattr(case_file, "tenant_narrative", None),
            getattr(case_file, "landlord_narrative", None),
        ):
            cleaned = self._clean_for_retrieval(value)
            if cleaned:
                parts.append(cleaned)

        if issue.tenant_claim:
            cleaned = self._clean_for_retrieval(issue.tenant_claim.description)
            if cleaned:
                parts.append(cleaned)
        if issue.landlord_claim:
            cleaned = self._clean_for_retrieval(issue.landlord_claim.description)
            if cleaned:
                parts.append(cleaned)

        for constraint in issue.kg_constraints or []:
            cleaned = self._clean_for_retrieval(constraint)
            if cleaned:
                parts.append(cleaned)

        for evidence in issue.supporting_evidence or []:
            text = self._get_value(
                evidence,
                "description",
                self._get_value(evidence, "text", ""),
            )
            cleaned = self._clean_for_retrieval(text)
            if cleaned:
                parts.append(cleaned)

        for event in issue.timeline_events or []:
            text = self._get_value(event, "description", "")
            cleaned = self._clean_for_retrieval(text)
            if cleaned:
                parts.append(cleaned)

        return "\n".join(parts)

    @staticmethod
    def _clean_for_retrieval(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        nullish = {
            "",
            "not provided",
            "none identified",
            "no timeline events recorded.",
            "no structured kg fact card available.",
            "no supporting evidence provided.",
            "no evidence conflicts identified.",
        }
        if text.lower() in nullish:
            return None
        return text

    def _assess_retrieval_gaps(
        self,
        candidates: List[Any],
        *,
        top_k: int,
    ) -> RetrievalGapReport:
        unique_cases = {
            self._result_case_key(candidate)
            for candidate in candidates
            if self._result_case_key(candidate)
        }
        return RetrievalGapReport(
            enough_unique_cases=len(unique_cases) >= min(4, max(1, top_k)),
            has_liability_cases=any(
                "liability" in self._result_purposes(candidate)
                for candidate in candidates
            ),
            has_remedy_cases=any(
                bool(self._result_purposes(candidate) & {"remedy", "award_amount"})
                for candidate in candidates
            ),
            has_award_amounts=any(
                self._contains_award_amount(self._result_text(candidate))
                for candidate in candidates
            ),
            has_counterexamples=any(
                bool(
                    self._result_purposes(candidate)
                    & {"counterexample", "reasonable_redress"}
                )
                for candidate in candidates
            ),
            has_quotes=any(len(self._result_text(candidate)) >= 80 for candidate in candidates),
        )

    def _select_repairs_case_cards(
        self,
        candidates: List[Any],
        *,
        max_cards: int,
    ) -> List[Any]:
        selected: List[Any] = []
        selected_ids: set[int] = set()
        seen_cases: set[str] = set()

        purpose_targets = [
            ({"liability"}, 2),
            ({"remedy", "award_amount"}, 1),
            ({"counterexample", "reasonable_redress"}, 1),
            ({"severe_maladministration"}, 1),
        ]

        def add_candidate(candidate: Any) -> bool:
            if len(selected) >= max_cards:
                return False
            candidate_id = id(candidate)
            if candidate_id in selected_ids:
                return False
            case_key = self._result_case_key(candidate)
            if case_key and case_key in seen_cases:
                return False
            selected.append(candidate)
            selected_ids.add(candidate_id)
            if case_key:
                seen_cases.add(case_key)
            return True

        for purposes, needed in purpose_targets:
            added = 0
            for candidate in candidates:
                candidate_purposes = self._result_purposes(candidate)
                if not candidate_purposes.intersection(purposes):
                    continue
                if add_candidate(candidate):
                    added += 1
                if added >= needed:
                    break

        for candidate in candidates:
            add_candidate(candidate)
            if len(selected) >= max_cards:
                break

        if len(selected) < max_cards:
            for candidate in candidates:
                if id(candidate) in selected_ids:
                    continue
                selected.append(candidate)
                selected_ids.add(id(candidate))
                if len(selected) >= max_cards:
                    break

        return selected

    def _annotated_retrieval_result(
        self,
        result: Any,
        spec: RagQuerySpec,
    ) -> Dict[str, Any]:
        card = self._retrieval_result_to_dict(result)
        text = self._result_text(card)
        card["retrieval_purpose"] = spec.purpose
        card["retrieval_purposes"] = [spec.purpose]
        card["retrieval_query"] = spec.query
        card["retrieval_requires_amount"] = spec.require_amount
        card["retrieval_search_type"] = spec.search_type
        card["has_award_amount"] = self._contains_award_amount(text)
        card["ombudsman_finding_signal"] = self._infer_ombudsman_finding(text)
        return card

    def _build_target_exclusion_filter(
        self,
        case_file: CaseFile,
        spec: RagQuerySpec,
    ) -> Optional[Any]:
        metadata = getattr(case_file, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        excluded_source_ids = self._source_id_variants(
            metadata.get("target_source_id"),
            metadata.get("excluded_source_ids", []),
            getattr(case_file, "case_id", None),
            metadata.get("source_url"),
        )
        data: Dict[str, Any] = {}
        if excluded_source_ids:
            data["excluded_source_ids"] = excluded_source_ids
        matter_type = spec.filters.get("matter_type")
        if matter_type:
            data["matter_type"] = matter_type
        if not data:
            return None
        try:
            from rag_engine.config import RetrievalFilterEnvelope
        except Exception:
            return None
        return RetrievalFilterEnvelope(**data)

    @staticmethod
    def _source_id_variants(*values: Any) -> List[str]:
        variants: set[str] = set()

        def add(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    add(item)
                return
            if not isinstance(value, (str, int, float)):
                return
            raw = str(value).strip().rstrip("/")
            if not raw or raw.lower() in {"none", "unknown"}:
                return
            variants.add(raw)
            compact = re.sub(r"\s+", "", raw)
            if compact:
                variants.add(compact)
            parsed = urlparse(raw)
            if parsed.scheme and parsed.netloc:
                path_parts = [part for part in parsed.path.split("/") if part]
                if path_parts:
                    add(path_parts[-1])
                return
            if raw.startswith("housing-ombudsman-"):
                add(raw.removeprefix("housing-ombudsman-"))
            tail_digits = re.search(r"(\d{6,})$", compact)
            if tail_digits:
                variants.add(tail_digits.group(1))

        for value in values:
            add(value)
        return sorted(variants)

    @staticmethod
    def _format_query_specs(query_specs: List[RagQuerySpec]) -> str:
        return "\n".join(
            f"{idx}. {spec.purpose}: {spec.query}"
            for idx, spec in enumerate(query_specs, 1)
        )

    @staticmethod
    def _contains_award_amount(text: str) -> bool:
        text_lower = text.lower()
        if re.search(r"\u00a3\s?\d", text):
            return True
        return bool(
            re.search(
                r"\b\d{2,5}\s?(?:gbp|pounds?)\b",
                text_lower,
            )
        )

    @staticmethod
    def _infer_ombudsman_finding(text: str) -> str:
        text_lower = text.lower()
        if "severe maladministration" in text_lower:
            return "severe_maladministration"
        if "no maladministration" in text_lower or "no service failure" in text_lower:
            return "no_maladministration"
        if "reasonable redress" in text_lower:
            return "reasonable_redress"
        if "maladministration" in text_lower:
            return "maladministration"
        if "service failure" in text_lower:
            return "service_failure"
        return "unknown"

    @staticmethod
    def _result_text(result: Any) -> str:
        return str(
            IssueRetriever._get_value(
                result,
                "chunk_text",
                IssueRetriever._get_value(
                    result,
                    "text",
                    IssueRetriever._get_value(result, "content", ""),
                ),
            )
        )

    @staticmethod
    def _result_case_key(result: Any) -> str:
        return str(
            IssueRetriever._get_value(
                result,
                "source_id",
                IssueRetriever._get_value(result, "case_reference", ""),
            )
            or ""
        )

    @staticmethod
    def _result_purposes(result: Any) -> set[str]:
        purposes = IssueRetriever._get_value(result, "retrieval_purposes", [])
        if not isinstance(purposes, list):
            purposes = [str(purposes)]
        single = IssueRetriever._get_value(result, "retrieval_purpose", None)
        if single:
            purposes.append(str(single))
        return {p for p in purposes if p}

    def _apply_temporal_decay(
        self, results: List[Any], issue: IssueContext
    ) -> List[Any]:
        scored: List[tuple[float, Any]] = []
        issue_tokens = issue.issue_type.value.replace("_", " ").lower().split()
        legislative_breaks = (
            {2015: "post_deregulation_act_2015", 2019: "post_tenant_fees_act_2019"}
            if issue.issue_type == IssueType.DEPOSIT_PROTECTION
            else None
        )

        for result in results:
            semantic_score = self._to_float(
                self._get_value(result, "semantic_score", 0.0)
            )
            bm25_score = self._to_float(self._get_value(result, "bm25_score", 0.0))
            year = self._extract_year(result)
            temporal = (
                temporal_relevance_score(
                    case_year=year,
                    legislative_breaks=legislative_breaks,
                )
                if year is not None
                else 0.0
            )

            text = str(
                self._get_value(
                    result,
                    "text",
                    self._get_value(
                        result,
                        "content",
                        self._get_value(result, "chunk_text", ""),
                    ),
                )
            ).lower()
            issue_match = 1.2 if all(token in text for token in issue_tokens) else 1.0

            final_score = (
                (0.55 * semantic_score)
                + (0.20 * bm25_score)
                + (0.15 * temporal)
                + (0.10 * issue_match)
            )
            self._set_value(result, "final_score", final_score)
            scored.append((final_score, result))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]

    def _apply_kg_filter(
        self, results: List[Any], kg_facts: KGFacts
    ) -> List[Any]:
        """Demote retrieved-case chunks whose text contradicts typed KG facts.

        Writes to both `combined_score` (read by IssuePredictor when formatting
        the prompt) and `final_score` (used for internal sorting). Soft demotion
        only — does not drop precedents below `min_cases_required` threshold.
        """
        adjusted: List[tuple[float, Any]] = []
        for r in results:
            score = self._to_float(
                self._get_value(
                    r,
                    "combined_score",
                    self._get_value(r, "final_score", 0.0),
                )
            )
            text = str(
                self._get_value(
                    r,
                    "text",
                    self._get_value(r, "chunk_text", ""),
                )
            ).lower()
            penalty = 0.0

            if kg_facts.deposit_protection_status == "protected_late":
                if any(p in text for p in DEPOSIT_LATE_CONTRADICTORS):
                    penalty += KG_CONTRADICTION_PENALTY
            elif kg_facts.deposit_protection_status == "not_protected":
                if any(p in text for p in DEPOSIT_NONE_CONTRADICTORS):
                    penalty += KG_CONTRADICTION_PENALTY

            if kg_facts.prescribed_information_status in (
                "provided_late",
                "not_provided",
            ):
                if any(p in text for p in PRESCRIBED_LATE_CONTRADICTORS):
                    penalty += KG_CONTRADICTION_PENALTY

            if kg_facts.check_in_inventory_baseline == "absent":
                if any(p in text for p in INVENTORY_ABSENT_CONTRADICTORS):
                    penalty += KG_CONTRADICTION_PENALTY

            adjusted_score = score + penalty
            self._set_value(r, "kg_filter_penalty", penalty)
            self._set_value(r, "combined_score", adjusted_score)
            self._set_value(r, "final_score", adjusted_score)
            adjusted.append((adjusted_score, r))

        adjusted.sort(key=lambda item: item[0], reverse=True)
        return [r for _, r in adjusted]

    def _determine_legislative_regime(
        self,
        results: List[Any],
        issue: IssueContext,
    ) -> str:
        if issue.issue_type != IssueType.DEPOSIT_PROTECTION:
            return "current"

        years = [
            year for year in (self._extract_year(result) for result in results) if year
        ]
        if not years:
            return "current"

        post_2019 = sum(1 for year in years if year > 2019)
        between_2015_2019 = sum(1 for year in years if 2015 <= year <= 2019)

        if post_2019 > len(years) / 2:
            return "post_tenant_fees_act_2019"
        if between_2015_2019 > len(years) / 2:
            return "post_deregulation_act_2015"
        return "current"

    @staticmethod
    def _extract_results(rag_result: Any) -> List[Any]:
        if rag_result is None:
            return []
        if isinstance(rag_result, list):
            return rag_result
        if isinstance(rag_result, dict):
            results = rag_result.get("results", [])
            return results if isinstance(results, list) else []
        results = getattr(rag_result, "results", [])
        return results if isinstance(results, list) else []

    @staticmethod
    def _retrieval_result_to_dict(result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "model_dump"):
            try:
                data = result.model_dump(mode="json")
            except TypeError:
                data = result.model_dump()
            if isinstance(data, dict):
                return data
        if hasattr(result, "dict"):
            data = result.dict()
            if isinstance(data, dict):
                return data

        fields = [
            "kind",
            "chunk_id",
            "proposition_id",
            "case_reference",
            "source_id",
            "source_kind",
            "chunk_text",
            "text",
            "content",
            "section_type",
            "semantic_score",
            "semantic_rank",
            "bm25_score",
            "bm25_rank",
            "combined_score",
            "rerank_score",
            "final_score",
            "year",
            "case_year",
            "region",
            "case_type",
            "paragraph",
        ]
        return {
            field: getattr(result, field)
            for field in fields
            if hasattr(result, field)
        }

    @staticmethod
    def _dedupe_results(results: List[Any]) -> List[Any]:
        deduped: List[Any] = []
        seen: Dict[tuple[str, str, str, str], Any] = {}
        for result in results:
            text = str(
                IssueRetriever._get_value(
                    result,
                    "chunk_text",
                    IssueRetriever._get_value(result, "text", ""),
                )
            )
            key = (
                str(IssueRetriever._get_value(result, "kind", "chunk")),
                str(
                    IssueRetriever._get_value(
                        result,
                        "chunk_id",
                        IssueRetriever._get_value(result, "proposition_id", ""),
                    )
                ),
                str(IssueRetriever._get_value(result, "case_reference", "")),
                text[:160],
            )
            existing = seen.get(key)
            if existing is not None:
                IssueRetriever._merge_retrieval_annotations(existing, result)
                continue
            seen[key] = result
            deduped.append(result)
        return deduped

    @staticmethod
    def _merge_retrieval_annotations(existing: Any, duplicate: Any) -> None:
        existing_purposes = IssueRetriever._get_value(
            existing,
            "retrieval_purposes",
            [],
        )
        if not isinstance(existing_purposes, list):
            existing_purposes = [str(existing_purposes)]
        for value in (
            IssueRetriever._get_value(existing, "retrieval_purpose", None),
            IssueRetriever._get_value(duplicate, "retrieval_purpose", None),
        ):
            if value and value not in existing_purposes:
                existing_purposes.append(str(value))
        if existing_purposes:
            IssueRetriever._set_value(
                existing,
                "retrieval_purposes",
                sorted(set(existing_purposes)),
            )

        if IssueRetriever._get_value(duplicate, "has_award_amount", False):
            IssueRetriever._set_value(existing, "has_award_amount", True)

        existing_finding = IssueRetriever._get_value(
            existing,
            "ombudsman_finding_signal",
            "unknown",
        )
        duplicate_finding = IssueRetriever._get_value(
            duplicate,
            "ombudsman_finding_signal",
            "unknown",
        )
        if existing_finding == "unknown" and duplicate_finding != "unknown":
            IssueRetriever._set_value(
                existing,
                "ombudsman_finding_signal",
                duplicate_finding,
            )

    @staticmethod
    def _extract_rag_confidence(rag_result: Any) -> float:
        if rag_result is None:
            return 0.0
        if isinstance(rag_result, dict):
            return IssueRetriever._to_float(rag_result.get("confidence", 0.0))
        return IssueRetriever._to_float(getattr(rag_result, "confidence", 0.0))

    @staticmethod
    def _extract_year(result: Any) -> Optional[int]:
        year_value = IssueRetriever._get_value(
            result,
            "year",
            IssueRetriever._get_value(result, "case_year", None),
        )
        try:
            year = int(year_value)
            return year if 1900 <= year <= 2100 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_optional_float(value: Any) -> Optional[float]:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _set_value(obj: Any, key: str, value: Any) -> None:
        if isinstance(obj, dict):
            obj[key] = value
            return
        try:
            setattr(obj, key, value)
        except Exception:
            return
