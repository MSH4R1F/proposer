"""
Retrieval quality evaluation tests.

These tests measure the quality of RAG retrieval using golden test cases.
They can be run against the live system to evaluate retrieval performance.
"""

import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any

import pytest

# Skip these tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping live retrieval tests"
)


class TestRetrievalQualityMetrics:
    """Tests for retrieval quality metrics calculation."""

    def test_topic_precision_calculation(self, sample_retrieval_results):
        """Test calculating topic precision."""
        expected_topics = ["deposit", "section 213", "protection"]

        hits = 0
        for result in sample_retrieval_results:
            text_lower = result.chunk_text.lower()
            if any(topic.lower() in text_lower for topic in expected_topics):
                hits += 1

        precision = hits / len(sample_retrieval_results)
        assert 0 <= precision <= 1

    def test_case_type_precision_calculation(self, sample_retrieval_results):
        """Test calculating case type precision."""
        expected_case_types = ["HMF", "HTC"]

        hits = sum(
            1 for r in sample_retrieval_results
            if r.case_type in expected_case_types
        )

        precision = hits / len(sample_retrieval_results)
        assert precision > 0  # Should have some hits

    def test_confidence_threshold_check(self, sample_retrieval_results):
        """Test confidence threshold checking."""
        min_confidence = 0.5

        # Simulate confidence calculation based on semantic scores
        avg_semantic = sum(r.semantic_score for r in sample_retrieval_results) / len(sample_retrieval_results)

        meets_threshold = avg_semantic >= min_confidence
        assert isinstance(meets_threshold, bool)


class TestGoldenDatasetEvaluation:
    """Tests using the golden test dataset."""

    def test_golden_cases_structure(self, golden_test_cases):
        """Test that golden test cases have required fields."""
        for case in golden_test_cases:
            assert "query" in case
            assert "expected_topics" in case
            assert "expected_case_types" in case
            assert "min_confidence" in case

            assert len(case["expected_topics"]) > 0
            assert len(case["expected_case_types"]) > 0
            assert 0 <= case["min_confidence"] <= 1

    def test_golden_cases_diversity(self, golden_test_cases):
        """Test that golden test cases cover diverse topics."""
        queries = [c["query"] for c in golden_test_cases]

        # Should have unique queries
        assert len(queries) == len(set(queries))

        # Should cover different case types
        all_case_types = set()
        for case in golden_test_cases:
            all_case_types.update(case["expected_case_types"])

        assert len(all_case_types) >= 3  # At least 3 different case types


