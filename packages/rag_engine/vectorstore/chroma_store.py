"""
ChromaDB vector store implementation.

Provides persistent vector storage using ChromaDB for
similarity search over tribunal case embeddings.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings
import structlog

from .base import BaseVectorStore, VectorSearchResult
from ..config import DocumentChunk, RAGConfig, RetrievalFilterEnvelope

logger = structlog.get_logger()

_DEFAULT_CHROMA_INSERT_BATCH_SIZE = 5000


class ChromaStore(BaseVectorStore):
    """
    ChromaDB-based vector store for tribunal cases.

    Features:
    - Persistent storage to disk
    - Metadata filtering (year, region, case_type)
    - Efficient similarity search
    """

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        persist_directory: Optional[Path] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        """
        Initialize ChromaDB store.

        Args:
            config: RAGConfig object (optional)
            persist_directory: Path for persistent storage
            collection_name: Explicit collection name. If omitted, the
                collection name from ``config.collection_name`` is used
                (which is what ``RAGConfig.from_namespace`` populates).
                Defaults to ``"tribunal_cases"`` only when neither a
                config nor an explicit name is provided — i.e. legacy
                no-arg construction.
        """
        if config:
            persist_dir = persist_directory or config.chroma_persist_dir
            self._collection_name = collection_name or config.collection_name
        else:
            persist_dir = persist_directory or Path("./data/embeddings")
            self._collection_name = collection_name or "tribunal_cases"

        # Ensure directory exists
        persist_dir = Path(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )

        # Stats tracking
        self._stats = {
            "chunks_added": 0,
            "queries": 0,
        }

        logger.info(
            "chroma_store_initialized",
            persist_directory=str(persist_dir),
            collection=self._collection_name,
            existing_count=self._collection.count()
        )

    @property
    def collection_name(self) -> str:
        """Return collection name."""
        return self._collection_name

    async def add_chunks(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]]
    ) -> None:
        """
        Add document chunks with embeddings to ChromaDB.

        Args:
            chunks: List of document chunks
            embeddings: Corresponding embedding vectors
        """
        if not chunks or not embeddings:
            return

        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings"
            )

        # Prepare data for ChromaDB
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [chunk.to_chroma_metadata() for chunk in chunks]

        batch_size = self._max_insert_batch_size()
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            self._collection.add(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end]
            )

            batch_count = min(end, len(chunks)) - start
            self._stats["chunks_added"] += batch_count

            logger.debug(
                "chunks_added_to_chroma",
                count=batch_count,
                total=self._collection.count(),
                batch_start=start,
                batch_size=batch_size,
            )

    def _max_insert_batch_size(self) -> int:
        """Return Chroma's insert limit, with a conservative fallback."""
        get_max_batch_size = getattr(self._client, "get_max_batch_size", None)
        if callable(get_max_batch_size):
            try:
                return max(1, int(get_max_batch_size()))
            except (TypeError, ValueError):
                pass

        max_batch_size = getattr(self._client, "max_batch_size", None)
        if max_batch_size is not None:
            try:
                return max(1, int(max_batch_size))
            except (TypeError, ValueError):
                pass

        return _DEFAULT_CHROMA_INSERT_BATCH_SIZE

    async def query(
        self,
        embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        *,
        filters: Optional[RetrievalFilterEnvelope] = None,
    ) -> List[VectorSearchResult]:
        """
        Query for similar vectors.

        Args:
            embedding: Query embedding vector.
            n_results: Number of results to return.
            where: Legacy raw ChromaDB-style filter dict (e.g., ``{"year": 2023}``).
                Backward-compat path used by the deposit pipeline.
            filters: SHA-20 Phase 4
                :class:`~rag_engine.config.RetrievalFilterEnvelope`. When
                provided, takes precedence over ``where`` and is the
                envelope the BM25 side must also receive — see
                ``HybridRetriever`` for enforcement.

        Returns:
            List of search results ordered by similarity (highest first).
            Phase-4 filters that cannot be expressed in Chroma's
            where-clause (e.g. ``matter_type``) are applied in Python on
            the result set so semantic + keyword backends agree.
        """
        self._stats["queries"] += 1

        # Build query kwargs
        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }

        chroma_where: Optional[Dict[str, Any]]
        if filters is not None:
            chroma_where = filters.to_chroma_where()
        elif where:
            chroma_where = self._build_where_clause(where)
        else:
            chroma_where = None
        if chroma_where:
            query_kwargs["where"] = chroma_where

        # Execute query
        results = self._collection.query(**query_kwargs)

        # Convert to VectorSearchResult objects
        search_results = []

        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                # ChromaDB returns distances, convert to similarity score
                # For cosine distance: similarity = 1 - distance
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 - distance

                meta = (
                    results["metadatas"][0][i]
                    if results["metadatas"]
                    else {}
                ) or {}
                search_results.append(VectorSearchResult(
                    chunk_id=chunk_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    score=similarity,
                    metadata=meta,
                ))

        # Phase-4 post-filter for fields Chroma can't express in where.
        # Currently this is matter_type (stored as "|"-joined string).
        # Applying the same envelope here as BM25 keeps the two backends
        # aligned. matches_metadata also re-checks excluded_source_ids /
        # date filters, which is harmless since they were already applied
        # by Chroma's where; the duplication is the correctness guarantee.
        if filters is not None and not filters.is_empty():
            search_results = [
                r for r in search_results if filters.matches_metadata(r.metadata)
            ]

        logger.debug(
            "chroma_query_complete",
            n_results=len(search_results),
            top_score=search_results[0].score if search_results else 0
        )

        return search_results

    def _build_where_clause(self, where: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build ChromaDB-compatible where clause.

        Supports simple key-value filters and ranges.

        Args:
            where: Filter dictionary

        Returns:
            ChromaDB where clause
        """
        # Simple case: single conditions
        if len(where) == 1:
            key, value = list(where.items())[0]
            if isinstance(value, dict):
                # Range query like {"year": {"$gte": 2020}}
                return {key: value}
            else:
                return {key: {"$eq": value}}

        # Multiple conditions: use $and
        conditions = []
        for key, value in where.items():
            if isinstance(value, dict):
                conditions.append({key: value})
            else:
                conditions.append({key: {"$eq": value}})

        return {"$and": conditions}

    async def delete_collection(self) -> None:
        """Delete the entire collection."""
        self._client.delete_collection(self._collection_name)
        logger.info("collection_deleted", name=self._collection_name)

        # Recreate empty collection
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        count = self._collection.count()

        # Get full statistics by scanning all chunks
        # This ensures accuracy for year/region distributions
        from collections import Counter
        
        years = []
        regions = []
        case_types = []
        case_refs = set()
        
        if count == 0:
            # Empty collection
            pass
        else:
            # Scan all chunks in batches for accurate statistics
            batch_size = 5000
            logger.info(
                "collecting_stats",
                total_chunks=count,
                message="Scanning all chunks for accurate statistics..."
            )
            
            for offset in range(0, count, batch_size):
                results = self._collection.get(
                    limit=min(batch_size, count - offset),
                    offset=offset,
                    include=["metadatas"]
                )
                
                if results.get("metadatas"):
                    for meta in results["metadatas"]:
                        if meta.get("year"):
                            years.append(meta["year"])
                        if meta.get("region"):
                            regions.append(meta["region"])
                        if meta.get("case_type"):
                            case_types.append(meta["case_type"])
                        if meta.get("case_reference"):
                            case_refs.add(meta["case_reference"])
        
        # Calculate distributions
        year_counts = Counter(years)
        region_counts = Counter(regions)
        case_type_counts = Counter(case_types)

        return {
            "collection_name": self._collection_name,
            "total_chunks": count,
            "unique_cases": len(case_refs),
            "years": sorted(set(years)),
            "year_distribution": dict(sorted(year_counts.items())),
            "regions": sorted(set(regions)),
            "region_distribution": dict(sorted(region_counts.items())),
            "case_types": sorted(set(case_types)),
            "top_case_types": dict(case_type_counts.most_common(10)),
        }

    async def chunk_exists(self, chunk_id: str) -> bool:
        """Check if a chunk exists in the collection."""
        try:
            result = self._collection.get(ids=[chunk_id])
            return len(result["ids"]) > 0
        except Exception:
            return False

    async def get_all_chunk_ids(self) -> List[str]:
        """Get all chunk IDs in the collection."""
        # ChromaDB doesn't have a great way to list all IDs
        # We'll peek at the max possible
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.get(
            limit=count,
            include=[]  # Don't include documents/embeddings for efficiency
        )
        return results["ids"]

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            **self._stats,
            "total_in_collection": self._collection.count()
        }
