"""
Abstract base class for vector stores.

Defines the interface for vector storage backends, enabling
easy migration from ChromaDB to Pinecone or other providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from ..config import DocumentChunk


class VectorSearchResult:
    """Result from a vector similarity search."""

    def __init__(
        self,
        chunk_id: str,
        text: str,
        score: float,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Initialize a search result.

        Args:
            chunk_id: Unique identifier for the chunk
            text: Text content of the chunk
            score: Similarity score (higher is better)
            metadata: Associated metadata
        """
        self.chunk_id = chunk_id
        self.text = text
        self.score = score
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata,
        }


class BaseVectorStore(ABC):
    """
    Abstract base class for vector storage backends.

    Implementations must provide methods for:
    - Adding documents with embeddings
    - Querying by vector similarity
    - Managing collections/indices
    """

    @property
    @abstractmethod
    def collection_name(self) -> str:
        """Return the name of the collection/index."""
        pass

    @abstractmethod
    async def add_chunks(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]]
    ) -> None:
        """
        Add document chunks with their embeddings.

        Args:
            chunks: List of document chunks
            embeddings: Corresponding embedding vectors
        """
        pass

    @abstractmethod
    async def query(
        self,
        embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        """
        Query for similar vectors.

        Args:
            embedding: Query embedding vector
            n_results: Number of results to return
            where: Optional metadata filter

        Returns:
            List of search results ordered by similarity
        """
        pass

    @abstractmethod
    async def delete_collection(self) -> None:
        """Delete the entire collection/index."""
        pass

    @abstractmethod
    async def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the collection.

        Returns:
            Dict with count, storage size, etc.
        """
        pass

    @abstractmethod
    async def chunk_exists(self, chunk_id: str) -> bool:
        """
        Check if a chunk already exists.

        Args:
            chunk_id: Chunk identifier to check

        Returns:
            True if chunk exists
        """
        pass

    async def add_chunk(
        self,
        chunk: DocumentChunk,
        embedding: List[float]
    ) -> None:
        """
        Add a single chunk (convenience method).

        Args:
            chunk: Document chunk
            embedding: Embedding vector
        """
        await self.add_chunks([chunk], [embedding])

    def get_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.

        Returns:
            Dict with operation counts, etc.
        """
        return {}
