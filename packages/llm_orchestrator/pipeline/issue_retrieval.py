import asyncio
from typing import Any, Dict, List, Optional

import structlog

from ..models.case_file import CaseFile
from ..models.prediction_v2 import IssueContext, IssueRetrievalResult, IssueType

logger = structlog.get_logger()


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
    def __init__(self, rag_pipeline: Any, min_cases_required: int = 3):
        self.rag = rag_pipeline
        self.min_cases_required = min_cases_required

    async def retrieve_all(
        self,
        issues: List[IssueContext],
        case_file: CaseFile,
        top_k: int = 10,
    ) -> Dict[IssueType, IssueRetrievalResult]:
        tasks = [self._retrieve_for_issue(issue, case_file, top_k) for issue in issues]
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
    ) -> IssueRetrievalResult:
        query = self._build_issue_query(issue, case_file)
        rag_result = await self.rag.retrieve(
            query=query,
            top_k=top_k + 5,
            query_region=case_file.property.region,
        )

        raw_results = self._extract_results(rag_result)
        reranked = self._apply_temporal_decay(raw_results, issue)
        trimmed_results = reranked[:top_k]

        temporal_distribution: Dict[int, int] = {}
        for result in trimmed_results:
            year = self._extract_year(result)
            if year is not None:
                temporal_distribution[year] = temporal_distribution.get(year, 0) + 1

        legislative_regime = self._determine_legislative_regime(trimmed_results, issue)
        rag_confidence = self._extract_rag_confidence(rag_result)

        return IssueRetrievalResult(
            issue_type=issue.issue_type,
            query_used=query,
            results=trimmed_results,
            rag_confidence=rag_confidence,
            temporal_distribution=temporal_distribution,
            legislative_regime=legislative_regime,
            is_sufficient=len(trimmed_results) >= self.min_cases_required,
        )

    def _build_issue_query(self, issue: IssueContext, case_file: CaseFile) -> str:
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
