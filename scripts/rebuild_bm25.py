#!/usr/bin/env python3
"""
Rebuild BM25 index from ChromaDB data.

This script extracts all documents from ChromaDB and rebuilds the BM25 index,
useful when the BM25 index is corrupted but ChromaDB is intact.
"""

import sys
from pathlib import Path

# Add packages directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "packages"))

import os
os.chdir(str(project_root))

import asyncio
from tqdm import tqdm
import structlog

from rag_engine.config import RAGConfig, DocumentChunk
from rag_engine.vectorstore.chroma_store import ChromaStore
from rag_engine.retrieval.bm25_index import BM25Index

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

async def rebuild_bm25(lite_mode: bool = False):
    """Rebuild BM25 index from ChromaDB."""
    
    # Initialize config
    config = RAGConfig(
        data_dir=Path("data"),
        chroma_persist_dir=Path("data/embeddings"),
        bm25_index_path=Path("data/embeddings/bm25_index.pkl"),
        bm25_lite_mode=lite_mode
    )
    
    # Initialize ChromaDB store
    print("Connecting to ChromaDB...")
    store = ChromaStore(config=config)
    
    # Get total count
    count = store._collection.count()
    print(f"Found {count:,} chunks in ChromaDB")
    
    if count == 0:
        print("No chunks to rebuild from!")
        return
    
    # Fetch all documents in batches
    print("Fetching all documents from ChromaDB...")
    batch_size = 5000
    all_chunks = []
    
    for offset in tqdm(range(0, count, batch_size), desc="Fetching batches"):
        results = store._collection.get(
            limit=min(batch_size, count - offset),
            offset=offset,
            include=["documents", "metadatas"]
        )
        
        # Reconstruct DocumentChunk objects
        for i, chunk_id in enumerate(results["ids"]):
            meta = results["metadatas"][i] if results["metadatas"] else {}
            text = results["documents"][i] if results["documents"] else ""

            # Extract year from metadata or case reference
            year = meta.get("year", 2020)  # Default to 2020 if missing
            if isinstance(year, str):
                try:
                    year = int(year)
                except:
                    year = 2020

            chunk = DocumentChunk(
                chunk_id=chunk_id,
                case_reference=meta.get("case_reference", ""),
                text=text,
                section_type=meta.get("section_type", "unknown"),
                chunk_index=meta.get("chunk_index", 0),
                year=year,
                region=meta.get("region") or None,
                case_type=meta.get("case_type") or None,
                token_count=meta.get("token_count", 0),
            )
            all_chunks.append(chunk)
    
    print(f"Fetched {len(all_chunks):,} chunks")
    
    # Build new BM25 index
    print(f"Building BM25 index (lite_mode={lite_mode})...")
    bm25 = BM25Index(lite_mode=lite_mode)
    bm25.build_index(all_chunks)
    
    # Save the index
    print(f"Saving BM25 index to {config.bm25_index_path}...")
    bm25.save(config.bm25_index_path)
    
    # Verify
    stats = bm25.get_stats()
    print("\n" + "=" * 50)
    print("BM25 INDEX REBUILT SUCCESSFULLY")
    print("=" * 50)
    print(f"Indexed documents: {stats['indexed_documents']:,}")
    print(f"Unique cases: {stats['unique_case_references']}")
    print(f"Avg tokens/doc: {stats['avg_tokens_per_doc']:.1f}")
    print(f"Total tokens: {stats['total_tokens']:,}")
    print(f"Lite mode: {stats['lite_mode']}")
    
    # Check file size
    file_size = config.bm25_index_path.stat().st_size
    print(f"Index file size: {file_size / (1024*1024):.1f} MB")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rebuild BM25 index from ChromaDB")
    parser.add_argument("--lite-mode", action="store_true", 
                       help="Use lite mode (lower RAM, recommended for 8000+ cases)")
    args = parser.parse_args()
    
    asyncio.run(rebuild_bm25(lite_mode=args.lite_mode))