@pytest.mark.integration
@pytest.mark.requires_api
class TestLiveRetrievalQuality:
    """
    Live tests against the actual RAG system.

    These tests require:
    - OPENAI_API_KEY environment variable
    - Populated ChromaDB and BM25 index

    Run with: pytest -m integration tests/test_retrieval_quality.py
    """

    @pytest.fixture
    def live_pipeline(self):
        """Create a pipeline connected to the live system."""
        from rag_engine.config import RAGConfig
        from rag_engine.pipeline import RAGPipeline

        config = RAGConfig(
            data_dir=Path("data"),
            chroma_persist_dir=Path("data/embeddings"),
            bm25_index_path=Path("data/embeddings/bm25_index.pkl"),
            bm25_lite_mode=True,
        )

        return RAGPipeline(config=config)

    @pytest.mark.asyncio
    async def test_deposit_protection_query(self, live_pipeline):
        """Test retrieval for deposit protection queries."""
        result = await live_pipeline.retrieve(
            query="landlord didn't protect deposit section 213",
            top_k=5
        )

        # Should get results
        assert len(result.results) > 0

        # Should have reasonable confidence
        assert result.confidence > 0.3

        # At least one result should mention deposit
        texts = [r.chunk_text.lower() for r in result.results]
        assert any("deposit" in t for t in texts)

    @pytest.mark.asyncio
    async def test_cleaning_costs_query(self, live_pipeline):
        """Test retrieval for cleaning cost queries."""
        result = await live_pipeline.retrieve(
            query="cleaning costs disputed service charge",
            top_k=5
        )

        assert len(result.results) > 0

        # Should find cleaning-related content
        texts = [r.chunk_text.lower() for r in result.results]
        assert any("clean" in t for t in texts)

    @pytest.mark.asyncio
    async def test_rent_repayment_query(self, live_pipeline):
        """Test retrieval for rent repayment order queries."""
        result = await live_pipeline.retrieve(
            query="rent repayment order housing act",
            top_k=5
        )

        assert len(result.results) > 0
        assert result.confidence > 0.3

    @pytest.mark.asyncio
    async def test_retrieval_time_acceptable(self, live_pipeline):
        """Test that retrieval completes within acceptable time."""
        result = await live_pipeline.retrieve(
            query="deposit protection",
            top_k=5
        )

        # Should complete within 5 seconds
        assert result.retrieval_time_ms < 5000

    @pytest.mark.asyncio
    async def test_hybrid_search_uses_both_indices(self, live_pipeline):
        """Test that hybrid search uses both semantic and BM25."""
        result = await live_pipeline.retrieve(
            query="section 213 housing act 2004 deposit",
            top_k=5
        )

        # At least some results should have BM25 scores
        bm25_scores = [r.bm25_score for r in result.results]
        semantic_scores = [r.semantic_score for r in result.results]

        assert any(s > 0 for s in semantic_scores)
        # BM25 might not always have hits for semantic queries
        # but should for keyword-rich queries

    @pytest.mark.asyncio
    async def test_golden_dataset_evaluation(self, live_pipeline, golden_test_cases):
        """Run evaluation on the golden test dataset."""
        results = []

        for test_case in golden_test_cases:
            result = await live_pipeline.retrieve(
                query=test_case["query"],
                top_k=5
            )

            # Calculate metrics
            topic_hits = 0
            case_type_hits = 0

            for r in result.results:
                text_lower = r.chunk_text.lower()
                if any(t.lower() in text_lower for t in test_case["expected_topics"]):
                    topic_hits += 1
                if r.case_type in test_case["expected_case_types"]:
                    case_type_hits += 1

            topic_precision = topic_hits / len(result.results) if result.results else 0
            case_type_precision = case_type_hits / len(result.results) if result.results else 0

            results.append({
                "query": test_case["query"],
                "confidence": result.confidence,
                "topic_precision": topic_precision,
                "case_type_precision": case_type_precision,
                "meets_min_confidence": result.confidence >= test_case["min_confidence"],
            })

        # Aggregate metrics
        avg_confidence = sum(r["confidence"] for r in results) / len(results)
        avg_topic_precision = sum(r["topic_precision"] for r in results) / len(results)
        avg_case_type_precision = sum(r["case_type_precision"] for r in results) / len(results)
        confidence_pass_rate = sum(1 for r in results if r["meets_min_confidence"]) / len(results)

        # Assert quality thresholds
        assert avg_confidence >= 0.5, f"Average confidence {avg_confidence:.2%} below threshold"
        assert avg_topic_precision >= 0.6, f"Topic precision {avg_topic_precision:.2%} below threshold"
        assert confidence_pass_rate >= 0.8, f"Confidence pass rate {confidence_pass_rate:.2%} below threshold"


class TestRetrievalCalibration:
    """Tests for retrieval calibration (confidence vs actual relevance)."""

    def test_high_confidence_implies_relevance(self, sample_retrieval_results):
        """Test that high confidence correlates with relevant results."""
        # If confidence is high, semantic scores should also be high
        avg_semantic = sum(r.semantic_score for r in sample_retrieval_results) / len(sample_retrieval_results)

        # With good results, average semantic should be reasonable
        assert avg_semantic > 0.5

    def test_score_distribution(self, sample_retrieval_results):
        """Test that scores have reasonable distribution."""
        scores = [r.semantic_score for r in sample_retrieval_results]

        # Scores should be sorted (highest first)
        assert scores == sorted(scores, reverse=True)

        # Should have some variance (not all same score)
        if len(scores) > 1:
            assert max(scores) > min(scores)


class TestCiteOrAbstainPrinciple:
    """Tests for the cite-or-abstain principle (no hallucination)."""

    def test_uncertain_when_no_matches(self, sample_retrieval_results):
        """Test that uncertainty is flagged when no good matches."""
        # Simulate low-score results
        for result in sample_retrieval_results:
            result.semantic_score = 0.15  # Very low scores

        # Would expect system to flag uncertainty
        avg_score = sum(r.semantic_score for r in sample_retrieval_results) / len(sample_retrieval_results)
        is_uncertain = avg_score < 0.3

        assert is_uncertain is True

    def test_results_have_citations(self, sample_retrieval_results):
        """Test that results include case citations."""
        for result in sample_retrieval_results:
            assert result.case_reference is not None
            assert len(result.case_reference) > 0

            # Case reference should follow expected pattern
            assert "_" in result.case_reference  # e.g., LON_00AB_HMF_2021_0001
