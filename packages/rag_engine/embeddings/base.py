"""
Abstract base class for embedding providers.

Defines the interface that all embedding implementations must follow,
enabling easy swapping between providers (OpenAI, local models, etc.).
"""

from abc import ABC, abstractmethod
from typing import List

import numpy as np


class BaseEmbeddings(ABC):
    """
    Abstract base class for text embedding generation.

    All embedding providers should implement this interface to ensure
    compatibility with the RAG pipeline.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the name of the embedding model."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding vector dimensions."""
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.

        Some models use different embeddings for documents vs queries.
        Default implementation just calls embed_text.

        Args:
            query: Query text to embed

        Returns:
            Query embedding vector
        """
        pass

    def cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0 to 1)
        """
        a = np.array(embedding1)
        b = np.array(embedding2)

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def get_stats(self) -> dict:
        """
        Get usage statistics.

        Returns:
            Dict with stats like tokens used, API calls, etc.
        """
        return {}

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        pass
