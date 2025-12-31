"""
Configuration and data models for RAG Engine.

Handles environment variables, paths, and defines core data structures
used throughout the RAG pipeline.
"""

import os
from pathlib import Path
from typing import Dict, List, Literal, Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

load_dotenv()


class SectionType(str, Enum):
    """Types of sections in tribunal decisions."""
    BACKGROUND = "background"
    FACTS = "facts"
    REASONING = "reasoning"
    DECISION = "decision"
    UNKNOWN = "unknown"


class CaseDocument(BaseModel):
    """Represents a parsed tribunal case document."""

    case_reference: str = Field(..., description="Unique case identifier, e.g., LON_00BK_HMF_2022_0227")
    year: int = Field(..., ge=2000, le=2030, description="Year of decision")
    region: Optional[str] = Field(None, description="Tribunal region code, e.g., LON, CHI, MAN")
    region_name: Optional[str] = Field(None, description="Full region name, e.g., London")
    case_type: Optional[str] = Field(None, description="Case type code, e.g., HNA, HMF")
    case_type_name: Optional[str] = Field(None, description="Full case type name")
    title: Optional[str] = Field(None, description="Case title from document")
    decision_date: Optional[str] = Field(None, description="Date of decision (ISO format)")

    full_text: str = Field(..., description="Complete extracted text from PDF")
    sections: Dict[str, str] = Field(
        default_factory=dict,
        description="Document sections: background, facts, reasoning, decision"
    )

    source_path: str = Field(..., description="Path to source PDF file")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")

    @property
    def category(self) -> str:
        """Infer category from source path."""
        path_lower = self.source_path.lower()
        if "deposit" in path_lower:
            return "deposit"
        elif "adjacent" in path_lower:
            return "adjacent"
        return "other"


