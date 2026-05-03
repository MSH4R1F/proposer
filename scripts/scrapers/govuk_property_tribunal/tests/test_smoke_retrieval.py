"""SHA-126: smoke retrieval test for the RRO namespace (slow / live).

Skipped unless ``OPENAI_API_KEY`` is set. Builds a tiny tmp Chroma index
from a handful of fixture decisions and asserts a query for "unlicensed
HMO rent repayment 12 months" returns a result whose Phase-4 metadata is
correctly stamped (domain_id, forum, source_publisher, matter_types,
corpus_version).
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path

import pytest

from scripts.scrapers.govuk_property_tribunal.config import (
    CORPUS_VERSION,
    DOMAIN_ID,
    NAMESPACE_ID,
)
from scripts.scrapers.govuk_property_tribunal.models import (
    ArtefactKind,
    GovUKPCMetadata,
)
from scripts.scrapers.govuk_property_tribunal.to_source_document import (
    govuk_to_source_document,
)


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set; smoke retrieval test requires live embeddings",
    ),
]


_BODIES = [
    (
        "LON/00AG/HMF/2023/0001",
        "RRO decision: unlicensed HMO 12-month rent repayment",
        "The respondent committed an offence under section 72(1) of the Housing Act 2004. "
        "The property was an unlicensed HMO. The tribunal awards a rent repayment order "
        "of £6,000 covering the 12-month relevant period.",
        ["Housing Act 2004 s.72(1) (unlicensed HMO)"],
    ),
    (
        "LON/00BG/HMF/2023/0002",
        "RRO decision: selective licensing breach",
        "Failure to obtain a licence under section 95 of the Housing Act 2004 "
        "in a designated selective licensing area.",
        ["Housing Act 2004 s.95 (selective licensing)"],
    ),
]


def _meta(case_ref, title, body) -> GovUKPCMetadata:
    return GovUKPCMetadata(
        case_reference=case_ref,
        title=title,
        govuk_page_url=f"https://www.gov.uk/decisions/{case_ref}",
        base_path=f"/decisions/{case_ref}",
        decision_date=date(2023, 6, 15),
        raw_text=body,
        primary_asset_url=f"https://www.gov.uk/decisions/{case_ref}",
        primary_artefact_kind=ArtefactKind.HTML,
    )


def test_smoke_retrieval(tmp_path: Path):
    from rag_engine.chunking.legal_chunker import LegalChunker
    from rag_engine.config import RAGConfig
    from rag_engine.embeddings import OpenAIEmbeddings
    from rag_engine.ingestion.adapters import chunk_source_document
    from rag_engine.vectorstore.chroma_store import ChromaStore

    config = RAGConfig(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        data_dir=tmp_path,
        chroma_persist_dir=tmp_path / "chroma",
        bm25_index_path=tmp_path / "bm25.pkl",
        collection_name=f"smoke_{NAMESPACE_ID}",
    )
    config.ensure_directories()

    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)
    embedder = OpenAIEmbeddings(config=config)
    store = ChromaStore(config=config)

    all_chunks = []
    for case_ref, title, body, grounds in _BODIES:
        meta = _meta(case_ref, title, body)
        sd = govuk_to_source_document(meta, kept_grounds=grounds)
        chunks = chunk_source_document(sd, namespace_id=NAMESPACE_ID, chunker=chunker)
        all_chunks.extend(chunks)

    async def _ingest():
        texts = [c.text for c in all_chunks]
        embs = await embedder.embed_texts(texts)
        await store.add_chunks(all_chunks, embs)
        q = await embedder.embed_query("unlicensed HMO rent repayment 12 months")
        results = await store.query(q, n_results=3)
        return results

    results = asyncio.run(_ingest())
    assert results, "expected at least one result"
    top = results[0]
    md = top.metadata if hasattr(top, "metadata") else top
    # ChromaStore returns dicts; reconstruct via SourceMetadata.from_chroma_metadata
    from rag_engine.source_metadata import SourceMetadata

    sm = SourceMetadata.from_chroma_metadata(dict(md))
    assert sm.domain_id == DOMAIN_ID
    assert sm.forum.value == "first_tier_property_chamber"
    assert sm.source_publisher.value == "govuk"
    assert "rent_repayment_order" in sm.matter_types
    assert sm.corpus_version == CORPUS_VERSION
