"""Cross-namespace leakage guard (slow, requires OPENAI_API_KEY + chroma).

Seed two namespaces in the same tmp Chroma collection and assert the
non-repairs chunks do NOT come back when we query with a repairs-only
filter. This protects against a regression where the BM25/Chroma
filter envelope diverges and lets cross-domain chunks leak into a
domain-scoped retrieval.
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
def test_repairs_query_does_not_leak_other_domain(tmp_path: Path) -> None:
    from rag_engine.chunking.legal_chunker import LegalChunker
    from rag_engine.config import (
        DocumentChunk,
        RAGConfig,
        RetrievalFilterEnvelope,
    )
    from rag_engine.embeddings.openai_embeddings import OpenAIEmbeddings
    from rag_engine.ingestion.adapters import chunk_source_document
    from rag_engine.source_metadata import SourceMetadata
    from rag_engine.vectorstore.chroma_store import ChromaStore
    from domain_core.spec import Forum, SourceKind, SourcePublisher

    from scripts.scrapers.housing_ombudsman.config import ScraperConfig
    from scripts.scrapers.housing_ombudsman.models import OmbudsmanCaseMetadata
    from scripts.scrapers.housing_ombudsman.to_source_document import (
        ombudsman_to_source_document,
    )

    rag_config = RAGConfig.from_env()
    rag_config.data_dir = tmp_path
    rag_config.chroma_persist_dir = tmp_path / "chroma"
    rag_config.bm25_index_path = tmp_path / "bm25.pkl"
    rag_config.collection_name = "leakage_guard_test"
    rag_config.ensure_directories()

    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)
    embeddings = OpenAIEmbeddings(config=rag_config)
    chroma = ChromaStore(config=rag_config)

    # Repairs document (housing.repairs_social.v1)
    repairs_meta = OmbudsmanCaseMetadata(
        case_reference="REPAIRS001",
        decision_date=date(2024, 1, 1),
        complaint_categories=["Property condition"],
        outcome_raw="Maladministration",
        outcome_normalized="maladministration",
        source_url="https://x/decisions/REPAIRS001/",
    )
    repairs_sd = ombudsman_to_source_document(
        repairs_meta,
        "Damp and mould reported in a council flat; landlord failed to act.",
        kept_matter_types=["repairs_damp_mould"],
        config=ScraperConfig(),
    )
    repairs_chunks = chunk_source_document(
        repairs_sd, namespace_id="housing_repairs_social_v1", chunker=chunker
    )

    # Non-repairs document (synthesised in a different namespace).
    foreign_meta = SourceMetadata(
        domain_id="housing.deposit.v1",
        domain_family="housing",
        forum=Forum.DEPOSIT_SCHEME_ADJUDICATION,
        source_id="DEPOSIT001",
        source_publisher=SourcePublisher.BAILII,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["deposit_deduction"],
        source_url="https://x/case/DEPOSIT001",
        corpus_version="legacy_test",
        parser_version="bailii-test",
    )
    foreign_chunks = [
        DocumentChunk(
            chunk_id="housing_deposit_v1::legacy_test::DEPOSIT001::0001::deadbeef",
            case_reference="DEPOSIT001",
            chunk_index=0,
            text="The tenant disputed deposit deductions for cleaning costs.",
            year=2024,
            source_metadata=foreign_meta,
        )
    ]

    chunks = repairs_chunks + foreign_chunks
    texts = [c.text for c in chunks]
    vectors = asyncio.run(embeddings.embed_documents(texts))
    asyncio.run(chroma.add_chunks(chunks, vectors))

    qvec = asyncio.run(embeddings.embed_documents(["damp and mould council flat"]))
    # Domain-scoped query.
    envelope = RetrievalFilterEnvelope(domain_ids=["housing.repairs_social.v1"])
    results = asyncio.run(chroma.query(qvec[0], n_results=10, filters=envelope))

    assert results, "domain-scoped query should still hit the repairs namespace"
    for r in results:
        md = r.metadata if hasattr(r, "metadata") else r.get("metadata", {})
        domain_id = (
            md.domain_id if hasattr(md, "domain_id") else md.get("domain_id")
        )
        assert domain_id == "housing.repairs_social.v1"
