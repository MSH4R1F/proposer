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
from ..config import DocumentChunk, RAGConfig

logger = structlog.get_logger()


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
        collection_name: str = "tribunal_cases"
    ) -> None:
        """
        Initialize ChromaDB store.

        Args:
            config: RAGConfig object (optional)
            persist_directory: Path for persistent storage
            collection_name: Name of the collection
        """
        if config:
            persist_dir = persist_directory or config.chroma_persist_dir
            self._collection_name = collection_name or config.collection_name
        else:
            persist_dir = persist_directory or Path("./data/embeddings")
            self._collection_name = collection_name

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

        # Add to collection
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

        self._stats["chunks_added"] += len(chunks)

        logger.debug(
            "chunks_added_to_chroma",
            count=len(chunks),
            total=self._collection.count()
        )

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
            where: Optional metadata filter (e.g., {"year": 2023})

        Returns:
            List of search results ordered by similarity (highest first)
        """
        self._stats["queries"] += 1

        # Build query kwargs
        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }

        if where:
            # Convert where clause for ChromaDB
            query_kwargs["where"] = self._build_where_clause(where)

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

                search_results.append(VectorSearchResult(
                    chunk_id=chunk_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    score=similarity,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {}
                ))

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
