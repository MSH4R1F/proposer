"""
CLI interface for RAG Engine.

Provides commands for:
- Ingesting PDF documents
- Querying the index
- Viewing statistics
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import click
import structlog

from .config import RAGConfig
from .pipeline import RAGPipeline

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def run_async(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
@click.option(
    "--data-dir",
    type=click.Path(exists=False),
    default="./data",
    help="Base data directory"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose logging"
)
@click.pass_context
def cli(ctx, data_dir: str, verbose: bool):
    """RAG Engine CLI for tribunal case retrieval."""
    ctx.ensure_object(dict)

    # Configure logging level
    import logging
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    # Create config
    ctx.obj["config"] = RAGConfig(
        data_dir=Path(data_dir),
        chroma_persist_dir=Path(data_dir) / "embeddings",
        bm25_index_path=Path(data_dir) / "embeddings" / "bm25_index.pkl"
    )


@cli.command()
@click.option(
    "--pdf-dir",
    type=click.Path(exists=True),
    required=True,
    help="Directory containing PDF files to ingest"
)
@click.option(
    "--batch-size",
    type=int,
    default=10,
    help="Number of chunks to embed at once"
)
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    help="Skip chunks that already exist"
)
@click.pass_context
def ingest(ctx, pdf_dir: str, batch_size: int, skip_existing: bool):
    """Ingest PDF documents into the RAG index."""
    config = ctx.obj["config"]

    click.echo(f"Initializing RAG pipeline...")
    pipeline = RAGPipeline(config=config)

    click.echo(f"Ingesting PDFs from: {pdf_dir}")
    click.echo(f"Batch size: {batch_size}, Skip existing: {skip_existing}")

    stats = run_async(
        pipeline.ingest(
            pdf_dir=Path(pdf_dir),
            batch_size=batch_size,
            skip_existing=skip_existing
        )
    )

    click.echo("\n" + "=" * 50)
    click.echo("INGESTION COMPLETE")
    click.echo("=" * 50)
    click.echo(f"PDFs processed: {stats.get('processed', 0)}")
    click.echo(f"PDFs skipped: {stats.get('skipped', 0)}")
    click.echo(f"PDFs failed: {stats.get('failed', 0)}")
    click.echo(f"Chunks created: {stats.get('chunks_created', 0)}")
    click.echo(f"Chunks embedded: {stats.get('chunks_embedded', 0)}")

    if "embedding_stats" in stats:
        embed_stats = stats["embedding_stats"]
        click.echo(f"\nEmbedding Stats:")
        click.echo(f"  Total tokens: {embed_stats.get('total_tokens', 0):,}")
        click.echo(f"  Estimated cost: ${embed_stats.get('estimated_cost_usd', 0):.4f}")


@cli.command()
@click.argument("query_text")
@click.option(
    "--top-k",
    type=int,
    default=5,
    help="Number of results to return"
)
@click.option(
    "--region",
    type=str,
    default=None,
    help="Filter by region code (e.g., LON, CHI, MAN)"
)
@click.option(
    "--year",
    type=int,
    default=None,
    help="Filter by year"
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Output results as JSON"
)
@click.pass_context
def query(
    ctx,
    query_text: str,
    top_k: int,
    region: Optional[str],
    year: Optional[int],
    json_output: bool
):
    """Query the RAG index for similar cases."""
    config = ctx.obj["config"]

    pipeline = RAGPipeline(config=config)

    # Build where clause
    where = {}
    if region:
        where["region"] = region.upper()
    if year:
        where["year"] = year

    result = run_async(
        pipeline.retrieve(
            query=query_text,
            top_k=top_k,
            where=where if where else None,
            query_region=region
        )
    )

    if json_output:
        output = {
            "query": result.query,
            "confidence": result.confidence,
            "is_uncertain": result.is_uncertain,
            "uncertainty_reason": result.uncertainty_reason,
            "retrieval_time_ms": result.retrieval_time_ms,
            "total_candidates": result.total_candidates,
            "results": [
                {
                    "case_reference": r.case_reference,
                    "section_type": r.section_type,
                    "year": r.year,
                    "region": r.region,
                    "semantic_score": r.semantic_score,
                    "bm25_score": r.bm25_score,
                    "combined_score": r.combined_score,
                    "rerank_score": r.rerank_score,
                    "relevance_explanation": r.relevance_explanation,
                    "chunk_text": r.chunk_text[:500] + "..." if len(r.chunk_text) > 500 else r.chunk_text
                }
                for r in result.results
            ]
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Pretty print results
    click.echo("\n" + "=" * 60)
    click.echo("QUERY RESULTS")
    click.echo("=" * 60)
    click.echo(f"Query: {query_text[:100]}...")
    click.echo(f"Confidence: {result.confidence:.2%}")
    click.echo(f"Time: {result.retrieval_time_ms:.0f}ms")
    click.echo(f"Total candidates: {result.total_candidates}")

    if result.is_uncertain:
        click.echo(f"\n⚠️  UNCERTAINTY: {result.uncertainty_reason}")

    click.echo("\n" + "-" * 60)

    for i, r in enumerate(result.results, start=1):
        click.echo(f"\n#{i} - {r.case_reference} ({r.year})")
        click.echo(f"   Region: {r.region or 'Unknown'} | Section: {r.section_type}")
        click.echo(f"   Scores: semantic={r.semantic_score:.3f}, bm25={r.bm25_score:.3f}, combined={r.combined_score:.4f}")
        if r.rerank_score:
            click.echo(f"   Rerank score: {r.rerank_score:.4f}")
        if r.relevance_explanation:
            click.echo(f"   Why relevant: {r.relevance_explanation}")
        click.echo(f"   Preview: {r.chunk_text[:200]}...")


@cli.command()
@click.pass_context
def stats(ctx):
    """Show index statistics."""
    config = ctx.obj["config"]

    pipeline = RAGPipeline(config=config)

    stats = run_async(pipeline.get_stats())

    click.echo("\n" + "=" * 50)
    click.echo("INDEX STATISTICS")
    click.echo("=" * 50)

    # Vectorstore stats
    vs = stats.get("vectorstore", {})
    click.echo("\nVector Store (ChromaDB):")
    click.echo(f"  Collection: {vs.get('collection_name', 'N/A')}")
    click.echo(f"  Total chunks: {vs.get('total_chunks', 0):,}")
    click.echo(f"  Years: {vs.get('sample_years', [])}")
    click.echo(f"  Regions: {vs.get('sample_regions', [])}")

    # BM25 stats
    bm25 = stats.get("bm25", {})
    click.echo("\nBM25 Index:")
    click.echo(f"  Indexed documents: {bm25.get('indexed_documents', 0):,}")
    click.echo(f"  Unique cases: {bm25.get('unique_case_references', 0)}")
    if bm25.get("avg_tokens_per_doc"):
        click.echo(f"  Avg tokens/doc: {bm25['avg_tokens_per_doc']:.1f}")

    # Embedding stats
    embed = stats.get("embeddings", {})
    if embed.get("total_tokens"):
        click.echo("\nEmbedding Usage:")
        click.echo(f"  Total tokens: {embed['total_tokens']:,}")
        click.echo(f"  API calls: {embed.get('api_calls', 0)}")
        click.echo(f"  Estimated cost: ${embed.get('estimated_cost_usd', 0):.4f}")


@cli.command()
@click.confirmation_option(prompt="Are you sure you want to clear the index?")
@click.pass_context
def clear(ctx):
    """Clear all indexed data."""
    config = ctx.obj["config"]

    pipeline = RAGPipeline(config=config)
    run_async(pipeline.clear_index())

    click.echo("Index cleared successfully.")


@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.pass_context
def test_extract(ctx, pdf_path: str):
    """Test PDF extraction on a single file."""
    from .extractors.pdf_extractor import PDFExtractor
    from .extractors.text_cleaner import TextCleaner

    extractor = PDFExtractor()
    cleaner = TextCleaner()

    try:
        doc = extractor.extract_case_document(Path(pdf_path))
        doc.full_text = cleaner.clean(doc.full_text)

        click.echo("\n" + "=" * 50)
        click.echo("EXTRACTION RESULTS")
        click.echo("=" * 50)
        click.echo(f"Case Reference: {doc.case_reference}")
        click.echo(f"Year: {doc.year}")
        click.echo(f"Region: {doc.region}")
        click.echo(f"Case Type: {doc.case_type}")
        click.echo(f"Title: {doc.title}")
        click.echo(f"Text Length: {len(doc.full_text):,} characters")
        click.echo(f"\nFirst 500 characters:")
        click.echo("-" * 50)
        click.echo(doc.full_text[:500])

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


if __name__ == "__main__":
    cli()
