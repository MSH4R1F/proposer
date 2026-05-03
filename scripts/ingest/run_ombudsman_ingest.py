"""SHA-125: Ingest Housing Ombudsman determinations into the RAG corpus.

Reads kept records from ``master_index.json``, builds
:class:`SourceDocument` instances via
:func:`ombudsman_to_source_document`, chunks them through the shared
:func:`chunk_source_document` adapter (NOT a private chunker), embeds
via :class:`OpenAIEmbeddings`, and writes both ChromaStore and BM25
artefacts under the ``housing_repairs_social_v1`` namespace.

Outputs:

* ChromaDB persistence under
  ``data/indices/housing_repairs_social_v1/<corpus_version>/chroma/``
* BM25 pickle at the namespace-specified path
* :class:`CorpusManifest` + :class:`IngestionRunManifest` JSON files
  next to the BM25 index for audit
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import click

# Ensure repo root + packages/ are importable when invoked as a script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT, _REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from domain_core.registry import load_domain_specs  # noqa: E402
from domain_core.spec import ChunkKind, DomainSpec  # noqa: E402
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
from rag_engine.vectorstore.chroma_store import ChromaStore  # noqa: E402

from scripts.scrapers.housing_ombudsman.config import ScraperConfig  # noqa: E402
from scripts.scrapers.housing_ombudsman.models import OmbudsmanCaseMetadata  # noqa: E402
from scripts.scrapers.housing_ombudsman.progress import RunLog  # noqa: E402
from scripts.scrapers.housing_ombudsman.to_source_document import (  # noqa: E402
    ombudsman_to_source_document,
)

logger = logging.getLogger(__name__)

DOMAIN_ID = "housing.repairs_social.v1"


def _select_namespace(spec: DomainSpec):
    """Pick the single retrieval namespace for the housing repairs domain."""
    if not spec.retrieval_namespaces:
        raise RuntimeError(f"domain {spec.id} has no retrieval namespaces")
    if len(spec.retrieval_namespaces) > 1:
        # Pick the one whose corpus_root points at housing_ombudsman.
        for ns in spec.retrieval_namespaces:
            if "housing_ombudsman" in (ns.corpus_root or ""):
                return ns
    return spec.retrieval_namespaces[0]


def _resolve_data_dir(data_dir: Optional[str]) -> Optional[Path]:
    """Resolve ``--data-dir`` as the base data directory, if supplied."""
    if not data_dir:
        return None
    return Path(data_dir).expanduser().resolve()


def _scraper_config_for_data_dir(data_dir: Optional[str]) -> ScraperConfig:
    """Build scraper config whose raw paths live under ``data_dir``.

    ``--data-dir /tmp/proposer-data`` means:

    * raw scraper output/input: ``/tmp/proposer-data/raw/housing_ombudsman``
    * indices/manifests: ``/tmp/proposer-data/indices/...``
    """
    data_root = _resolve_data_dir(data_dir)
    if data_root is None:
        return ScraperConfig()
    return ScraperConfig(
        output_subdir=str(data_root / "raw" / "housing_ombudsman")
    )


def _rag_config_for_namespace(
    namespace,
    *,
    base_rag: RAGConfig,
    data_dir: Optional[str],
) -> RAGConfig:
    """Build namespace RAG config, honoring ``--data-dir`` for outputs."""
    rag_config = RAGConfig.from_namespace(
        namespace, base=base_rag, project_root=_REPO_ROOT
    )
    data_root = _resolve_data_dir(data_dir)
    if data_root is None:
        return rag_config

    corpus_version = namespace.corpus_version or "unversioned"
    namespace_dir = data_root / "indices" / namespace.namespace_id / corpus_version
    rag_config.data_dir = data_root
    rag_config.bm25_index_path = namespace_dir / "bm25.pkl"
    rag_config.chroma_persist_dir = namespace_dir / "chroma"
    return rag_config


def _load_kept_records(scraper_config: ScraperConfig) -> List[Dict]:
    """Read master_index.json and return only kept entries."""
    runlog = RunLog(
        runs_dir=scraper_config.runs_dir,
        master_index_path=scraper_config.master_index_path,
    )
    kept = runlog.kept_entries()
    out: List[Dict] = []
    for case_ref, entry in kept.items():
        if not entry.raw_storage_path:
            continue
        case_dir = Path(entry.raw_storage_path)
        parsed_path = case_dir / "parsed.json"
        raw_path = case_dir / "raw.txt"
        if not parsed_path.exists() or not raw_path.exists():
            logger.warning("missing artefact for %s", case_ref)
            continue
        try:
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            raw_text = raw_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("could not read artefacts for %s: %s", case_ref, e)
            continue
        out.append(
            {
                "case_ref": case_ref,
                "metadata": parsed,
                "raw_text": raw_text,
                "matter_types": list(entry.matter_types or []),
                "storage_path": str(case_dir),
            }
        )
    return out


def _build_source_documents(
    records: List[Dict], scraper_config: ScraperConfig
) -> List[SourceDocument]:
    docs: List[SourceDocument] = []
    for rec in records:
        meta = OmbudsmanCaseMetadata(**rec["metadata"])
        sd = ombudsman_to_source_document(
            meta,
            rec["raw_text"],
            kept_matter_types=rec["matter_types"],
            config=scraper_config,
        )
        # Storage path is useful for citation mapping / audit.
        if sd.storage_path is None:
            sd = sd.model_copy(update={"storage_path": rec["storage_path"]})
        docs.append(sd)
    return docs


async def _ingest_async(
    documents: List[SourceDocument],
    *,
    namespace,
    rag_config: RAGConfig,
    chunker: LegalChunker,
) -> Dict:
    """Embed + index documents. Returns stats dict."""
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

    # Embed in batches.
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
) -> tuple[Path, Path]:
    manifests_dir = rag_config.bm25_index_path.parent / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    corpus = CorpusManifest(
        domain_id=str(spec.id),
        domain_family=str(spec.family),
        forum=spec.forums[0],
        corpus_version=namespace.corpus_version or "unversioned",
        embed_model=rag_config.embedding_model,
        parser_version="ombudsman-0.1.0",
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
        parser_version="ombudsman-0.1.0",
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
@click.option("--max-docs", type=int, default=None, help="Cap on documents to ingest.")
@click.option(
    "--data-dir",
    type=click.Path(),
    default=None,
    help="Override base data dir (defaults to <repo_root>/data).",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def main(max_docs: Optional[int], data_dir: Optional[str], verbose: bool) -> None:
    """Ingest Housing Ombudsman determinations into the SHA-125 namespace."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    scraper_config = _scraper_config_for_data_dir(data_dir)

    records = _load_kept_records(scraper_config)
    if max_docs is not None:
        records = records[:max_docs]
    if not records:
        logger.warning(
            "no kept records found in master_index at %s; nothing to ingest",
            scraper_config.master_index_path,
        )
        return
    logger.info(
        "loaded %d kept records from %s",
        len(records),
        scraper_config.master_index_path,
    )

    documents = _build_source_documents(records, scraper_config)

    specs = load_domain_specs()
    spec = specs[DOMAIN_ID]
    namespace = _select_namespace(spec)

    base_rag = RAGConfig.from_env()
    rag_config = _rag_config_for_namespace(
        namespace,
        base_rag=base_rag,
        data_dir=data_dir,
    )
    rag_config.ensure_directories()

    chunker = LegalChunker(
        chunk_size=rag_config.chunk_size,
        chunk_overlap=rag_config.chunk_overlap,
    )

    logger.info(
        "ingesting %d documents into namespace=%s collection=%s persist=%s bm25=%s corpus_version=%s embed=%s",
        len(documents),
        namespace.namespace_id,
        rag_config.collection_name,
        rag_config.chroma_persist_dir,
        rag_config.bm25_index_path,
        namespace.corpus_version,
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
