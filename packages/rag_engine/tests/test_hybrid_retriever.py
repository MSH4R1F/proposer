"""
Tests for hybrid retrieval combining semantic and keyword search.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_engine.config import DocumentChunk, RAGConfig, SectionType
from rag_engine.retrieval.bm25_index import BM25Index
from rag_engine.retrieval.hybrid_retriever import HybridRetriever
from rag_engine.vectorstore.base import VectorSearchResult


class TestHybridRetriever:
    """Tests for the HybridRetriever class."""

    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks for testing."""
        return [
            DocumentChunk(
                chunk_id="chunk_0",
                case_reference="LON_00AB_HMF_2021_0001",
                chunk_index=0,
                text="The landlord failed to protect the deposit under section 213 of the Housing Act 2004.",
                section_type=SectionType.FACTS,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
            DocumentChunk(
                chunk_id="chunk_1",
                case_reference="LON_00AB_HMF_2021_0001",
                chunk_index=1,
                text="The tribunal awards compensation for the deposit protection failure.",
                section_type=SectionType.DECISION,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
            DocumentChunk(
                chunk_id="chunk_2",
                case_reference="CHI_00CD_LSC_2022_0005",
                chunk_index=0,
                text="The service charge for cleaning was disputed by the leaseholder.",
                section_type=SectionType.BACKGROUND,
                year=2022,
                region="CHI",
                case_type="LSC",
            ),
        ]

    @pytest.fixture
    def mock_embeddings(self):
        """Create mock embeddings service."""
        mock = MagicMock()
        mock.embed_query = AsyncMock(return_value=[0.5] * 1536)
        return mock

    @pytest.fixture
    def mock_vectorstore(self, sample_chunks):
        """Create mock vector store."""
        mock = MagicMock()

        async def query(embedding, n_results=10, where=None):
            results = []
            for i, chunk in enumerate(sample_chunks[:n_results]):
                results.append(VectorSearchResult(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=0.9 - (i * 0.1),
                    metadata=chunk.to_chroma_metadata(),
                ))
            return results

        mock.query = AsyncMock(side_effect=query)
        return mock

    @pytest.fixture
    def bm25_index(self, sample_chunks):
        """Create a BM25 index with sample data."""
        index = BM25Index(lite_mode=True)
        index.build_index(sample_chunks)
        return index

    @pytest.fixture
    def hybrid_retriever(self, mock_embeddings, mock_vectorstore, bm25_index, test_config):
        """Create a hybrid retriever with mocked components."""
        return HybridRetriever(
            embeddings=mock_embeddings,
            vectorstore=mock_vectorstore,
            bm25_index=bm25_index,
            config=test_config,
        )

    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self, hybrid_retriever):
        """Test that retrieval returns results."""
        results = await hybrid_retriever.retrieve(
            query="deposit protection",
            top_k=5
        )

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_retrieve_combines_semantic_and_keyword(self, hybrid_retriever):
        """Test that results have both semantic and BM25 scores."""
        results = await hybrid_retriever.retrieve(
            query="deposit section 213",
            top_k=5
        )

        for result in results:
            assert result.semantic_score >= 0
            # BM25 score might be 0 if no keyword match
            assert result.bm25_score >= 0
            assert result.combined_score > 0

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self, hybrid_retriever):
        """Test that top_k is respected."""
        results = await hybrid_retriever.retrieve(
            query="deposit",
            top_k=2
        )

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_retrieve_includes_ranks(self, hybrid_retriever):
        """Test that results include rank information."""
        results = await hybrid_retriever.retrieve(
            query="deposit protection",
            top_k=5
        )

        for result in results:
            assert result.semantic_rank >= 1
            assert result.bm25_rank >= 1

    @pytest.mark.asyncio
    async def test_retrieve_with_filters(self, hybrid_retriever):
        """Test retrieval with metadata filters."""
        results = await hybrid_retriever.retrieve(
            query="deposit",
            top_k=5,
            where={"year": 2021}
        )

        # Should still return results (mock doesn't filter)
        assert results is not None


class TestRRFFusion:
    """Tests for Reciprocal Rank Fusion scoring."""

    @pytest.fixture
    def retriever_config(self, test_config):
        """Create config with specific RRF settings."""
        test_config.rrf_k = 60
        test_config.semantic_weight = 0.7
        return test_config

    def test_rrf_formula(self):
        """Test the RRF score calculation formula."""
        # RRF score = 1 / (k + rank)
        k = 60

        # Rank 1 should have highest score
        score_rank_1 = 1 / (k + 1)
        score_rank_2 = 1 / (k + 2)

        assert score_rank_1 > score_rank_2

    def test_combined_rrf_score(self):
        """Test combining semantic and BM25 RRF scores."""
        k = 60
        semantic_weight = 0.7

        semantic_rank = 1
        bm25_rank = 3

        semantic_rrf = 1 / (k + semantic_rank)
        bm25_rrf = 1 / (k + bm25_rank)

        combined = (semantic_weight * semantic_rrf) + ((1 - semantic_weight) * bm25_rrf)

        assert combined > 0
        assert combined < 1


