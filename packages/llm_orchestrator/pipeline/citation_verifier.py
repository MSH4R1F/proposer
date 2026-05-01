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
        valid_chunk_refs: Set[str] = set()
        valid_propositions_by_id: Dict[str, object] = {}
        valid_proposition_results: List[object] = []
        for retrieval in retrieval_results.values():
            for result in retrieval.results:
                case_reference = self._get_value(result, "case_reference", "")
                normalized_ref = normalize_case_ref(str(case_reference))
                proposition_id = self._get_value(result, "proposition_id", None)
                kind = str(self._get_value(result, "kind", "")).lower()
                if kind == "proposition" or proposition_id:
                    if proposition_id:
                        valid_propositions_by_id[str(proposition_id)] = result
                    valid_proposition_results.append(result)
                elif normalized_ref:
                    valid_chunk_refs.add(normalized_ref)

        verified_citations: List[Citation] = []
        removed_citations: List[Citation] = []
        total_citations = 0

        for prediction in issue_predictions:
            kept: List[Citation] = []
            for citation in prediction.supporting_cases:
                total_citations += 1
                normalized = normalize_case_ref(citation.case_reference)
                proposition_verified = self._verify_proposition_citation(
                    citation,
                    valid_propositions_by_id,
                    valid_proposition_results,
                )
                if proposition_verified or normalized in valid_chunk_refs:
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

    def _verify_proposition_citation(
        self,
        citation: Citation,
        by_id: Dict[str, object],
        results: List[object],
    ) -> bool:
        if citation.proposition_id:
            result = by_id.get(str(citation.proposition_id))
            if result is None:
                return False
            result_ref = normalize_case_ref(
                str(self._get_value(result, "case_reference", ""))
            )
            if normalize_case_ref(citation.case_reference) != result_ref:
                return False
            if citation.paragraph:
                result_paragraph = str(
                    self._get_value(
                        result,
                        "paragraph",
                        self._get_value(result, "paragraph_ref", ""),
                    )
                    or ""
                ).strip()
                if result_paragraph and citation.paragraph.strip() != result_paragraph:
                    return False
            return self._citation_quote_matches_result(citation, result)

        normalized_ref = normalize_case_ref(citation.case_reference)
        paragraph = (citation.paragraph or "").strip()
        for result in results:
            result_ref = normalize_case_ref(
                str(self._get_value(result, "case_reference", ""))
            )
            if result_ref != normalized_ref:
                continue
            result_paragraph = str(
                self._get_value(
                    result,
                    "paragraph",
                    self._get_value(result, "paragraph_ref", ""),
                )
                or ""
            ).strip()
            if paragraph and result_paragraph and paragraph != result_paragraph:
                continue
            if self._citation_quote_matches_result(citation, result):
                return True
        return False

    def _citation_quote_matches_result(self, citation: Citation, result: object) -> bool:
        citation_quote = _normalize_quote(citation.quote)
        if not citation_quote:
            return False
        result_quote = _normalize_quote(
            str(
                self._get_value(
                    result,
                    "quote",
                    self._get_value(
                        result,
                        "source_passage",
                        self._get_value(result, "chunk_text", ""),
                    ),
                )
            )
        )
        if not result_quote:
            return False
        return citation_quote in result_quote or result_quote in citation_quote


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())
