import re
from typing import Dict, List, Set, Tuple

import structlog

from ..models.prediction_v2 import (
    Citation,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
    VerificationResult,
)

logger = structlog.get_logger()


def normalize_case_ref(ref: str) -> str:
    cleaned = (ref or "").strip().upper()
    cleaned = re.sub(r"/+", "/", cleaned)
    cleaned = cleaned.strip(" .,;:!?'\"()[]{}")

    parts = cleaned.split("/")
    normalized_parts: List[str] = []
    for part in parts:
        if re.fullmatch(r"\d+", part):
            stripped = part.lstrip("0")
            normalized_parts.append(stripped if stripped else "0")
        else:
            normalized_parts.append(part)
    return "/".join(normalized_parts)


class CitationVerifier:
    @staticmethod
    def empty_verification() -> VerificationResult:
        """Vacuously-valid result for modes that don't run retrieval (LLM_ONLY, KG_ONLY).

        Used by SHA-33 ablation paths where there are no retrieved cases to verify
        citations against, and the prompt forces an empty supporting_cases list.
        """
        return VerificationResult(
            verified_citations=[],
            removed_citations=[],
            removal_rate=0.0,
            needs_reprediction=False,
            all_citations_valid=True,
        )

    def verify(
        self,
        issue_predictions: List[IssuePrediction],
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
    ) -> Tuple[List[IssuePrediction], VerificationResult]:
        valid_refs: Set[str] = set()
        for retrieval in retrieval_results.values():
            for result in retrieval.results:
                case_reference = self._get_value(result, "case_reference", "")
                normalized_ref = normalize_case_ref(str(case_reference))
                if normalized_ref:
                    valid_refs.add(normalized_ref)

        verified_citations: List[Citation] = []
        removed_citations: List[Citation] = []
        total_citations = 0

        for prediction in issue_predictions:
            kept: List[Citation] = []
            for citation in prediction.supporting_cases:
                total_citations += 1
                normalized = normalize_case_ref(citation.case_reference)
                if normalized in valid_refs:
                    citation.verified = True
                    verified_citations.append(citation)
                    kept.append(citation)
                else:
                    citation.verified = False
                    removed_citations.append(citation)
            prediction.supporting_cases = kept

        removal_rate = (
            len(removed_citations) / total_citations if total_citations > 0 else 0.0
        )
        verification_result = VerificationResult(
            verified_citations=verified_citations,
            removed_citations=removed_citations,
            removal_rate=removal_rate,
            needs_reprediction=removal_rate > 0.3,
            all_citations_valid=len(removed_citations) == 0,
        )

        logger.info(
            "citation_verification_completed",
            total_citations=total_citations,
            verified=len(verified_citations),
            removed=len(removed_citations),
            removal_rate=removal_rate,
            needs_reprediction=verification_result.needs_reprediction,
        )

        return issue_predictions, verification_result

    @staticmethod
    def _get_value(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
