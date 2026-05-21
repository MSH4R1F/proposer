"""Ingest the 50 redacted Employment Tribunal PDFs into the SHA-145 namespace.

Mirrors ``run_ombudsman_ingest.py`` but reads from the on-disk ET artifacts
that the SHA-147 scrape committed (``data/raw/employment/decisions/<safe_ref>/
pdf_text_redacted.txt`` + ``pdf_metadata.json``). The 50-doc corpus is the
exact same set the SHA-148 panel + gold-set was built from, so each gold
row has 49 peer documents to retrieve against under leave-one-out.

Why not call the scraper's full ETCaseMetadata round-trip? The committed
on-disk artifacts only retain the redacted body + a small extraction
metadata JSON — the full ETCaseMetadata only lived in the scraper
worktree's master_index. To keep ingest reproducible on main without
re-running the scrape, this script reads decision_date / source_url from
the gold JSONL (or the worktree master_index for the 50th non-gold case).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import click

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT, _REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from domain_core.registry import load_domain_specs  # noqa: E402
from domain_core.spec import (  # noqa: E402
    ChunkKind,
    DomainSpec,
    Forum,
    SourceKind,
    SourcePublisher,
)
from rag_engine.chunking.legal_chunker import LegalChunker  # noqa: E402
from rag_engine.config import DocumentChunk, RAGConfig  # noqa: E402
from rag_engine.embeddings.openai_embeddings import OpenAIEmbeddings  # noqa: E402
from rag_engine.ingestion.adapters import chunk_source_document  # noqa: E402
from rag_engine.ingestion.contracts import (  # noqa: E402
    CorpusManifest,
    IngestionRunManifest,
    SourceDocument,
)
from rag_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from rag_engine.source_metadata import SourceMetadata  # noqa: E402
from rag_engine.vectorstore.chroma_store import ChromaStore  # noqa: E402

logger = logging.getLogger(__name__)

DOMAIN_ID = "employment.unfair_dismissal.v1"
DECISIONS_ROOT = _REPO_ROOT / "data" / "raw" / "employment" / "decisions"
GOLD_PATH = _REPO_ROOT / "data" / "gold_standard" / "employment_unfair_dismissal_v1.jsonl"
WORKTREE_MASTER_INDEX = (
    _REPO_ROOT
    / "worktrees"
    / "sha-147-et-corpus"
    / "data"
    / "raw"
    / "employment"
    / "master_index.json"
)
PARSER_VERSION = "et-ingest-0.1.0"


def _load_per_case_metadata() -> Dict[str, Dict]:
    """case_ref -> {"decision_date": str|None, "source_url": str|None}."""
    out: Dict[str, Dict] = {}
    if GOLD_PATH.exists():
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            out[row["case_id"]] = {
                "decision_date": row.get("decision_date"),
                "source_url": row.get("source_url"),
            }
    if WORKTREE_MASTER_INDEX.exists():
        wt = json.loads(WORKTREE_MASTER_INDEX.read_text(encoding="utf-8"))
        for case_ref, entry in wt.items():
            if case_ref in out:
                continue
            if not entry.get("kept"):
                continue
            out[case_ref] = {
                "decision_date": entry.get("decision_date"),
                "source_url": entry.get("source_url"),
            }
    return out


def _parse_decision_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _content_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _build_source_document(
    case_ref: str,
    *,
    namespace_corpus_version: str,
    per_case: Dict[str, Dict],
) -> Optional[SourceDocument]:
    case_dir = DECISIONS_ROOT / case_ref
    text_path = case_dir / "pdf_text_redacted.txt"
    if not text_path.exists():
        logger.warning("redacted text missing for %s", case_ref)
        return None
    redacted_text = text_path.read_text(encoding="utf-8")
    if not redacted_text.strip():
        logger.warning("redacted text empty for %s", case_ref)
        return None

    meta_path = case_dir / "pdf_metadata.json"
    extraction_meta = {}
    if meta_path.exists():
        try:
            extraction_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    info = per_case.get(case_ref, {})
    decision_date = _parse_decision_date(info.get("decision_date"))
    source_url = info.get("source_url") or (
        f"https://www.gov.uk/employment-tribunal-decisions/{case_ref}"
    )

    metadata = SourceMetadata(
        domain_id=DOMAIN_ID,
        domain_family="employment",
        forum=Forum.EMPLOYMENT_TRIBUNAL,
        source_id=case_ref,
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["unfair_dismissal"],
        decision_date=decision_date,
        source_url=source_url,
        canonical_url=source_url,
        corpus_version=namespace_corpus_version,
        parser_version=PARSER_VERSION,
        content_sha256=_content_sha256(redacted_text),
        case_reference=case_ref,
        chunk_kind=ChunkKind.DOCUMENT_CHUNK,
    )

    return SourceDocument(
        metadata=metadata,
        raw_text=redacted_text,
        title=(extraction_meta.get("extraction_metadata") or {}).get("title"),
        storage_path=str(case_dir),
        extra={
            "raw_content_sha256": extraction_meta.get("pdf_sha256"),
            "redaction_stats": extraction_meta.get("redaction_stats", {}),
            "page_count": (extraction_meta.get("extraction_metadata") or {}).get("page_count"),
        },
    )


def _select_namespace(spec: DomainSpec):
    if not spec.retrieval_namespaces:
        raise RuntimeError(f"domain {spec.id} has no retrieval namespaces")
    return spec.retrieval_namespaces[0]


def _rag_config_for_namespace(
    namespace, *, base_rag: RAGConfig, data_dir: Optional[Path]
) -> RAGConfig:
    rag_config = RAGConfig.from_namespace(
        namespace, base=base_rag, project_root=_REPO_ROOT
    )
    if data_dir is not None:
        cv = namespace.corpus_version or "unversioned"
        ns_dir = data_dir / "indices" / namespace.namespace_id / cv
        rag_config.data_dir = data_dir
        rag_config.bm25_index_path = ns_dir / "bm25.pkl"
        rag_config.chroma_persist_dir = ns_dir / "chroma"
    return rag_config


async def _ingest_async(
    documents: List[SourceDocument],
    *,
    namespace,
    rag_config: RAGConfig,
    chunker: LegalChunker,
) -> Dict:
    chroma = ChromaStore(config=rag_config)
    bm25 = BM25Index(lite_mode=rag_config.bm25_lite_mode)
    embeddings = OpenAIEmbeddings(config=rag_config)

    all_chunks: List[DocumentChunk] = []
    chunk_kind_counts: Dict[str, int] = {}
    for sd in documents:
        chunks = chunk_source_document(
            sd, namespace_id=namespace.namespace_id, chunker=chunker
        )
        for c in chunks:
            ck = (
                c.source_metadata.chunk_kind.value
                if c.source_metadata
                else ChunkKind.DOCUMENT_CHUNK.value
            )
            chunk_kind_counts[ck] = chunk_kind_counts.get(ck, 0) + 1
        all_chunks.extend(chunks)

    if not all_chunks:
        return {
            "documents": len(documents),
            "chunks": 0,
            "chunk_kind_counts": chunk_kind_counts,
        }

    texts = [c.text for c in all_chunks]
    vectors = await embeddings.embed_texts(texts)
    await chroma.add_chunks(all_chunks, vectors)
    bm25.build_index(all_chunks)
    bm25.save(rag_config.bm25_index_path)

    return {
        "documents": len(documents),
        "chunks": len(all_chunks),
        "chunk_kind_counts": chunk_kind_counts,
        "collection_name": chroma.collection_name,
        "persist_dir": str(rag_config.chroma_persist_dir),
        "bm25_path": str(rag_config.bm25_index_path),
        "embedding_model": rag_config.embedding_model,
    }


def _write_manifests(
    *,
    namespace,
    spec: DomainSpec,
    rag_config: RAGConfig,
    started: datetime,
    finished: datetime,
    docs: int,
    chunks: int,
    chunk_kind_counts: Dict[str, int],
    notes: List[str],
):
    manifests_dir = rag_config.bm25_index_path.parent / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    corpus = CorpusManifest(
        domain_id=str(spec.id),
        domain_family=str(spec.family),
        forum=spec.forums[0],
        corpus_version=namespace.corpus_version or "unversioned",
        embed_model=rag_config.embedding_model,
        parser_version=PARSER_VERSION,
        ingestion_started_at=started,
        ingestion_finished_at=finished,
        total_documents=docs,
        total_chunks=chunks,
        chunk_kind_counts=chunk_kind_counts,
    )
    run_manifest = IngestionRunManifest(
        run_id=uuid.uuid4().hex,
        domain_id=str(spec.id),
        corpus_version=namespace.corpus_version or "unversioned",
        started_at=started,
        finished_at=finished,
        documents_attempted=docs,
        documents_ingested=docs,
        chunks_emitted=chunks,
        parser_version=PARSER_VERSION,
        embed_model=rag_config.embedding_model,
        notes=notes,
    )

    cv = namespace.corpus_version or "unversioned"
    corpus_path = manifests_dir / f"corpus_{cv}.json"
    run_path = manifests_dir / f"run_{run_manifest.run_id}.json"
    corpus_path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    run_path.write_text(run_manifest.model_dump_json(indent=2), encoding="utf-8")
    return corpus_path, run_path


@click.command()
@click.option(
    "--data-dir",
    type=click.Path(),
    default=None,
    help="Override base data dir (defaults to <repo_root>/data).",
)
@click.option("--max-docs", type=int, default=None)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(data_dir: Optional[str], max_docs: Optional[int], verbose: bool) -> None:
    """Ingest the 50 redacted ET PDFs into the SHA-145 namespace."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    data_path = Path(data_dir).expanduser().resolve() if data_dir else None
    per_case = _load_per_case_metadata()

    specs = load_domain_specs()
    spec = specs[DOMAIN_ID]
    namespace = _select_namespace(spec)
    cv = namespace.corpus_version or "unversioned"

    case_refs = sorted(p.name for p in DECISIONS_ROOT.iterdir() if p.is_dir())
    if max_docs is not None:
        case_refs = case_refs[:max_docs]

    documents: List[SourceDocument] = []
    for case_ref in case_refs:
        sd = _build_source_document(
            case_ref, namespace_corpus_version=cv, per_case=per_case
        )
        if sd is not None:
            documents.append(sd)

    if not documents:
        logger.error("no ET documents found under %s", DECISIONS_ROOT)
        sys.exit(1)

    base_rag = RAGConfig.from_env()
    rag_config = _rag_config_for_namespace(
        namespace, base_rag=base_rag, data_dir=data_path
    )
    rag_config.ensure_directories()

    chunker = LegalChunker(
        chunk_size=rag_config.chunk_size,
        chunk_overlap=rag_config.chunk_overlap,
    )

    logger.info(
        "ingesting %d ET documents into namespace=%s collection=%s persist=%s bm25=%s corpus_version=%s embed=%s",
        len(documents),
        namespace.namespace_id,
        rag_config.collection_name,
        rag_config.chroma_persist_dir,
        rag_config.bm25_index_path,
        cv,
        rag_config.embedding_model,
    )

    started = datetime.now(timezone.utc)
    stats = asyncio.run(
        _ingest_async(
            documents,
            namespace=namespace,
            rag_config=rag_config,
            chunker=chunker,
        )
    )
    finished = datetime.now(timezone.utc)

    corpus_path, run_path = _write_manifests(
        namespace=namespace,
        spec=spec,
        rag_config=rag_config,
        started=started,
        finished=finished,
        docs=stats["documents"],
        chunks=stats["chunks"],
        chunk_kind_counts=stats.get("chunk_kind_counts", {}),
        notes=[],
    )
    logger.info("wrote corpus manifest %s", corpus_path)
    logger.info("wrote run manifest %s", run_path)
    print(
        json.dumps(
            {
                "stats": stats,
                "corpus_manifest": str(corpus_path),
                "run_manifest": str(run_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
