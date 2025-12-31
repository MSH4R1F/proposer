"""
Hybrid retriever combining semantic and keyword search.

Uses Reciprocal Rank Fusion (RRF) to merge results from
ChromaDB (semantic) and BM25 (keyword) searches.
"""

from typing import Any, Dict, List, Optional, Tuple

import structlog

from .bm25_index import BM25Index
from ..config import DocumentChunk, RAGConfig, RetrievalResult
from ..embeddings.base import BaseEmbeddings
from ..vectorstore.base import BaseVectorStore

logger = structlog.get_logger()


class HybridRetriever:
    """
    Hybrid retrieval combining semantic and keyword search.

    Uses Reciprocal Rank Fusion (RRF) to combine results from:
    - Semantic search (via embeddings + vector store)
    - Keyword search (via BM25)

    RRF Formula: score = sum(1 / (k + rank)) for each result list
    """

    def __init__(
        self,
        embeddings: BaseEmbeddings,
        vectorstore: BaseVectorStore,
        bm25_index: BM25Index,
        config: Optional[RAGConfig] = None,
        rrf_k: int = 60,
        semantic_weight: float = 0.7
    ) -> None:
        """
        Initialize hybrid retriever.

        Args:
            embeddings: Embedding provider
            vectorstore: Vector store for semantic search
            bm25_index: BM25 index for keyword search
            config: RAGConfig object (optional)
            rrf_k: K parameter for RRF (default 60)
            semantic_weight: Weight for semantic results (0-1)
        """
        self.embeddings = embeddings
        self.vectorstore = vectorstore
        self.bm25_index = bm25_index

        if config:
            self.rrf_k = config.rrf_k
            self.semantic_weight = config.semantic_weight
        else:
            self.rrf_k = rrf_k
            self.semantic_weight = semantic_weight

        self.keyword_weight = 1.0 - self.semantic_weight

        # Stats
        self._stats = {
            "queries": 0,
            "avg_semantic_hits": 0.0,
            "avg_keyword_hits": 0.0,
        }

    async def retrieve(
        self,
        query: str,
        top_k: int = 20,
        where: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """
        Retrieve relevant documents using hybrid search.

        Args:
            query: Search query
            top_k: Number of results to retrieve
            where: Optional metadata filter

        Returns:
            List of RetrievalResult objects with combined scores
        """
        self._stats["queries"] += 1

        # Run semantic and keyword search in parallel
        semantic_results = await self._semantic_search(query, top_k * 2, where)
        keyword_results = self._keyword_search(query, top_k * 2)

        # Update stats
        n_semantic = len(semantic_results)
        n_keyword = len(keyword_results)
        self._stats["avg_semantic_hits"] = (
            (self._stats["avg_semantic_hits"] * (self._stats["queries"] - 1) + n_semantic)
            / self._stats["queries"]
        )
        self._stats["avg_keyword_hits"] = (
            (self._stats["avg_keyword_hits"] * (self._stats["queries"] - 1) + n_keyword)
            / self._stats["queries"]
        )

        # Fuse results using RRF
        fused_results = self._rrf_fusion(
            semantic_results,
            keyword_results,
            top_k
        )

        logger.debug(
            "hybrid_retrieval_complete",
            query_preview=query[:50],
            semantic_hits=n_semantic,
            keyword_hits=n_keyword,
            fused_results=len(fused_results)
        )

        return fused_results

    async def _semantic_search(
        self,
        query: str,
        top_k: int,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, int, Dict]]:
        """
        Perform semantic search.

        Returns:
            List of (chunk_id, score, rank, metadata) tuples
        """
        # Generate query embedding
        query_embedding = await self.embeddings.embed_query(query)

        # Query vector store
        results = await self.vectorstore.query(
            embedding=query_embedding,
            n_results=top_k,
            where=where
        )

        # Convert to tuple format with ranks
        return [
            (r.chunk_id, r.score, rank, r.metadata)
            for rank, r in enumerate(results, start=1)
        ]

    def _keyword_search(
        self,
        query: str,
        top_k: int
    ) -> List[Tuple[str, float, int, Dict]]:
        """
        Perform BM25 keyword search.

        Returns:
            List of (chunk_id, score, rank, metadata) tuples
        """
        if not self.bm25_index.is_built:
            return []

        results = self.bm25_index.search(query, top_k)

        # Convert to tuple format
        return [
            (
                chunk.chunk_id,
                score,
                rank,
                chunk.to_chroma_metadata()
            )
            for chunk, score, rank in results
        ]

    def _rrf_fusion(
        self,
        semantic_results: List[Tuple[str, float, int, Dict]],
        keyword_results: List[Tuple[str, float, int, Dict]],
        top_k: int
    ) -> List[RetrievalResult]:
        """
        Fuse results using Reciprocal Rank Fusion.

        Args:
            semantic_results: Results from semantic search
            keyword_results: Results from keyword search
            top_k: Number of final results

        Returns:
            Fused and re-ranked results
        """
        # Build lookup tables
        chunk_data: Dict[str, Dict] = {}

        # Process semantic results
        for chunk_id, score, rank, metadata in semantic_results:
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = {
                    "chunk_id": chunk_id,
                    "metadata": metadata,
                    "semantic_score": 0.0,
                    "semantic_rank": 999,
                    "bm25_score": 0.0,
                    "bm25_rank": 999,
                }

            chunk_data[chunk_id]["semantic_score"] = score
            chunk_data[chunk_id]["semantic_rank"] = rank

        # Process keyword results
        for chunk_id, score, rank, metadata in keyword_results:
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = {
                    "chunk_id": chunk_id,
                    "metadata": metadata,
                    "semantic_score": 0.0,
                    "semantic_rank": 999,
                    "bm25_score": 0.0,
                    "bm25_rank": 999,
                }

            chunk_data[chunk_id]["bm25_score"] = score
            chunk_data[chunk_id]["bm25_rank"] = rank

        # Calculate RRF scores
        for chunk_id, data in chunk_data.items():
            semantic_rrf = 1.0 / (self.rrf_k + data["semantic_rank"])
            keyword_rrf = 1.0 / (self.rrf_k + data["bm25_rank"])

            # Weighted combination
            data["rrf_score"] = (
                self.semantic_weight * semantic_rrf +
                self.keyword_weight * keyword_rrf
            )

        # Sort by RRF score and take top_k
        sorted_chunks = sorted(
            chunk_data.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )[:top_k]

        # Convert to RetrievalResult objects
        results = []
        for data in sorted_chunks:
            # Get text from BM25 index if available
            chunk_text = ""
            chunk = self.bm25_index.get_chunk_by_id(data["chunk_id"])
            if chunk:
                chunk_text = chunk.text

            result = RetrievalResult(
                chunk_id=data["chunk_id"],
                case_reference=data["metadata"].get("case_reference", ""),
                chunk_text=chunk_text,
                section_type=data["metadata"].get("section_type", "unknown"),
                semantic_score=data["semantic_score"],
                semantic_rank=data["semantic_rank"],
                bm25_score=data["bm25_score"],
                bm25_rank=data["bm25_rank"],
                combined_score=data["rrf_score"],
                year=data["metadata"].get("year", 0),
                region=data["metadata"].get("region"),
                case_type=data["metadata"].get("case_type"),
            )
            results.append(result)

        return results

    def get_stats(self) -> Dict:
        """Get retriever statistics."""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "queries": 0,
            "avg_semantic_hits": 0.0,
            "avg_keyword_hits": 0.0,
        }
