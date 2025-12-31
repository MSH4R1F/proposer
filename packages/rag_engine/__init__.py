"""
RAG Engine for Proposer Legal Mediation System.

This package provides retrieval-augmented generation capabilities
for finding similar tribunal cases based on case facts.

Usage:
    from rag_engine import RAGPipeline, RAGConfig

    config = RAGConfig.from_env()
    pipeline = RAGPipeline(config)

    # Ingest documents
    await pipeline.ingest(pdf_dir="data/raw/bailii")

    # Query for similar cases
    result = await pipeline.retrieve("tenant deposit not protected")
"""

__version__ = "0.1.0"
__all__ = ["RAGPipeline", "RAGConfig"]

# Lazy imports to avoid circular dependencies at module load time
def __getattr__(name):
    if name == "RAGPipeline":
        from .pipeline import RAGPipeline
        return RAGPipeline
    elif name == "RAGConfig":
        from .config import RAGConfig
        return RAGConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
