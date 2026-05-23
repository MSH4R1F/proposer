#!/usr/bin/env python3
"""Ingest the selected BAILII RRO corpus into the
``housing_property_chamber_rro_v1`` RAG namespace (cross-domain build).

The pre-existing index for this namespace held a single placeholder
document (1 doc / 11 chunks), which is unusable for leave-one-out
retrieval. This script rebuilds the index from the SAME redacted decision
text used to build the gold set
(``data/raw/property_chamber_rro/decisions/<case_ref>/pdf_text_redacted.txt``),
so every gold case has real peers in the index and self-exclusion works
(``source_id == case_reference``).

Unlike ``run_govuk_pc_rro_ingest.py`` (which is bound to the GOV.UK
scraper's Pydantic models), this builds ``SourceDocument`` directly from
the BAILII PDF text — no GOV.UK scrape artefacts required.

It writes the BM25 + Chroma index under
``data/indices/housing_property_chamber_rro_v1/<corpus_version>/`` so that
``predict_all.py --rag-index-root data/indices`` resolves it.

Usage:
    PYTHONPATH=packages python scripts/ingest/run_bailii_rro_ingest.py \
        --gold data/gold_standard/housing_property_chamber_rro_v1.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from domain_core.registry import get_domain_spec  # noqa: E402
from domain_core.spec import SourceKind, SourcePublisher  # noqa: E402
from rag_engine.chunking.legal_chunker import LegalChunker  # noqa: E402
from rag_engine.config import RAGConfig  # noqa: E402
from rag_engine.embeddings import OpenAIEmbeddings  # noqa: E402
from rag_engine.ingestion.adapters import chunk_source_document  # noqa: E402
from rag_engine.ingestion.contracts import (  # noqa: E402
    ChunkKind,
    Forum,
    SourceDocument,
    SourceMetadata,
)
from rag_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from rag_engine.vectorstore.chroma_store import ChromaStore  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

logger = logging.getLogger("bailii_rro_ingest")

DOMAIN_ID = "housing.property_chamber.rro.v1"
NAMESPACE_ID = "housing_property_chamber_rro_v1"
CORPUS_VERSION = "research_seed_2026_05"
PARSER_VERSION = "bailii-rro-pymupdf-1.0.0"
REDACTED_ROOT = REPO_ROOT / "data" / "raw" / "property_chamber_rro" / "decisions"


def _load_gold_case_refs(gold_path: Path) -> list[tuple[str, str | None]]:
    refs: list[tuple[str, str | None]] = []
    with gold_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            refs.append((row["case_id"], row.get("decision_date")))
    return refs


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _build_source_doc(case_ref: str, decision_date: str | None, text: str) -> SourceDocument:
    meta = SourceMetadata(
        domain_id=DOMAIN_ID,
        domain_family="housing",
        forum=Forum.FIRST_TIER_PROPERTY_CHAMBER,
        source_id=case_ref,
        source_publisher=SourcePublisher.BAILII,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["rent_repayment_order"],
        decision_date=_parse_date(decision_date),
        source_url=f"https://www.bailii.org/uk/cases/UKFTT/PC/",
        source_license="BAILII (Crown copyright; FTT Property Chamber decision)",
        corpus_version=CORPUS_VERSION,
        parser_version=PARSER_VERSION,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        case_reference=case_ref,
        chunk_kind=ChunkKind.DOCUMENT_CHUNK,
    )
    return SourceDocument(metadata=meta, raw_text=text, title=case_ref, storage_path=None)


async def run(args: argparse.Namespace) -> int:
    gold_path = Path(args.gold)
    if not gold_path.is_absolute():
        gold_path = REPO_ROOT / gold_path
    refs = _load_gold_case_refs(gold_path)
    if not refs:
        raise SystemExit(f"no gold case refs in {gold_path}")
    logger.info("ingesting %d gold-corpus RRO cases", len(refs))

    spec = get_domain_spec(DOMAIN_ID)
    namespace = next((n for n in spec.retrieval_namespaces if n.namespace_id == NAMESPACE_ID), None)
    if namespace is None:
        raise SystemExit(f"namespace {NAMESPACE_ID} not in domain spec")

    base_cfg = RAGConfig.from_env()
    rag_cfg = RAGConfig.from_namespace(namespace, base=base_cfg, project_root=REPO_ROOT)

    # Redirect index outputs to data/indices/<ns>/<cv>/ so
    # predict_all.py --rag-index-root data/indices resolves it.
    out_dir = REPO_ROOT / "data" / "indices" / NAMESPACE_ID / CORPUS_VERSION
    chroma_dir = out_dir / "chroma"
    bm25_path = out_dir / "bm25.pkl"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    rag_cfg = rag_cfg.model_copy(update={"bm25_index_path": bm25_path, "chroma_persist_dir": chroma_dir})
    rag_cfg.ensure_directories()

    chunker = LegalChunker(chunk_size=rag_cfg.chunk_size, chunk_overlap=rag_cfg.chunk_overlap)
    embedder = OpenAIEmbeddings(config=rag_cfg)
    store = ChromaStore(config=rag_cfg)
    bm25 = BM25Index(lite_mode=rag_cfg.bm25_lite_mode)

    all_chunks = []
    n_docs = n_failed = 0
    chunk_kind_counts: dict[str, int] = {}

    sem = asyncio.Semaphore(args.concurrency)

    async def _ingest_one(case_ref: str, decision_date: str | None) -> int:
        nonlocal n_docs, n_failed
        text_path = REDACTED_ROOT / case_ref / "pdf_text_redacted.txt"
        if not text_path.exists():
            logger.warning("no redacted text for %s", case_ref)
            n_failed += 1
            return 0
        text = text_path.read_text(encoding="utf-8")
        if len(text.strip()) < 400:
            n_failed += 1
            return 0
        sd = _build_source_doc(case_ref, decision_date, text)
        chunks = chunk_source_document(sd, namespace_id=NAMESPACE_ID, chunker=chunker)
        if not chunks:
            n_failed += 1
            return 0
        async with sem:
            embs = await embedder.embed_texts([c.text for c in chunks])
            await store.add_chunks(chunks, embs)
        for c in chunks:
            ck = c.source_metadata.chunk_kind.value if c.source_metadata else "document_chunk"
            chunk_kind_counts[ck] = chunk_kind_counts.get(ck, 0) + 1
        all_chunks.extend(chunks)
        n_docs += 1
        return len(chunks)

    await asyncio.gather(*[_ingest_one(ref, dd) for ref, dd in refs])

    if all_chunks:
        bm25.build_index(all_chunks)
        bm25.save(bm25_path)

    manifest = {
        "domain_id": DOMAIN_ID,
        "domain_family": "housing",
        "forum": "first_tier_property_chamber",
        "corpus_version": CORPUS_VERSION,
        "embed_model": rag_cfg.embedding_model,
        "parser_version": PARSER_VERSION,
        "ingestion_finished_at": datetime.utcnow().isoformat(),
        "total_documents": n_docs,
        "total_chunks": len(all_chunks),
        "chunk_kind_counts": chunk_kind_counts,
        "documents_failed": n_failed,
        "bm25_index_path": str(bm25_path),
        "chroma_persist_dir": str(chroma_dir),
        "run_id": str(uuid.uuid4()),
    }
    (out_dir / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps(manifest, indent=2, default=str))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest BAILII RRO corpus into the RAG namespace.")
    p.add_argument("--gold", default="data/gold_standard/housing_property_chamber_rro_v1.jsonl")
    p.add_argument("--concurrency", type=int, default=4)
    return p


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return asyncio.run(run(_parser().parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