class DocumentChunk(BaseModel):
    """A chunk of text from a case document."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    case_reference: str = Field(..., description="Parent case reference")
    chunk_index: int = Field(..., ge=0, description="Position in document")

    text: str = Field(..., description="Chunk text content")
    section_type: SectionType = Field(
        default=SectionType.UNKNOWN,
        description="Which section this chunk belongs to"
    )

    # Metadata for filtering
    year: int = Field(..., description="Year of case")
    region: Optional[str] = Field(None, description="Region code")
    case_type: Optional[str] = Field(None, description="Case type code")

    # Token count for cost tracking
    token_count: int = Field(default=0, description="Approximate token count")

    def to_chroma_metadata(self) -> Dict:
        """Convert to ChromaDB-compatible metadata dict."""
        return {
            "case_reference": self.case_reference,
            "chunk_index": self.chunk_index,
            "section_type": self.section_type.value,
            "year": self.year,
            "region": self.region or "",
            "case_type": self.case_type or "",
            "token_count": self.token_count,
        }


class RetrievalResult(BaseModel):
    """Result from hybrid retrieval with scoring details."""

    chunk_id: str = Field(..., description="Chunk identifier")
    case_reference: str = Field(..., description="Source case reference")
    chunk_text: str = Field(..., description="Retrieved text content")
    section_type: str = Field(..., description="Section type of chunk")

    # Scoring
    semantic_score: float = Field(..., ge=0, le=1, description="Cosine similarity score")
    semantic_rank: int = Field(..., ge=1, description="Rank in semantic results")
    bm25_score: float = Field(..., ge=0, description="BM25 relevance score")
    bm25_rank: int = Field(..., ge=1, description="Rank in BM25 results")
    combined_score: float = Field(..., ge=0, description="RRF combined score")

    # Metadata
    year: int = Field(..., description="Year of case")
    region: Optional[str] = Field(None, description="Region code")
    case_type: Optional[str] = Field(None, description="Case type")

    # Re-ranking
    rerank_score: Optional[float] = Field(None, description="Score after re-ranking")
    relevance_explanation: Optional[str] = Field(None, description="Why this result is relevant")


class QueryResult(BaseModel):
    """Final result from RAG query including confidence."""

    query: str = Field(..., description="Original query text")
    results: List[RetrievalResult] = Field(..., description="Retrieved results")

    confidence: float = Field(..., ge=0, le=1, description="Confidence in results")
    is_uncertain: bool = Field(default=False, description="True if no similar cases found")
    uncertainty_reason: Optional[str] = Field(None, description="Explanation if uncertain")

    # Stats
    total_candidates: int = Field(..., description="Total candidates before filtering")
    retrieval_time_ms: float = Field(..., description="Time taken for retrieval")


class RAGConfig(BaseModel):
    """Configuration for RAG pipeline."""

    # API Keys
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""),
        description="OpenAI API key for embeddings"
    )

    # Paths
    data_dir: Path = Field(
        default=Path("./data"),
        description="Base data directory"
    )
    chroma_persist_dir: Path = Field(
        default=Path("./data/embeddings"),
        description="ChromaDB persistence directory"
    )
    bm25_index_path: Path = Field(
        default=Path("./data/embeddings/bm25_index.pkl"),
        description="Path to BM25 index pickle file"
    )

    # Embedding settings
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model"
    )
    embedding_dimensions: int = Field(
        default=1536,
        description="Embedding vector dimensions"
    )
    embedding_batch_size: int = Field(
        default=50,
        description="Batch size for embedding generation"
    )

    # Chunking settings
    chunk_size: int = Field(
        default=500,
        description="Target chunk size in tokens"
    )
    chunk_overlap: int = Field(
        default=50,
        description="Overlap between chunks in tokens"
    )

    # Retrieval settings
    initial_retrieval_k: int = Field(
        default=20,
        description="Number of candidates to retrieve before re-ranking"
    )
    final_top_k: int = Field(
        default=5,
        description="Final number of results to return"
    )
    rrf_k: int = Field(
        default=60,
        description="K parameter for Reciprocal Rank Fusion"
    )
    semantic_weight: float = Field(
        default=0.7,
        ge=0, le=1,
        description="Weight for semantic search (BM25 gets 1-this)"
    )

    # Confidence thresholds
    min_confidence_threshold: float = Field(
        default=0.5,
        description="Minimum confidence to not flag as uncertain"
    )
    min_similarity_threshold: float = Field(
        default=0.3,
        description="Minimum similarity score for a result to be considered"
    )

    # ChromaDB settings
    collection_name: str = Field(
        default="tribunal_cases",
        description="ChromaDB collection name"
    )

    @field_validator("openai_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Warn if API key is not set."""
        if not v:
            import structlog
            logger = structlog.get_logger()
            logger.warning("OPENAI_API_KEY not set - embedding generation will fail")
        return v

    @field_validator("data_dir", "chroma_persist_dir", mode="before")
    @classmethod
    def resolve_path(cls, v):
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Create config from environment variables."""
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            chroma_persist_dir=Path(os.getenv("CHROMA_PERSIST_DIR", "./data/embeddings")),
        )


# Legal domain keywords for re-ranking relevance
DEPOSIT_ISSUE_KEYWORDS = {
    "deposit_protection": [
        "deposit protection", "section 213", "section 214",
        "tenancy deposit scheme", "tds", "dps", "mydeposits",
        "protected deposit", "unprotected deposit", "prescribed information"
    ],
    "cleaning": [
        "cleaning", "professional clean", "end of tenancy clean",
        "cleanliness", "dirty", "filthy", "clean condition"
    ],
    "damage": [
        "damage", "damages", "broken", "stain", "mark", "scratch",
        "hole", "burn", "tear", "worn", "deterioration"
    ],
    "fair_wear_and_tear": [
        "fair wear and tear", "reasonable wear", "natural wear",
        "normal use", "betterment"
    ],
    "inventory": [
        "inventory", "check-in", "check-out", "schedule of condition",
        "photographic evidence", "inspection report"
    ],
    "rent_arrears": [
        "rent arrears", "unpaid rent", "outstanding rent",
        "rent owed", "arrears"
    ],
    "garden": [
        "garden", "lawn", "grass", "overgrown", "landscaping",
        "outdoor area", "patio"
    ],
    "decoration": [
        "redecoration", "painting", "redecorating", "walls",
        "paintwork", "marks on walls"
    ],
}
