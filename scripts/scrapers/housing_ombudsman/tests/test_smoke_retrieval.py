"""End-to-end smoke retrieval test (slow, requires OPENAI_API_KEY).

Ingests 2-3 fixture decisions through the real RAG pipeline machinery
into a tmp Chroma+BM25, then queries and asserts the top hit carries
``housing.repairs_social.v1`` metadata.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def _have_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _have_chroma() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _have_key(), reason="OPENAI_API_KEY not set")
@pytest.mark.skipif(not _have_chroma(), reason="chromadb not available")
def test_smoke_retrieval_repairs_social(tmp_path: Path) -> None:
    from rag_engine.chunking.legal_chunker import LegalChunker
    from rag_engine.config import RAGConfig
    from rag_engine.embeddings.openai_embeddings import OpenAIEmbeddings
    from rag_engine.ingestion.adapters import chunk_source_document
    from rag_engine.retrieval.bm25_index import BM25Index
    from rag_engine.vectorstore.chroma_store import ChromaStore

    from scripts.scrapers.housing_ombudsman.config import ScraperConfig
    from scripts.scrapers.housing_ombudsman.models import OmbudsmanCaseMetadata
    from scripts.scrapers.housing_ombudsman.to_source_document import (
        ombudsman_to_source_document,
    )

    cases = [
        OmbudsmanCaseMetadata(
            case_reference=f"20230000{i}",
            decision_date=date(2024, 1, i + 1),
            landlord_name="Acme Council",
            complaint_categories=["Property condition"],
            outcome_raw="Maladministration",
            outcome_normalized="maladministration",
            source_url=f"https://x/decisions/20230000{i}/",
        )
        for i in range(1, 4)
    ]
    bodies = [
        "The resident reported persistent damp and mould in their council flat. "
        "The landlord failed to inspect for 14 weeks despite repeated emails.",
        "Black mould was found in the bedroom of the social housing tenancy. "
        "The landlord did not undertake a survey under section 11.",
        "The complaint concerned cold draughts and a broken boiler in winter. "
        "The Ombudsman found the landlord's repair response inadequate.",
    ]

    docs = [
        ombudsman_to_source_document(
            meta,
            body,
            kept_matter_types=["repairs_damp_mould"],
            config=ScraperConfig(),
        )
        for meta, body in zip(cases, bodies)
    ]

    rag_config = RAGConfig.from_env()
    rag_config.data_dir = tmp_path
    rag_config.chroma_persist_dir = tmp_path / "chroma"
    rag_config.bm25_index_path = tmp_path / "bm25.pkl"
    rag_config.collection_name = "housing_ombudsman_test"
    rag_config.ensure_directories()

    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)
    all_chunks = []
    for sd in docs:
        all_chunks.extend(
            chunk_source_document(sd, namespace_id="housing_repairs_social_v1", chunker=chunker)
        )
    assert all_chunks

    embeddings = OpenAIEmbeddings(config=rag_config)
    vectors = asyncio.run(embeddings.embed_texts([c.text for c in all_chunks]))

    chroma = ChromaStore(config=rag_config)
    asyncio.run(chroma.add_chunks(all_chunks, vectors))
    bm25 = BM25Index()
    bm25.build_index(all_chunks)

    # Query.
    query = "damp and mould in a council flat"
    qvec = asyncio.run(embeddings.embed_texts([query]))
    results = asyncio.run(chroma.query(qvec[0], n_results=3))
    assert results, "expected non-empty results"
    top = results[0]
    md = top.metadata if hasattr(top, "metadata") else top.get("metadata", {})
    if hasattr(md, "domain_id"):
        assert md.domain_id == "housing.repairs_social.v1"
    else:
        assert md.get("domain_id") == "housing.repairs_social.v1"
        assert md.get("source_publisher") == "housing_ombudsman"
        assert md.get("corpus_version") == "research_seed_2026_05"