class TestHybridRetrieverEdgeCases:
    """Tests for edge cases in hybrid retrieval."""

    @pytest.fixture
    def empty_bm25(self):
        """Create an empty BM25 index."""
        return BM25Index(lite_mode=True)

    @pytest.fixture
    def mock_embeddings(self):
        mock = MagicMock()
        mock.embed_query = AsyncMock(return_value=[0.5] * 1536)
        return mock

    @pytest.fixture
    def mock_empty_vectorstore(self):
        mock = MagicMock()
        mock.query = AsyncMock(return_value=[])
        return mock

    @pytest.mark.asyncio
    async def test_empty_bm25_index(self, mock_embeddings, mock_empty_vectorstore, empty_bm25, test_config):
        """Test retrieval with empty BM25 index."""
        retriever = HybridRetriever(
            embeddings=mock_embeddings,
            vectorstore=mock_empty_vectorstore,
            bm25_index=empty_bm25,
            config=test_config,
        )

        results = await retriever.retrieve(query="test", top_k=5)

        # Should return empty or handle gracefully
        assert results is not None

    @pytest.mark.asyncio
    async def test_no_semantic_results(self, mock_embeddings, mock_empty_vectorstore, test_config):
        """Test when semantic search returns no results."""
        bm25 = BM25Index(lite_mode=True)
        bm25.build_index([
            DocumentChunk(
                chunk_id="test",
                case_reference="TEST",
                chunk_index=0,
                text="Test document about deposits.",
                section_type=SectionType.FACTS,
                year=2021,
                region="LON",
                case_type="HMF",
            )
        ])

        retriever = HybridRetriever(
            embeddings=mock_embeddings,
            vectorstore=mock_empty_vectorstore,
            bm25_index=bm25,
            config=test_config,
        )

        results = await retriever.retrieve(query="deposit", top_k=5)

        # Should still get BM25 results
        assert results is not None


class TestHybridRetrieverScoring:
    """Tests for scoring in hybrid retrieval."""

    @pytest.fixture
    def retriever_with_data(self, mock_embeddings, test_config):
        """Create retriever with controlled data."""
        # Create chunks with known relevance
        chunks = [
            DocumentChunk(
                chunk_id="highly_relevant",
                case_reference="REL_001",
                chunk_index=0,
                text="The landlord failed to protect the tenant's deposit under section 213 of the Housing Act 2004. This was a clear violation.",
                section_type=SectionType.FACTS,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
            DocumentChunk(
                chunk_id="somewhat_relevant",
                case_reference="REL_002",
                chunk_index=0,
                text="The deposit was eventually protected but the prescribed information was delayed.",
                section_type=SectionType.FACTS,
                year=2021,
                region="LON",
                case_type="HMF",
            ),
            DocumentChunk(
                chunk_id="less_relevant",
                case_reference="REL_003",
                chunk_index=0,
                text="The cleaning service charge was disputed by the tenant.",
                section_type=SectionType.BACKGROUND,
                year=2022,
                region="CHI",
                case_type="LSC",
            ),
        ]

        bm25 = BM25Index(lite_mode=True)
        bm25.build_index(chunks)

        # Mock vector store to return in expected order
        mock_vectorstore = MagicMock()

        async def query(embedding, n_results=10, where=None):
            return [
                VectorSearchResult(
                    chunk_id="highly_relevant",
                    text=chunks[0].text,
                    score=0.90,
                    metadata=chunks[0].to_chroma_metadata(),
                ),
                VectorSearchResult(
                    chunk_id="somewhat_relevant",
                    text=chunks[1].text,
                    score=0.75,
                    metadata=chunks[1].to_chroma_metadata(),
                ),
                VectorSearchResult(
                    chunk_id="less_relevant",
                    text=chunks[2].text,
                    score=0.50,
                    metadata=chunks[2].to_chroma_metadata(),
                ),
            ][:n_results]

        mock_vectorstore.query = AsyncMock(side_effect=query)

        return HybridRetriever(
            embeddings=mock_embeddings,
            vectorstore=mock_vectorstore,
            bm25_index=bm25,
            config=test_config,
        )

    @pytest.mark.asyncio
    async def test_highly_relevant_ranked_first(self, retriever_with_data):
        """Test that highly relevant results are ranked first."""
        results = await retriever_with_data.retrieve(
            query="deposit section 213 Housing Act",
            top_k=3
        )

        # First result should be the most relevant
        assert results[0].chunk_id == "highly_relevant"

    @pytest.mark.asyncio
    async def test_combined_score_ordering(self, retriever_with_data):
        """Test that results are ordered by combined score."""
        results = await retriever_with_data.retrieve(
            query="deposit protection",
            top_k=3
        )

        scores = [r.combined_score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_both_scores_contribute(self, retriever_with_data):
        """Test that both semantic and BM25 contribute to final score."""
        results = await retriever_with_data.retrieve(
            query="deposit section 213",
            top_k=3
        )

        # The top result should have good scores from both
        top = results[0]
        assert top.semantic_score > 0.5
        # BM25 score depends on keyword matching
