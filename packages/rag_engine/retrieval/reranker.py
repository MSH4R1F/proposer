"""
Custom re-ranking for legal case retrieval.

Re-ranks retrieved results based on domain-specific factors:
- Issue type matching (deposit protection, cleaning, damage, etc.)
- Temporal relevance (recent cases weighted higher)
- Region similarity (same tribunal region preferred)
- Evidence type matching
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Set

import structlog

from ..config import DEPOSIT_ISSUE_KEYWORDS, RetrievalResult

logger = structlog.get_logger()


class Reranker:
    """
    Domain-specific re-ranking for legal case retrieval.

    Adjusts hybrid search scores based on:
    1. Issue type match (most important)
    2. Temporal relevance
    3. Region match
    4. Evidence type similarity
    """

    # Weights for different re-ranking factors
    WEIGHTS = {
        "issue_match": 0.4,
        "temporal": 0.2,
        "region": 0.1,
        "evidence": 0.2,
        "original_score": 0.1,
    }

    # Current year for temporal scoring
    CURRENT_YEAR = datetime.now().year

    def __init__(
        self,
        issue_weight: float = 0.4,
        temporal_weight: float = 0.2,
        region_weight: float = 0.1,
        evidence_weight: float = 0.2,
        score_weight: float = 0.1
    ) -> None:
        """
        Initialize the reranker.

        Args:
            issue_weight: Weight for issue type matching
            temporal_weight: Weight for temporal relevance
            region_weight: Weight for region matching
            evidence_weight: Weight for evidence type matching
            score_weight: Weight for original retrieval score
        """
        self.weights = {
            "issue_match": issue_weight,
            "temporal": temporal_weight,
            "region": region_weight,
            "evidence": evidence_weight,
            "original_score": score_weight,
        }

        # Normalize weights to sum to 1
        total = sum(self.weights.values())
        self.weights = {k: v / total for k, v in self.weights.items()}

    def rerank(
        self,
        results: List[RetrievalResult],
        query: str,
        query_region: Optional[str] = None,
        top_k: int = 5
    ) -> List[RetrievalResult]:
        """
        Re-rank retrieval results based on domain factors.

        Args:
            results: Initial retrieval results
            query: Original search query
            query_region: Optional user's region for matching
            top_k: Number of results to return

        Returns:
            Re-ranked results with updated scores and explanations
        """
        if not results:
            return []

        # Detect issues in query
        query_issues = self._detect_issues(query)

        # Detect evidence mentions in query
        query_evidence = self._detect_evidence_types(query)

        # Score each result
        scored_results = []
        for result in results:
            scores = self._calculate_scores(
                result,
                query_issues,
                query_evidence,
                query_region
            )

            # Calculate weighted combined score
            rerank_score = sum(
                scores[factor] * weight
                for factor, weight in self.weights.items()
            )

            # Update result with rerank score
            result.rerank_score = rerank_score

            # Generate relevance explanation
            result.relevance_explanation = self._generate_explanation(
                result,
                query_issues,
                scores
            )

            scored_results.append((result, rerank_score))

        # Sort by rerank score
        scored_results.sort(key=lambda x: x[1], reverse=True)

        # Return top_k results
        reranked = [r for r, _ in scored_results[:top_k]]

        logger.debug(
            "reranking_complete",
            input_count=len(results),
            output_count=len(reranked),
            query_issues=list(query_issues),
            top_rerank_score=reranked[0].rerank_score if reranked else 0
        )

        return reranked

    def _calculate_scores(
        self,
        result: RetrievalResult,
        query_issues: Set[str],
        query_evidence: Set[str],
        query_region: Optional[str]
    ) -> Dict[str, float]:
        """
        Calculate individual factor scores for a result.

        Returns:
            Dict mapping factor names to scores (0-1)
        """
        # Detect issues in result text
        result_issues = self._detect_issues(result.chunk_text)
        result_evidence = self._detect_evidence_types(result.chunk_text)

        scores = {}

        # Issue match score (Jaccard similarity)
        if query_issues and result_issues:
            intersection = query_issues & result_issues
            union = query_issues | result_issues
            scores["issue_match"] = len(intersection) / len(union)
        elif query_issues or result_issues:
            scores["issue_match"] = 0.3  # Partial credit if one has issues
        else:
            scores["issue_match"] = 0.5  # Neutral if neither has issues

        # Temporal score (newer = better, with decay)
        year_diff = self.CURRENT_YEAR - result.year
        if year_diff <= 0:
            scores["temporal"] = 1.0
        elif year_diff <= 2:
            scores["temporal"] = 0.9
        elif year_diff <= 5:
            scores["temporal"] = 0.7
        else:
            scores["temporal"] = max(0.3, 1.0 - (year_diff * 0.05))

        # Region match score
        if query_region and result.region:
            if query_region.upper() == result.region.upper():
                scores["region"] = 1.0
            else:
                scores["region"] = 0.5  # Different region
        else:
            scores["region"] = 0.5  # No region info

        # Evidence match score
        if query_evidence and result_evidence:
            intersection = query_evidence & result_evidence
            union = query_evidence | result_evidence
            scores["evidence"] = len(intersection) / len(union)
        elif query_evidence or result_evidence:
            scores["evidence"] = 0.3
        else:
            scores["evidence"] = 0.5

        # Original score (normalized)
        # Combined score is already normalized from hybrid retrieval
        scores["original_score"] = min(1.0, result.combined_score * 10)

        return scores

    def _detect_issues(self, text: str) -> Set[str]:
        """
        Detect legal issues mentioned in text.

        Args:
            text: Text to analyze

        Returns:
            Set of detected issue categories
        """
        if not text:
            return set()

        text_lower = text.lower()
        detected = set()

        for issue_type, keywords in DEPOSIT_ISSUE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    detected.add(issue_type)
                    break  # One match is enough for this issue type

        return detected

    def _detect_evidence_types(self, text: str) -> Set[str]:
        """
        Detect evidence type mentions in text.

        Args:
            text: Text to analyze

        Returns:
            Set of detected evidence types
        """
        if not text:
            return set()

        text_lower = text.lower()
        evidence_types = set()

        evidence_keywords = {
            "inventory": ["inventory", "schedule of condition", "check-in report", "check-out report"],
            "photographs": ["photograph", "photo", "picture", "image"],
            "receipts": ["receipt", "invoice", "quotation", "quote", "estimate"],
            "correspondence": ["email", "letter", "text message", "whatsapp", "correspondence"],
            "witness": ["witness", "testimony", "statement"],
            "contract": ["tenancy agreement", "contract", "lease"],
        }

        for evidence_type, keywords in evidence_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    evidence_types.add(evidence_type)
                    break

        return evidence_types

    def _generate_explanation(
        self,
        result: RetrievalResult,
        query_issues: Set[str],
        scores: Dict[str, float]
    ) -> str:
        """
        Generate a human-readable explanation of relevance.

        Args:
            result: The retrieval result
            query_issues: Issues detected in query
            scores: Individual factor scores

        Returns:
            Explanation string
        """
        explanations = []

        # Issue match explanation
        result_issues = self._detect_issues(result.chunk_text)
        matched_issues = query_issues & result_issues

        if matched_issues:
            issue_names = [i.replace("_", " ") for i in matched_issues]
            explanations.append(f"Matches issues: {', '.join(issue_names)}")

        # Temporal explanation
        if scores["temporal"] >= 0.9:
            explanations.append(f"Recent case ({result.year})")
        elif scores["temporal"] >= 0.7:
            explanations.append(f"Relatively recent ({result.year})")

        # Region explanation
        if scores["region"] >= 0.9 and result.region:
            explanations.append(f"Same region ({result.region})")

        # High semantic score
        if result.semantic_score >= 0.7:
            explanations.append("Strong semantic similarity")
        elif result.semantic_score >= 0.5:
            explanations.append("Good semantic match")

        # High keyword match
        if result.bm25_score > 0 and result.bm25_rank <= 5:
            explanations.append("Strong keyword match")

        if not explanations:
            explanations.append("General relevance")

        return "; ".join(explanations)

    def get_stats(self) -> Dict:
        """Get reranker configuration."""
        return {"weights": self.weights}
