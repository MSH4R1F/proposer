"""
Tests for RAG Engine configuration and data models.
"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_engine.config import (
    CaseDocument,
    DocumentChunk,
    QueryResult,
    RAGConfig,
    RetrievalResult,
    SectionType,
)


class TestSectionType:
    """Tests for SectionType enum."""

    def test_section_type_values(self):
        """Test that all section types are defined."""
        assert SectionType.BACKGROUND == "background"
        assert SectionType.FACTS == "facts"
        assert SectionType.REASONING == "reasoning"
        assert SectionType.DECISION == "decision"
        assert SectionType.UNKNOWN == "unknown"

    def test_section_type_from_string(self):
        """Test creating SectionType from string."""
        assert SectionType("background") == SectionType.BACKGROUND
        assert SectionType("unknown") == SectionType.UNKNOWN


class TestCaseDocument:
    """Tests for CaseDocument model."""

    def test_create_case_document(self, sample_case_document):
        """Test creating a valid CaseDocument."""
        doc = sample_case_document
        assert doc.case_reference == "LON_00AB_HMF_2021_0001"
        assert doc.year == 2021
        assert doc.region == "LON"
        assert doc.case_type == "HMF"
        assert len(doc.full_text) > 0

    def test_case_document_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError):
            CaseDocument(
                # Missing case_reference, year, full_text, source_path
                region="LON",
            )

    def test_case_document_year_validation(self):
        """Test year validation (must be 2000-2030)."""
        with pytest.raises(ValidationError):
            CaseDocument(
                case_reference="TEST",
                year=1999,  # Too old
                full_text="test",
                source_path="/test.pdf",
            )

        with pytest.raises(ValidationError):
            CaseDocument(
                case_reference="TEST",
                year=2031,  # Too new
                full_text="test",
                source_path="/test.pdf",
            )

    def test_case_document_category_property(self):
        """Test category inference from source path."""
        deposit_doc = CaseDocument(
            case_reference="TEST",
            year=2021,
            full_text="test",
            source_path="/data/raw/bailii/deposit-cases/test.pdf",
        )
        assert deposit_doc.category == "deposit"

        adjacent_doc = CaseDocument(
            case_reference="TEST",
            year=2021,
            full_text="test",
            source_path="/data/raw/bailii/adjacent-cases/test.pdf",
        )
        assert adjacent_doc.category == "adjacent"

        other_doc = CaseDocument(
            case_reference="TEST",
            year=2021,
            full_text="test",
            source_path="/data/raw/bailii/other/test.pdf",
        )
        assert other_doc.category == "other"


class TestDocumentChunk:
    """Tests for DocumentChunk model."""

    def test_create_document_chunk(self, sample_chunks):
        """Test creating a valid DocumentChunk."""
        chunk = sample_chunks[0]
        assert chunk.chunk_id == "LON_00AB_HMF_2021_0001_0"
        assert chunk.case_reference == "LON_00AB_HMF_2021_0001"
        assert chunk.chunk_index == 0
        assert chunk.section_type == SectionType.BACKGROUND

    def test_document_chunk_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError):
            DocumentChunk(
                # Missing chunk_id, case_reference, text, year
                chunk_index=0,
            )

    def test_chunk_index_validation(self):
        """Test chunk_index must be >= 0."""
        with pytest.raises(ValidationError):
            DocumentChunk(
                chunk_id="test_0",
                case_reference="test",
                chunk_index=-1,  # Invalid
                text="test",
                year=2021,
            )

    def test_to_chroma_metadata(self, sample_chunks):
        """Test conversion to ChromaDB metadata format."""
        chunk = sample_chunks[0]
        metadata = chunk.to_chroma_metadata()

        assert metadata["case_reference"] == "LON_00AB_HMF_2021_0001"
        assert metadata["chunk_index"] == 0
        assert metadata["section_type"] == "background"
        assert metadata["year"] == 2021
        assert metadata["region"] == "LON"
        assert metadata["case_type"] == "HMF"


class TestRetrievalResult:
    """Tests for RetrievalResult model."""

    def test_create_retrieval_result(self, sample_retrieval_results):
        """Test creating a valid RetrievalResult."""
        result = sample_retrieval_results[0]
        assert result.chunk_id == "LON_00AB_HMF_2021_0001_1"
        assert result.semantic_score == 0.85
        assert result.bm25_score == 15.5

    def test_score_validation(self):
        """Test that scores are within valid ranges."""
        # Semantic score must be 0-1
        with pytest.raises(ValidationError):
            RetrievalResult(
                chunk_id="test",
                case_reference="test",
                chunk_text="test",
                section_type="facts",
                semantic_score=1.5,  # Invalid > 1
                semantic_rank=1,
                bm25_score=10.0,
                bm25_rank=1,
                combined_score=0.5,
                year=2021,
            )

    def test_optional_rerank_fields(self, sample_retrieval_results):
        """Test that rerank fields are optional."""
        result = sample_retrieval_results[0]
        assert result.rerank_score is None
        assert result.relevance_explanation is None


class TestQueryResult:
    """Tests for QueryResult model."""

    def test_create_query_result(self, sample_retrieval_results):
        """Test creating a valid QueryResult."""
        result = QueryResult(
            query="test query",
            results=sample_retrieval_results,
            confidence=0.85,
            total_candidates=10,
            retrieval_time_ms=150.5,
        )
        assert result.query == "test query"
        assert len(result.results) == 3
        assert result.confidence == 0.85
        assert result.is_uncertain is False

    def test_uncertain_query_result(self):
        """Test QueryResult with uncertainty."""
        result = QueryResult(
            query="obscure query",
            results=[],
            confidence=0.2,
            is_uncertain=True,
            uncertainty_reason="No matching cases found.",
            total_candidates=0,
            retrieval_time_ms=50.0,
        )
        assert result.is_uncertain is True
        assert result.uncertainty_reason == "No matching cases found."


class TestRAGConfig:
    """Tests for RAGConfig model."""

    def test_create_config_with_defaults(self):
        """Test creating RAGConfig with default values."""
        config = RAGConfig()
        assert config.embedding_model == "text-embedding-3-small"
        assert config.embedding_dimensions == 1536
        assert config.chunk_size == 500
        assert config.chunk_overlap == 50
        assert config.collection_name == "tribunal_cases"

    def test_create_config_with_custom_values(self, temp_data_dir):
        """Test creating RAGConfig with custom values."""
        config = RAGConfig(
            data_dir=temp_data_dir,
            chunk_size=300,
            chunk_overlap=30,
            initial_retrieval_k=15,
        )
        assert config.data_dir == temp_data_dir
        assert config.chunk_size == 300
        assert config.chunk_overlap == 30
        assert config.initial_retrieval_k == 15

    def test_config_from_env(self, monkeypatch):
        """Test creating config from environment variables."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-from-env")
        monkeypatch.setenv("DATA_DIR", "/custom/data")

        config = RAGConfig.from_env()
        assert config.openai_api_key == "test-key-from-env"
        assert config.data_dir == Path("/custom/data")

    def test_ensure_directories(self, temp_data_dir):
        """Test that ensure_directories creates required directories."""
        config = RAGConfig(
            data_dir=temp_data_dir / "new",
            chroma_persist_dir=temp_data_dir / "new" / "chroma",
            bm25_index_path=temp_data_dir / "new" / "chroma" / "bm25.pkl",
        )

        assert not config.data_dir.exists()

        config.ensure_directories()

        assert config.data_dir.exists()
        assert config.chroma_persist_dir.exists()
        assert config.bm25_index_path.parent.exists()

    def test_semantic_weight_validation(self):
        """Test semantic_weight must be 0-1."""
        with pytest.raises(ValidationError):
            RAGConfig(semantic_weight=1.5)

        with pytest.raises(ValidationError):
            RAGConfig(semantic_weight=-0.1)

    def test_path_resolution(self, temp_data_dir):
        """Test that string paths are converted to Path objects."""
        config = RAGConfig(
            data_dir=str(temp_data_dir),
            chroma_persist_dir=str(temp_data_dir / "embeddings"),
        )
        assert isinstance(config.data_dir, Path)
        assert isinstance(config.chroma_persist_dir, Path)
