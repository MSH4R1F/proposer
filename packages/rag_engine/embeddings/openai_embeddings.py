"""
OpenAI embedding implementation using text-embedding-3-small.

Provides async batch embedding with retry logic, rate limiting,
and cost tracking.
"""

import asyncio
from typing import List, Optional

import structlog
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import tiktoken

from .base import BaseEmbeddings
from ..config import RAGConfig

logger = structlog.get_logger()


class OpenAIEmbeddings(BaseEmbeddings):
    """
    OpenAI text embedding using text-embedding-3-small.

    Features:
    - Async batch processing
    - Automatic retry with exponential backoff
    - Token counting and cost tracking
    - Rate limiting awareness
    """

    # Pricing per 1M tokens (as of 2024)
    PRICING = {
        "text-embedding-3-small": 0.02,  # $0.02 per 1M tokens
        "text-embedding-3-large": 0.13,  # $0.13 per 1M tokens
        "text-embedding-ada-002": 0.10,  # $0.10 per 1M tokens
    }

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        batch_size: int = 50
    ) -> None:
        """
        Initialize OpenAI embeddings.

        Args:
            config: RAGConfig object (optional)
            api_key: OpenAI API key (overrides config)
            model: Embedding model name
            batch_size: Number of texts to embed per API call
        """
        if config:
            self._api_key = api_key or config.openai_api_key
            self._model = model or config.embedding_model
            self._batch_size = batch_size or config.embedding_batch_size
        else:
            self._api_key = api_key or ""
            self._model = model
            self._batch_size = batch_size

        if not self._api_key:
            raise ValueError("OpenAI API key is required")

        self._client = AsyncOpenAI(api_key=self._api_key)
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

        # Stats tracking
        self._stats = {
            "total_texts": 0,
            "total_tokens": 0,
            "api_calls": 0,
            "errors": 0,
        }

        # Model dimensions
        self._dimensions_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        return self._dimensions_map.get(self._model, 1536)

    async def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0]

    async def embed_query(self, query: str) -> List[float]:
        """
        Embed a search query.

        For OpenAI, queries and documents use the same embedding.

        Args:
            query: Query text

        Returns:
            Query embedding vector
        """
        return await self.embed_text(query)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts with batching.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Process in batches
        all_embeddings = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

            # Small delay between batches to avoid rate limits
            if i + self._batch_size < len(texts):
                await asyncio.sleep(0.1)

        return all_embeddings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: logger.warning(
            "embedding_retry",
            attempt=retry_state.attempt_number,
            error=str(retry_state.outcome.exception()) if retry_state.outcome else None
        )
    )
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts with retry logic.

        Args:
            texts: Batch of texts to embed

        Returns:
            List of embedding vectors
        """
        # Count tokens for stats
        token_count = sum(len(self._tokenizer.encode(t)) for t in texts)

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts
            )

            # Update stats
            self._stats["total_texts"] += len(texts)
            self._stats["total_tokens"] += token_count
            self._stats["api_calls"] += 1

            # Extract embeddings in correct order
            embeddings = [None] * len(texts)
            for data in response.data:
                embeddings[data.index] = data.embedding

            logger.debug(
                "batch_embedded",
                batch_size=len(texts),
                tokens=token_count,
                model=self._model
            )

            return embeddings

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(
                "embedding_failed",
                error=str(e),
                batch_size=len(texts)
            )
            raise

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        return len(self._tokenizer.encode(text))

    def estimate_cost(self, texts: List[str]) -> float:
        """
        Estimate cost for embedding texts.

        Args:
            texts: Texts to estimate cost for

        Returns:
            Estimated cost in USD
        """
        total_tokens = sum(self.count_tokens(t) for t in texts)
        price_per_million = self.PRICING.get(self._model, 0.02)
        return (total_tokens / 1_000_000) * price_per_million

    def get_stats(self) -> dict:
        """Get usage statistics."""
        stats = self._stats.copy()

        # Calculate estimated cost
        price_per_million = self.PRICING.get(self._model, 0.02)
        stats["estimated_cost_usd"] = (
            stats["total_tokens"] / 1_000_000
        ) * price_per_million

        return stats

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._stats = {
            "total_texts": 0,
            "total_tokens": 0,
            "api_calls": 0,
            "errors": 0,
        }
