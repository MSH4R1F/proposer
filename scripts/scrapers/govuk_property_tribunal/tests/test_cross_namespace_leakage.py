"""SHA-126: cross-namespace leakage test (slow / live).

Seeds three tmp Chroma collections — deposit, repairs, RRO — with
deliberately distinct fixture content. Asserts that:

* a deposit query does NOT return RRO chunks,
* a repairs query does NOT return RRO chunks,
* an RRO query does NOT return deposit/repairs chunks.

Skipped unless ``OPENAI_API_KEY`` is set.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path

import pytest

from domain_core.spec import Forum, SourceKind, SourcePublisher

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
        reason="OPENAI_API_KEY not set; cross-namespace leakage test requires live embeddings",
    ),
]


def _build_other_source_document(
    *,
    domain_id: str,
    domain_family: str,
    forum: Forum,
    matter_types: list,
    case_ref: str,
    text: str,
):
    """Build a SourceDocument for a non-RRO namespace (deposit/repairs)."""
    from rag_engine.ingestion.contracts import SourceDocument
    from rag_engine.source_metadata import SourceMetadata

    md = SourceMetadata(
        domain_id=domain_id,
        domain_family=domain_family,
        forum=forum,
        source_id=case_ref,
        source_publisher=SourcePublisher.BAILII,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=matter_types,
        decision_date=date(2023, 1, 15),
        source_url=f"https://example.test/{case_ref}",
        source_license="OGL-3.0",
        corpus_version=CORPUS_VERSION,
        parser_version="other-0.1",
        case_reference=case_ref,
    )
    return SourceDocument(metadata=md, raw_text=text, title=case_ref)


def test_cross_namespace_leakage(tmp_path: Path):
    from rag_engine.chunking.legal_chunker import LegalChunker
    from rag_engine.config import RAGConfig
    from rag_engine.embeddings import OpenAIEmbeddings
    from rag_engine.ingestion.adapters import chunk_source_document
    from rag_engine.source_metadata import SourceMetadata
    from rag_engine.vectorstore.chroma_store import ChromaStore

    chunker = LegalChunker(chunk_size=120, chunk_overlap=20)

    namespaces = {
        "deposit": dict(
            collection="ns_deposit",
            sd=_build_other_source_document(
                domain_id="housing.deposit.v1",
                domain_family="housing",
                forum=Forum.DEPOSIT_SCHEME_ADJUDICATION,
                matter_types=["deposit_deduction"],
                case_ref="DEP_2023_0001",
                text=(
                    "BACKGROUND The tenant paid a deposit of £1,200. "
                    "FACTS The landlord deducted £400 for cleaning. "
                    "DECISION The adjudicator awarded the tenant £300 of the deposit back."
                ),
            ),
        ),
        "repairs": dict(
            collection="ns_repairs",
            sd=_build_other_source_document(
                domain_id="housing.repairs.social.v1",
                domain_family="housing",
                forum=Forum.HOUSING_OMBUDSMAN,
                matter_types=["disrepair", "damp_and_mould"],
                case_ref="HO_2023_0001",
                text=(
                    "BACKGROUND The complainant reported damp and mould in the kitchen. "
                    "FACTS The landlord delayed repairs for 14 months. "
                    "DECISION Severe maladministration found; £1,200 compensation."
                ),
            ),
        ),
        "rro": dict(
            collection="ns_rro",
            sd=govuk_to_source_document(
                GovUKPCMetadata(
                    case_reference="LON/00AG/HMF/2023/0099",
                    title="RRO decision: unlicensed HMO",
                    govuk_page_url="https://www.gov.uk/decisions/lon-00ag-hmf-2023-0099",
                    base_path="/decisions/lon-00ag-hmf-2023-0099",
                    decision_date=date(2023, 6, 15),
                    raw_text=(
                        "BACKGROUND The applicants rented an HMO from January 2022. "
                        "FACTS The respondent failed to obtain an HMO licence under "
                        "section 72(1) of the Housing Act 2004. "
                        "DECISION We award a rent repayment order of £6,000."
                    ),
                    primary_asset_url="https://www.gov.uk/decisions/lon-00ag-hmf-2023-0099",
                    primary_artefact_kind=ArtefactKind.HTML,
                ),
                kept_grounds=["Housing Act 2004 s.72(1) (unlicensed HMO)"],
            ),
        ),
    }

    async def _seed_and_query():
        leakage_results = {}
        for ns_name, info in namespaces.items():
            cfg = RAGConfig(
                openai_api_key=os.environ["OPENAI_API_KEY"],
                data_dir=tmp_path / ns_name,
                chroma_persist_dir=tmp_path / ns_name / "chroma",
                bm25_index_path=tmp_path / ns_name / "bm25.pkl",
                collection_name=info["collection"],
            )
            cfg.ensure_directories()
            embedder = OpenAIEmbeddings(config=cfg)
            store = ChromaStore(config=cfg)
            chunks = chunk_source_document(
                info["sd"], namespace_id=ns_name + "_v1", chunker=chunker
            )
            embs = await embedder.embed_texts([c.text for c in chunks])
            await store.add_chunks(chunks, embs)
            info["embedder"] = embedder
            info["store"] = store

        # Deposit query against deposit store
        results = {}
        queries = {
            "deposit": "tenancy deposit deduction cleaning",
            "repairs": "damp and mould repairs delayed",
            "rro": "unlicensed HMO rent repayment order",
        }
        for ns_name, info in namespaces.items():
            q = await info["embedder"].embed_query(queries[ns_name])
            res = await info["store"].query(q, n_results=2)
            results[ns_name] = res
        return results

    results = asyncio.run(_seed_and_query())

    # Reconstruct domain_id of top hit per namespace and assert no leakage.
    from rag_engine.source_metadata import SourceMetadata

    for ns_name, res in results.items():
        assert res, f"namespace {ns_name} returned no results"
        top_meta = res[0].metadata if hasattr(res[0], "metadata") else res[0]
        sm = SourceMetadata.from_chroma_metadata(dict(top_meta))
        if ns_name == "deposit":
            assert sm.domain_id == "housing.deposit.v1"
        elif ns_name == "repairs":
            assert sm.domain_id == "housing.repairs.social.v1"
        elif ns_name == "rro":
            assert sm.domain_id == DOMAIN_ID
