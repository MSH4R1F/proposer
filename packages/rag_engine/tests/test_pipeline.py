"""
Integration tests for the RAG pipeline.

These tests verify the end-to-end functionality of the pipeline,
including ingestion and retrieval workflows.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag_engine.config import CaseDocument, RAGConfig, SectionType
from rag_engine.pipeline import RAGPipeline


class TestRAGPipelineInitialization:
    """Tests for pipeline initialization."""

    def test_pipeline_initializes(self, test_config):
        """Test that pipeline initializes correctly."""
        pipeline = RAGPipeline(config=test_config)

        assert pipeline.config is not None
        assert pipeline.extractor is not None
        assert pipeline.cleaner is not None
        assert pipeline.chunker is not None

    def test_pipeline_creates_directories(self, test_config):
        """Test that pipeline creates required directories."""
        # Remove directory to test creation
        if test_config.data_dir.exists():
            import shutil
            shutil.rmtree(test_config.data_dir)

        test_config.ensure_directories()
        pipeline = RAGPipeline(config=test_config)

        assert test_config.data_dir.exists()
        assert test_config.chroma_persist_dir.exists()


class TestRAGPipelineIngestion:
    """Tests for document ingestion."""

    @pytest.fixture
    def mock_pipeline(self, test_config):
        """Create a pipeline with mocked external services."""
        with patch("rag_engine.pipeline.OpenAIEmbeddings") as mock_embed_class:
            with patch("rag_engine.pipeline.ChromaStore") as mock_store_class:
                # Setup mock embeddings
                mock_embed = MagicMock()
                mock_embed.embed_texts = AsyncMock(
                    return_value=[[0.1] * 1536 for _ in range(10)]
                )
                mock_embed.get_stats = MagicMock(
                    return_value={"total_tokens": 1000}
                )
                mock_embed_class.return_value = mock_embed

                # Setup mock vector store
                mock_store = MagicMock()
                mock_store.add_chunks = AsyncMock()
                mock_store.chunk_exists = AsyncMock(return_value=False)
                mock_store.get_all_chunk_ids = AsyncMock(return_value=[])
                mock_store.get_collection_stats = AsyncMock(
                    return_value={"total_chunks": 0}
                )
                mock_store_class.return_value = mock_store

                pipeline = RAGPipeline(config=test_config)
                pipeline.embeddings = mock_embed
                pipeline.vectorstore = mock_store

                yield pipeline

    @pytest.mark.asyncio
    async def test_ingest_single_document(self, mock_pipeline, sample_case_document):
        """Test ingesting a single document."""
        result = await mock_pipeline.ingest_document(sample_case_document)

        assert result["status"] == "complete"
        assert result["case_reference"] == sample_case_document.case_reference
        assert result["chunks_created"] > 0

    @pytest.mark.asyncio
    async def test_ingest_empty_document(self, mock_pipeline):
        """Test ingesting an empty document."""
        doc = CaseDocument(
            case_reference="EMPTY",
            year=2021,
            full_text="   ",  # Whitespace only
            source_path="/test.pdf",
        )

        result = await mock_pipeline.ingest_document(doc)
        assert result["status"] == "no_chunks"

    @pytest.mark.asyncio
    async def test_ingest_creates_chunks(self, mock_pipeline, sample_case_document):
        """Test that ingestion creates proper chunks."""
        result = await mock_pipeline.ingest_document(sample_case_document)

        # Verify chunks were added to vector store
        mock_pipeline.vectorstore.add_chunks.assert_called()
        call_args = mock_pipeline.vectorstore.add_chunks.call_args
        chunks = call_args[0][0]

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.case_reference == sample_case_document.case_reference

    @pytest.mark.asyncio
    async def test_ingest_generates_embeddings(self, mock_pipeline, sample_case_document):
        """Test that ingestion generates embeddings."""
        await mock_pipeline.ingest_document(sample_case_document)

        # Verify embeddings were generated
        mock_pipeline.embeddings.embed_texts.assert_called()


class TestRAGPipelineRetrieval:
    """Tests for retrieval functionality."""

    @pytest.fixture
    def pipeline_with_data(self, test_config):
        """Create a pipeline with mock data."""
        from rag_engine.vectorstore.base import VectorSearchResult

        with patch("rag_engine.pipeline.OpenAIEmbeddings") as mock_embed_class:
            with patch("rag_engine.pipeline.ChromaStore") as mock_store_class:
                # Setup mock embeddings
                mock_embed = MagicMock()
                mock_embed.embed_query = AsyncMock(return_value=[0.5] * 1536)
                mock_embed.embed_texts = AsyncMock(
                    return_value=[[0.1] * 1536]
                )
                mock_embed.get_stats = MagicMock(return_value={})
                mock_embed_class.return_value = mock_embed

                # Setup mock vector store with results
                mock_store = MagicMock()
                mock_store.query = AsyncMock(return_value=[
                    VectorSearchResult(
                        chunk_id="test_chunk_1",
                        text="The landlord failed to protect the deposit under section 213.",
                        score=0.85,
                        metadata={
                            "case_reference": "LON_TEST_HMF_2021_0001",
                            "year": 2021,
                            "region": "LON",
                            "case_type": "HMF",
                            "section_type": "facts",
                            "chunk_index": 0,
                        }
                    ),
                    VectorSearchResult(
                        chunk_id="test_chunk_2",
                        text="Compensation awarded for deposit protection failure.",
                        score=0.75,
                        metadata={
                            "case_reference": "LON_TEST_HMF_2021_0001",
                            "year": 2021,
                            "region": "LON",
                            "case_type": "HMF",
                            "section_type": "decision",
                            "chunk_index": 1,
                        }
                    ),
                ])
                mock_store.get_collection_stats = AsyncMock(
                    return_value={"total_chunks": 100}
                )
                mock_store_class.return_value = mock_store

                pipeline = RAGPipeline(config=test_config)
                pipeline.embeddings = mock_embed
                pipeline.vectorstore = mock_store

                # Build a minimal BM25 index
                from rag_engine.config import DocumentChunk
                from rag_engine.retrieval.bm25_index import BM25Index

                chunks = [
                    DocumentChunk(
                        chunk_id="test_chunk_1",
                        case_reference="LON_TEST_HMF_2021_0001",
                        chunk_index=0,
                        text="The landlord failed to protect the deposit under section 213.",
                        section_type=SectionType.FACTS,
                        year=2021,
                        region="LON",
                        case_type="HMF",
                    ),
                    DocumentChunk(
                        chunk_id="test_chunk_2",
                        case_reference="LON_TEST_HMF_2021_0001",
                        chunk_index=1,
                        text="Compensation awarded for deposit protection failure.",
                        section_type=SectionType.DECISION,
                        year=2021,
                        region="LON",
                        case_type="HMF",
                    ),
                ]
                pipeline.bm25_index = BM25Index(lite_mode=True)
                pipeline.bm25_index.build_index(chunks)
                pipeline._init_retriever()

                yield pipeline

    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self, pipeline_with_data):
        """Test that retrieval returns results."""
        result = await pipeline_with_data.retrieve(
            query="deposit protection section 213",
            top_k=5
        )

        assert result is not None
        assert len(result.results) > 0
        assert result.query == "deposit protection section 213"

    @pytest.mark.asyncio
    async def test_retrieve_includes_confidence(self, pipeline_with_data):
        """Test that retrieval includes confidence score."""
        result = await pipeline_with_data.retrieve(
            query="deposit protection",
            top_k=5
        )

        assert result.confidence >= 0
        assert result.confidence <= 1

    @pytest.mark.asyncio
    async def test_retrieve_includes_timing(self, pipeline_with_data):
        """Test that retrieval includes timing information."""
        result = await pipeline_with_data.retrieve(
            query="deposit",
            top_k=5
        )

        assert result.retrieval_time_ms > 0

    @pytest.mark.asyncio
    async def test_retrieve_with_filters(self, pipeline_with_data):
        """Test retrieval with metadata filters."""
        result = await pipeline_with_data.retrieve(
            query="deposit",
            top_k=5,
            where={"year": 2021, "region": "LON"}
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self, pipeline_with_data):
        """Test retrieval with empty query."""
        result = await pipeline_with_data.retrieve(
            query="",
            top_k=5
        )

        # Should still return something (or handle gracefully)
        assert result is not None


class TestRAGPipelineConfidence:
    """Tests for confidence calculation."""

    def test_confidence_high_similarity(self, test_config):
        """Test confidence calculation with high similarity results."""
        pipeline = RAGPipeline(config=test_config)

        from rag_engine.config import RetrievalResult

        results = [
            RetrievalResult(
                chunk_id=f"chunk_{i}",
                case_reference=f"CASE_{i}",
                chunk_text="High quality match",
                section_type="facts",
                semantic_score=0.85 - (i * 0.02),
                semantic_rank=i + 1,
                bm25_score=10.0,
                bm25_rank=i + 1,
                combined_score=0.02,
                year=2021,
                region="LON",
                case_type="HMF",
            )
            for i in range(5)
        ]

        confidence, is_uncertain, reason = pipeline._calculate_confidence(results)

        assert confidence > 0.5  # Should be confident
        assert is_uncertain is False

    def test_confidence_low_similarity(self, test_config):
        """Test confidence calculation with low similarity results."""
        pipeline = RAGPipeline(config=test_config)

        from rag_engine.config import RetrievalResult

        results = [
            RetrievalResult(
                chunk_id=f"chunk_{i}",
                case_reference=f"CASE_{i}",
                chunk_text="Poor match",
                section_type="facts",
                semantic_score=0.25 - (i * 0.02),
                semantic_rank=i + 1,
                bm25_score=2.0,
                bm25_rank=i + 1,
                combined_score=0.005,
                year=2021,
                region="LON",
                case_type="HMF",
            )
            for i in range(3)
        ]

        confidence, is_uncertain, reason = pipeline._calculate_confidence(results)

        assert confidence < 0.5  # Should be uncertain
        assert is_uncertain is True
        assert reason is not None

    def test_confidence_empty_results(self, test_config):
        """Test confidence with no results."""
        pipeline = RAGPipeline(config=test_config)

        confidence, is_uncertain, reason = pipeline._calculate_confidence([])

        assert confidence == 0.0
        assert is_uncertain is True


class TestRAGPipelineStats:
    """Tests for pipeline statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, test_config):
        """Test getting pipeline statistics."""
        with patch("rag_engine.pipeline.OpenAIEmbeddings") as mock_embed_class:
            with patch("rag_engine.pipeline.ChromaStore") as mock_store_class:
                mock_embed = MagicMock()
                mock_embed.get_stats = MagicMock(
                    return_value={"total_tokens": 5000}
                )
                mock_embed_class.return_value = mock_embed

                mock_store = MagicMock()
                mock_store.get_collection_stats = AsyncMock(
                    return_value={"total_chunks": 100, "unique_cases": 50}
                )
                mock_store_class.return_value = mock_store

                pipeline = RAGPipeline(config=test_config)
                pipeline.embeddings = mock_embed
                pipeline.vectorstore = mock_store

                stats = await pipeline.get_stats()

                assert "vectorstore" in stats
                assert "bm25" in stats
                assert "embeddings" in stats


class TestRAGPipelineEdgeCases:
    """Tests for edge cases in the pipeline."""

    @pytest.mark.asyncio
    async def test_retriever_not_initialized(self, test_config):
        """Test retrieval when retriever is not initialized."""
        with patch("rag_engine.pipeline.OpenAIEmbeddings"):
            with patch("rag_engine.pipeline.ChromaStore"):
                pipeline = RAGPipeline(config=test_config)
                pipeline._retriever = None

                result = await pipeline.retrieve("test query", top_k=5)

                assert result.is_uncertain is True
                assert "not built" in result.uncertainty_reason.lower()

    @pytest.mark.asyncio
    async def test_clear_index(self, test_config):
        """Test clearing the index."""
        with patch("rag_engine.pipeline.OpenAIEmbeddings"):
            with patch("rag_engine.pipeline.ChromaStore") as mock_store_class:
                mock_store = MagicMock()
                mock_store.delete_collection = AsyncMock()
                mock_store_class.return_value = mock_store

                pipeline = RAGPipeline(config=test_config)
                pipeline.vectorstore = mock_store

                await pipeline.clear_index()

                mock_store.delete_collection.assert_called_once()
                assert pipeline._retriever is None
