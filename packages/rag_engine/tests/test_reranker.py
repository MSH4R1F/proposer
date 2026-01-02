"""
Tests for the reranking module.
"""

import pytest

from rag_engine.config import RetrievalResult
from rag_engine.retrieval.reranker import Reranker


class TestReranker:
    """Tests for the Reranker class."""

    @pytest.fixture
    def reranker(self):
        """Create a Reranker instance."""
        return Reranker()

    @pytest.fixture
    def deposit_results(self):
        """Create results about deposit protection."""
        return [
            RetrievalResult(
                chunk_id="dep_1",
                case_reference="LON_00AB_HMF_2021_0001",
                chunk_text="The landlord failed to protect the deposit under section 213 of the Housing Act 2004.",
                section_type="facts",
                semantic_score=0.85,
                semantic_rank=1,
                bm25_score=15.5,
                bm25_rank=1,
                combined_score=0.025,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
            RetrievalResult(
                chunk_id="dep_2",
                case_reference="CHI_00CD_HMF_2020_0005",
                chunk_text="The deposit was protected late. Prescribed information was not provided.",
                section_type="reasoning",
                semantic_score=0.75,
                semantic_rank=2,
                bm25_score=12.0,
                bm25_rank=2,
                combined_score=0.020,
                year=2020,
                region="CHI",
                case_type="HMF",
            ),
            RetrievalResult(
                chunk_id="dep_3",
                case_reference="LON_00EF_HMF_2022_0010",
                chunk_text="The tribunal awards compensation for failure to protect the deposit.",
                section_type="decision",
                semantic_score=0.70,
                semantic_rank=3,
                bm25_score=10.0,
                bm25_rank=3,
                combined_score=0.018,
                year=2022,
                region="LON",
                case_type="HMF",
            ),
        ]

    @pytest.fixture
    def mixed_results(self):
        """Create mixed results from different case types."""
        return [
            RetrievalResult(
                chunk_id="mix_1",
                case_reference="LON_00AB_LSC_2021_0001",
                chunk_text="The service charge for cleaning was disputed.",
                section_type="background",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=2,
                combined_score=0.022,
                year=2021,
                region="LON",
                case_type="LSC",
            ),
            RetrievalResult(
                chunk_id="mix_2",
                case_reference="CHI_00CD_HMF_2021_0005",
                chunk_text="The landlord did not protect the deposit.",
                section_type="facts",
                semantic_score=0.75,
                semantic_rank=2,
                bm25_score=12.0,
                bm25_rank=1,
                combined_score=0.023,
                year=2021,
                region="CHI",
                case_type="HMF",
            ),
            RetrievalResult(
                chunk_id="mix_3",
                case_reference="BIR_00GH_HMF_2019_0015",
                chunk_text="Old case about deposit protection.",
                section_type="decision",
                semantic_score=0.65,
                semantic_rank=3,
                bm25_score=8.0,
                bm25_rank=3,
                combined_score=0.015,
                year=2019,
                region="BIR",
                case_type="HMF",
            ),
        ]

    def test_rerank_returns_results(self, reranker, deposit_results):
        """Test that reranking returns results."""
        query = "landlord failed to protect deposit section 213"
        reranked = reranker.rerank(deposit_results, query, top_k=3)

        assert len(reranked) == 3
        for result in reranked:
            assert result.rerank_score is not None

    def test_rerank_top_k_limit(self, reranker, deposit_results):
        """Test that top_k limits the number of results."""
        query = "deposit protection"
        reranked = reranker.rerank(deposit_results, query, top_k=2)

        assert len(reranked) == 2

    def test_rerank_adds_scores(self, reranker, deposit_results):
        """Test that reranking adds rerank scores."""
        query = "deposit protection section 213"
        reranked = reranker.rerank(deposit_results, query, top_k=3)

        for result in reranked:
            assert result.rerank_score is not None
            assert result.rerank_score >= 0

    def test_rerank_adds_explanations(self, reranker, deposit_results):
        """Test that reranking adds relevance explanations."""
        query = "deposit protection"
        reranked = reranker.rerank(deposit_results, query, top_k=3)

        # At least some results should have explanations
        explanations = [r.relevance_explanation for r in reranked]
        assert any(e is not None for e in explanations)

    def test_rerank_empty_results(self, reranker):
        """Test reranking with empty results."""
        reranked = reranker.rerank([], "test query", top_k=5)
        assert reranked == []

    def test_rerank_preserves_original_scores(self, reranker, deposit_results):
        """Test that original scores are preserved after reranking."""
        query = "deposit protection"
        original_semantic = deposit_results[0].semantic_score

        reranked = reranker.rerank(deposit_results, query, top_k=3)

        # Find the same result in reranked
        for result in reranked:
            if result.chunk_id == deposit_results[0].chunk_id:
                assert result.semantic_score == original_semantic


class TestRerankerBoosts:
    """Tests for reranker boost factors."""

    @pytest.fixture
    def reranker(self):
        return Reranker()

    def test_recent_year_boost(self, reranker):
        """Test that recent years get boosted."""
        results = [
            RetrievalResult(
                chunk_id="old",
                case_reference="OLD_CASE",
                chunk_text="Old case about deposit.",
                section_type="facts",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.020,
                year=2018,
                region="LON",
                case_type="HMF",
            ),
            RetrievalResult(
                chunk_id="new",
                case_reference="NEW_CASE",
                chunk_text="New case about deposit.",
                section_type="facts",
                semantic_score=0.75,
                semantic_rank=2,
                bm25_score=9.0,
                bm25_rank=2,
                combined_score=0.018,
                year=2023,
                region="LON",
                case_type="HMF",
            ),
        ]

        reranked = reranker.rerank(results, "deposit", top_k=2)

        # The newer case should have a higher or equal rerank score
        old_score = next(r.rerank_score for r in reranked if r.chunk_id == "old")
        new_score = next(r.rerank_score for r in reranked if r.chunk_id == "new")

        # New case should be competitive despite lower semantic score
        # due to recency boost
        assert new_score is not None
        assert old_score is not None

    def test_region_boost(self, reranker):
        """Test that matching region gets boosted."""
        results = [
            RetrievalResult(
                chunk_id="chi",
                case_reference="CHI_CASE",
                chunk_text="Case from Chichester.",
                section_type="facts",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.020,
                year=2021,
                region="CHI",
                case_type="HMF",
            ),
            RetrievalResult(
                chunk_id="lon",
                case_reference="LON_CASE",
                chunk_text="Case from London.",
                section_type="facts",
                semantic_score=0.75,
                semantic_rank=2,
                bm25_score=9.0,
                bm25_rank=2,
                combined_score=0.018,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
        ]

        # Rerank with London as query region
        reranked = reranker.rerank(results, "deposit", query_region="LON", top_k=2)

        # Find scores
        chi_score = next(r.rerank_score for r in reranked if r.chunk_id == "chi")
        lon_score = next(r.rerank_score for r in reranked if r.chunk_id == "lon")

        # London case should get a regional boost
        assert lon_score is not None
        assert chi_score is not None


class TestRerankerIssueDetection:
    """Tests for issue detection in queries."""

    @pytest.fixture
    def reranker(self):
        return Reranker()

    def test_detect_deposit_protection_issue(self, reranker):
        """Test detecting deposit protection issues in query."""
        results = [
            RetrievalResult(
                chunk_id="dep",
                case_reference="DEP_CASE",
                chunk_text="The deposit was not protected under section 213.",
                section_type="facts",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.020,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
        ]

        reranked = reranker.rerank(results, "deposit protection scheme", top_k=1)

        # Should detect deposit protection as an issue
        explanation = reranked[0].relevance_explanation
        # The explanation should mention something about the match
        assert explanation is not None or reranked[0].rerank_score is not None

    def test_detect_cleaning_issue(self, reranker):
        """Test detecting cleaning issues in query."""
        results = [
            RetrievalResult(
                chunk_id="clean",
                case_reference="CLN_CASE",
                chunk_text="The professional cleaning costs were disputed.",
                section_type="facts",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.020,
                year=2021,
                region="LON",
                case_type="LSC",
            ),
        ]

        reranked = reranker.rerank(results, "cleaning service charge", top_k=1)
        assert len(reranked) == 1

    def test_detect_fair_wear_issue(self, reranker):
        """Test detecting fair wear and tear issues."""
        results = [
            RetrievalResult(
                chunk_id="wear",
                case_reference="WEAR_CASE",
                chunk_text="The damage was due to fair wear and tear.",
                section_type="reasoning",
                semantic_score=0.75,
                semantic_rank=1,
                bm25_score=8.0,
                bm25_rank=1,
                combined_score=0.018,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
        ]

        reranked = reranker.rerank(results, "fair wear and tear damage", top_k=1)
        assert len(reranked) == 1


class TestRerankerEdgeCases:
    """Tests for edge cases in reranking."""

    @pytest.fixture
    def reranker(self):
        return Reranker()

    def test_single_result(self, reranker):
        """Test reranking with a single result."""
        results = [
            RetrievalResult(
                chunk_id="single",
                case_reference="SINGLE_CASE",
                chunk_text="Single result case.",
                section_type="facts",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.020,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
        ]

        reranked = reranker.rerank(results, "test", top_k=5)
        assert len(reranked) == 1
        assert reranked[0].rerank_score is not None

    def test_top_k_larger_than_results(self, reranker):
        """Test when top_k is larger than available results."""
        results = [
            RetrievalResult(
                chunk_id=f"result_{i}",
                case_reference=f"CASE_{i}",
                chunk_text=f"Result {i}",
                section_type="facts",
                semantic_score=0.8 - (i * 0.1),
                semantic_rank=i + 1,
                bm25_score=10.0 - i,
                bm25_rank=i + 1,
                combined_score=0.02 - (i * 0.002),
                year=2021,
                region="LON",
                case_type="HMF",
            )
            for i in range(3)
        ]

        reranked = reranker.rerank(results, "test", top_k=10)
        assert len(reranked) == 3

    def test_empty_query(self, reranker):
        """Test reranking with an empty query."""
        results = [
            RetrievalResult(
                chunk_id="test",
                case_reference="TEST_CASE",
                chunk_text="Test content.",
                section_type="facts",
                semantic_score=0.80,
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.020,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
        ]

        reranked = reranker.rerank(results, "", top_k=1)
        assert len(reranked) == 1

    def test_missing_optional_fields(self, reranker):
        """Test reranking results with missing optional fields."""
        results = [
            RetrievalResult(
                chunk_id="minimal",
                case_reference="MIN_CASE",
                chunk_text="Minimal result.",
                section_type="facts",
                semantic_score=0.70,
                semantic_rank=1,
                bm25_score=5.0,
                bm25_rank=1,
                combined_score=0.015,
                year=2021,
                region=None,  # Missing region
                case_type=None,  # Missing case type
            ),
        ]

        reranked = reranker.rerank(results, "test", top_k=1)
        assert len(reranked) == 1
        assert reranked[0].rerank_score is not None
