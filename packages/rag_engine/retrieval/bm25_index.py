"""
BM25 keyword search index for legal documents.

Provides term-based search to complement semantic search,
particularly useful for legal terminology and exact phrase matching.

Supports two modes:
- Full mode: Stores complete DocumentChunk objects (more features, higher RAM)
- Lite mode: Stores only IDs and metadata (lower RAM, suitable for 8000+ cases)
"""

import pickle
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from rank_bm25 import BM25Okapi
import structlog

from ..config import DocumentChunk

logger = structlog.get_logger()


class BM25Index:
    """
    BM25-based keyword search index.

    Builds an inverted index over document chunks for fast
    keyword-based retrieval. Particularly effective for:
    - Legal terminology (section 213, Housing Act 2004)
    - Exact phrases
    - Technical terms

    Memory Usage (approximate):
    - Full mode: ~50 bytes/token + DocumentChunk overhead
    - Lite mode: ~50 bytes/token + 200 bytes/chunk (IDs only)

    For 8000 cases (~80k chunks, ~500 tokens each):
    - Full mode: ~4-6 GB RAM
    - Lite mode: ~2-3 GB RAM
    """

    # Legal stopwords to keep (important for legal search)
    LEGAL_KEEP_WORDS = {
        "section", "act", "order", "tribunal", "landlord", "tenant",
        "deposit", "protection", "scheme", "prescribed", "information",
        "damages", "award", "claim", "evidence", "finding"
    }

    def __init__(self, lite_mode: bool = False) -> None:
        """
        Initialize an empty BM25 index.

        Args:
            lite_mode: If True, only store chunk IDs and metadata (lower RAM).
                      Requires fetching full text from ChromaDB during search.
        """
        self._bm25: Optional[BM25Okapi] = None
        self._lite_mode = lite_mode

        # Full mode: store complete DocumentChunk objects
        self._documents: List[DocumentChunk] = []

        # Lite mode: store only essential data
        self._chunk_ids: List[str] = []
        self._chunk_metadata: List[Dict[str, Any]] = []  # Minimal metadata
        self._chunk_texts: List[str] = []  # Store texts separately for retrieval

        # Shared
        self._tokenized_docs: List[List[str]] = []
        self._chunk_id_to_index: Dict[str, int] = {}

    def build_index(self, chunks: List[DocumentChunk]) -> None:
        """
        Build BM25 index from document chunks.

        Args:
            chunks: List of document chunks to index
        """
        if not chunks:
            logger.warning("no_chunks_to_index")
            return

        self._tokenized_docs = []
        self._chunk_id_to_index = {}

        if self._lite_mode:
            # Lite mode: only store IDs, metadata, and texts (no full DocumentChunk)
            self._chunk_ids = []
            self._chunk_metadata = []
            self._chunk_texts = []

            for i, chunk in enumerate(chunks):
                tokens = self._tokenize(chunk.text)
                self._tokenized_docs.append(tokens)
                self._chunk_id_to_index[chunk.chunk_id] = i
                self._chunk_ids.append(chunk.chunk_id)
                self._chunk_texts.append(chunk.text)
                self._chunk_metadata.append({
                    "case_reference": chunk.case_reference,
                    "section_type": chunk.section_type,
                    "chunk_index": chunk.chunk_index,
                    "year": chunk.year,
                    "region": chunk.region,
                    "case_type": chunk.case_type,
                })
        else:
            # Full mode: store complete DocumentChunk objects
            self._documents = chunks
            for i, chunk in enumerate(chunks):
                tokens = self._tokenize(chunk.text)
                self._tokenized_docs.append(tokens)
                self._chunk_id_to_index[chunk.chunk_id] = i

        # Build BM25 index
        self._bm25 = BM25Okapi(self._tokenized_docs)

        logger.info(
            "bm25_index_built",
            num_documents=len(chunks),
            lite_mode=self._lite_mode,
            avg_doc_length=sum(len(t) for t in self._tokenized_docs) / len(self._tokenized_docs)
        )

    def search(
        self,
        query: str,
        top_k: int = 10
    ) -> List[Tuple[DocumentChunk, float, int]]:
        """
        Search for documents matching the query.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of (chunk, bm25_score, rank) tuples
        """
        if self._bm25 is None:
            logger.warning("bm25_index_not_built")
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        # Get BM25 scores for all documents
        scores = self._bm25.get_scores(query_tokens)

        # Get top-k indices
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]

        # Build results
        results = []
        for rank, idx in enumerate(top_indices, start=1):
            if scores[idx] > 0:  # Only include documents with non-zero scores
                if self._lite_mode:
                    # Reconstruct minimal DocumentChunk from stored data
                    meta = self._chunk_metadata[idx]
                    chunk = DocumentChunk(
                        chunk_id=self._chunk_ids[idx],
                        case_reference=meta["case_reference"],
                        text=self._chunk_texts[idx],
                        section_type=meta["section_type"],
                        chunk_index=meta["chunk_index"],
                        year=meta.get("year", 2020),
                        region=meta.get("region"),
                        case_type=meta.get("case_type"),
                    )
                else:
                    chunk = self._documents[idx]

                results.append((chunk, float(scores[idx]), rank))

        logger.debug(
            "bm25_search_complete",
            query_tokens=query_tokens[:5],
            num_results=len(results),
            top_score=results[0][1] if results else 0
        )

        return results

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text for BM25 indexing.

        Uses simple word tokenization while preserving legal terms.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        # Convert to lowercase
        text = text.lower()

        # Replace special characters with spaces (keep alphanumeric and hyphens)
        text = re.sub(r"[^\w\s\-]", " ", text)

        # Split into words
        tokens = text.split()

        # Basic filtering
        filtered = []
        for token in tokens:
            # Skip very short tokens (except important ones)
            if len(token) < 2 and token not in {"s", "a"}:
                continue

            # Skip pure numbers (except years)
            if token.isdigit():
                if len(token) == 4:  # Keep years
                    filtered.append(token)
                continue

            # Keep the token
            filtered.append(token)

        return filtered

    def save(self, path: Path) -> None:
        """
        Save index to disk.

        Args:
            path: Path to save the index
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "lite_mode": self._lite_mode,
            "tokenized_docs": self._tokenized_docs,
            "chunk_id_to_index": self._chunk_id_to_index,
        }

        if self._lite_mode:
            data["chunk_ids"] = self._chunk_ids
            data["chunk_metadata"] = self._chunk_metadata
            data["chunk_texts"] = self._chunk_texts
        else:
            data["documents"] = self._documents

        with open(path, "wb") as f:
            pickle.dump(data, f)

        logger.info("bm25_index_saved", path=str(path), lite_mode=self._lite_mode)

    def load(self, path: Path) -> bool:
        """
        Load index from disk.

        Args:
            path: Path to load the index from

        Returns:
            True if loaded successfully
        """
        path = Path(path)

        if not path.exists():
            logger.warning("bm25_index_not_found", path=str(path))
            return False

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)

            # Check if saved index was lite mode
            self._lite_mode = data.get("lite_mode", False)
            self._tokenized_docs = data["tokenized_docs"]
            self._chunk_id_to_index = data["chunk_id_to_index"]

            if self._lite_mode:
                self._chunk_ids = data["chunk_ids"]
                self._chunk_metadata = data["chunk_metadata"]
                self._chunk_texts = data["chunk_texts"]
                self._documents = []
                num_docs = len(self._chunk_ids)
            else:
                self._documents = data["documents"]
                self._chunk_ids = []
                self._chunk_metadata = []
                self._chunk_texts = []
                num_docs = len(self._documents)

            # Rebuild BM25 from tokenized docs
            self._bm25 = BM25Okapi(self._tokenized_docs)

            logger.info(
                "bm25_index_loaded",
                path=str(path),
                lite_mode=self._lite_mode,
                num_documents=num_docs
            )
            return True

        except Exception as e:
            logger.error("bm25_load_failed", path=str(path), error=str(e))
            return False

    def get_chunk_by_id(self, chunk_id: str) -> Optional[DocumentChunk]:
        """
        Get a chunk by its ID.

        Args:
            chunk_id: Chunk identifier

        Returns:
            DocumentChunk or None if not found
        """
        idx = self._chunk_id_to_index.get(chunk_id)
        if idx is not None:
            if self._lite_mode:
                meta = self._chunk_metadata[idx]
                return DocumentChunk(
                    chunk_id=self._chunk_ids[idx],
                    case_reference=meta["case_reference"],
                    text=self._chunk_texts[idx],
                    section_type=meta["section_type"],
                    chunk_index=meta["chunk_index"],
                    year=meta.get("year", 2020),
                    region=meta.get("region"),
                    case_type=meta.get("case_type"),
                )
            else:
                return self._documents[idx]
        return None

    def get_stats(self) -> Dict:
        """Get index statistics."""
        num_docs = len(self._chunk_ids) if self._lite_mode else len(self._documents)

        if num_docs == 0:
            return {"indexed_documents": 0, "lite_mode": self._lite_mode}

        if self._lite_mode:
            unique_refs = len(set(m["case_reference"] for m in self._chunk_metadata))
        else:
            unique_refs = len(set(d.case_reference for d in self._documents))

        return {
            "indexed_documents": num_docs,
            "lite_mode": self._lite_mode,
            "unique_case_references": unique_refs,
            "avg_tokens_per_doc": sum(len(t) for t in self._tokenized_docs) / len(self._tokenized_docs),
            "total_tokens": sum(len(t) for t in self._tokenized_docs),
        }

    @property
    def is_built(self) -> bool:
        """Check if index has been built."""
        if self._bm25 is None:
            return False
        if self._lite_mode:
            return len(self._chunk_ids) > 0
        return len(self._documents) > 0

    @property
    def lite_mode(self) -> bool:
        """Check if index is in lite mode."""
        return self._lite_mode
