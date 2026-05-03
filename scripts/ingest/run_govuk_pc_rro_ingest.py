"""SHA-126: GOV.UK Property Tribunal RRO ingestion script.

Reads the master index produced by the GOV.UK scraper, converts every
ACCEPTED record to a SourceDocument via
:func:`govuk_to_source_document`, chunks via
:func:`rag_engine.ingestion.adapters.chunk_source_document`, embeds with
:class:`OpenAIEmbeddings`, and writes to the
``housing_property_chamber_rro_v1`` namespace's Chroma collection plus
its BM25 sidecar index.

Skips records whose master-index entry has ``bailii_duplicate_of != None``
unless ``--include-duplicates`` is passed.

Usage:
    python scripts/ingest/run_govuk_pc_rro_ingest.py --max-docs 30
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional

import click


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = REPO_ROOT / "packages"
for p in (REPO_ROOT, PACKAGES):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


from domain_core.registry import load_domain_specs  # noqa: E402
from rag_engine.chunking.legal_chunker import LegalChunker  # noqa: E402
from rag_engine.config import RAGConfig  # noqa: E402
from rag_engine.embeddings import OpenAIEmbeddings  # noqa: E402
from rag_engine.ingestion.adapters import chunk_source_document  # noqa: E402
from rag_engine.ingestion.contracts import (  # noqa: E402
    CorpusManifest,
    IngestionRunManifest,
)
from rag_engine.retrieval.bm25_index import BM25Index  # noqa: E402
from rag_engine.vectorstore.chroma_store import ChromaStore  # noqa: E402

from scripts.scrapers.govuk_property_tribunal.config import (  # noqa: E402
    CORPUS_VERSION,
    DOMAIN_ID,
    NAMESPACE_ID,
    PARSER_VERSION,
    ScraperConfig,
)
from scripts.scrapers.govuk_property_tribunal.models import (  # noqa: E402
    ArtefactKind,
    GovUKAsset,
    GovUKPCMetadata,
    ScrapeRecord,
)
from scripts.scrapers.govuk_property_tribunal.parsers import extract_pdf_text  # noqa: E402
from scripts.scrapers.govuk_property_tribunal.to_source_document import (  # noqa: E402
    govuk_to_source_document,
)


logger = logging.getLogger(__name__)


def _load_records(master_index_path: Path) -> List[ScrapeRecord]:
    if not master_index_path.is_file():
        return []
    data = json.loads(master_index_path.read_text(encoding="utf-8"))
    rows = data.get("records") or data.get("cases") or []
    out: List[ScrapeRecord] = []
    for row in rows:
        try:
            out.append(ScrapeRecord.model_validate(row))
        except Exception as exc:
            logger.warning("master_index_row_invalid", extra={"err": str(exc)})
    return out


def _record_to_metadata(rec: ScrapeRecord, scraper_cfg: ScraperConfig) -> Optional[GovUKPCMetadata]:
    """Reconstruct a GovUKPCMetadata from the master-index row + on-disk artefacts."""
    decision_dir = scraper_cfg.decisions_dir / _slug(rec.case_reference)
    raw_text = ""
    storage_path = rec.storage_path
    raw_txt_path = decision_dir / "raw.txt"
    if raw_txt_path.is_file():
        raw_text = raw_txt_path.read_text(encoding="utf-8")
    elif storage_path and Path(storage_path).is_file() and Path(storage_path).suffix == ".pdf":
        try:
            raw_text, _ = extract_pdf_text(Path(storage_path))
        except Exception as exc:
            logger.warning("pdf_extract_failed_during_ingest", extra={"path": storage_path, "err": str(exc)})
    parsed_path = decision_dir / "parsed.json"
    parsed: dict = {}
    if parsed_path.is_file():
        try:
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
    if not raw_text and not parsed:
        return None

    primary_kind: Optional[ArtefactKind]
    if rec.primary_artefact_kind is not None:
        primary_kind = rec.primary_artefact_kind
    elif parsed.get("primary_artefact_kind"):
        try:
            primary_kind = ArtefactKind(parsed["primary_artefact_kind"])
        except ValueError:
            primary_kind = None
    else:
        primary_kind = None

    return GovUKPCMetadata(
        case_reference=rec.case_reference,
        title=parsed.get("title") or rec.title,
        govuk_page_url=rec.govuk_page_url,
        base_path=rec.base_path,
        decision_date=rec.decision_date,
        tribunal_region=parsed.get("tribunal_region"),
        landlord=parsed.get("landlord"),
        tenant=parsed.get("tenant"),
        address=parsed.get("address"),
        relevant_period_months=parsed.get("relevant_period_months"),
        award_amount=parsed.get("award_amount"),
        award_pct_rent_paid=parsed.get("award_pct_rent_paid"),
        licensing_offence_section=parsed.get("licensing_offence_section"),
        statutory_grounds=list(rec.statutory_grounds or []),
        primary_asset_url=parsed.get("primary_asset_url"),
        primary_artefact_kind=primary_kind,
        raw_text=raw_text or parsed.get("raw_text"),
        content_sha256=rec.content_sha256 or parsed.get("content_sha256"),
        storage_path=storage_path,
    )


def _slug(case_reference: str) -> str:
    safe = []
    for ch in case_reference:
        if ch.isalnum():
            safe.append(ch)
        elif ch in ("/", "\\", " "):
            safe.append("_")
        elif ch in (".", "-", "_"):
            safe.append(ch)
    s = "".join(safe).strip("_")
    return s or "decision"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--max-docs", type=int, default=30)
@click.option("--include-duplicates", is_flag=True, default=False)
@click.option(
    "--master-index",
    type=click.Path(exists=False),
    default=str(REPO_ROOT / "data" / "raw" / "govuk_property_tribunal" / "master_index.json"),
)
@click.option("--dry-run", is_flag=True, default=False)
def main(max_docs: int, include_duplicates: bool, master_index: str, dry_run: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    specs = load_domain_specs()
    spec = specs.get(DOMAIN_ID)
    if spec is None:
        click.echo(f"Domain spec {DOMAIN_ID} not found", err=True)
        sys.exit(2)

    namespace = next(
        (n for n in spec.retrieval_namespaces if n.namespace_id == NAMESPACE_ID),
        None,
    )
    if namespace is None:
        click.echo(f"Namespace {NAMESPACE_ID} not found in domain spec", err=True)
        sys.exit(2)

    base_cfg = RAGConfig.from_env()
    rag_cfg = RAGConfig.from_namespace(namespace, base=base_cfg, project_root=REPO_ROOT)
    rag_cfg.ensure_directories()

    scraper_cfg = ScraperConfig(output_base_dir=Path(master_index).parent)
    records = _load_records(Path(master_index))
    if not records:
        click.echo("No records in master index — run the scraper first.")
        sys.exit(0)

    chunker = LegalChunker(chunk_size=rag_cfg.chunk_size, chunk_overlap=rag_cfg.chunk_overlap)

    started = datetime.utcnow()
    run_id = str(uuid.uuid4())
    run_log = IngestionRunManifest(
        run_id=run_id,
        domain_id=DOMAIN_ID,
        corpus_version=CORPUS_VERSION,
        started_at=started,
        parser_version=PARSER_VERSION,
        embed_model=rag_cfg.embedding_model,
    )

    selected: List[ScrapeRecord] = []
    for rec in records:
        if rec.bailii_duplicate_of and not include_duplicates:
            run_log.documents_skipped += 1
            continue
        selected.append(rec)
        if len(selected) >= max_docs:
            break

    run_log.documents_attempted = len(selected)

    if dry_run:
        click.echo(json.dumps({
            "selected": [r.case_reference for r in selected],
            "would_skip_duplicates": sum(1 for r in records if r.bailii_duplicate_of and not include_duplicates),
        }, indent=2))
        return

    embedder = OpenAIEmbeddings(config=rag_cfg)
    store = ChromaStore(config=rag_cfg)
    bm25 = BM25Index(lite_mode=rag_cfg.bm25_lite_mode)
    if rag_cfg.bm25_index_path.is_file():
        bm25.load(rag_cfg.bm25_index_path)

    all_chunks = []
    chunk_kind_counts = {}

    async def _ingest_one(rec: ScrapeRecord) -> int:
        meta = _record_to_metadata(rec, scraper_cfg)
        if meta is None or not (meta.raw_text or "").strip():
            run_log.documents_failed += 1
            return 0
        sd = govuk_to_source_document(
            meta,
            kept_grounds=list(rec.statutory_grounds or []),
            bailii_duplicate_of=rec.bailii_duplicate_of,
        )
        chunks = chunk_source_document(sd, namespace_id=NAMESPACE_ID, chunker=chunker)
        if not chunks:
            run_log.documents_failed += 1
            return 0
        embs = await embedder.embed_texts([c.text for c in chunks])
        await store.add_chunks(chunks, embs)
        for c in chunks:
            ck = c.source_metadata.chunk_kind.value if c.source_metadata else "document_chunk"
            chunk_kind_counts[ck] = chunk_kind_counts.get(ck, 0) + 1
        all_chunks.extend(chunks)
        run_log.documents_ingested += 1
        run_log.chunks_emitted += len(chunks)
        return len(chunks)

    async def _ingest_all():
        for rec in selected:
            try:
                await _ingest_one(rec)
            except Exception as exc:
                run_log.documents_failed += 1
                run_log.notes.append(f"{rec.case_reference}: {exc!s}")

    asyncio.run(_ingest_all())

    if all_chunks:
        bm25.build_index(all_chunks)
        bm25.save(rag_cfg.bm25_index_path)

    run_log.finished_at = datetime.utcnow()

    corpus_manifest = CorpusManifest(
        domain_id=DOMAIN_ID,
        domain_family="housing",
        forum=spec.forums[0] if spec.forums else None,
        corpus_version=CORPUS_VERSION,
        embed_model=rag_cfg.embedding_model,
        parser_version=PARSER_VERSION,
        ingestion_started_at=started,
        ingestion_finished_at=run_log.finished_at,
        total_documents=run_log.documents_ingested,
        total_chunks=run_log.chunks_emitted,
        chunk_kind_counts=chunk_kind_counts,
    )

    out_dir = REPO_ROOT / "data" / "indices" / NAMESPACE_ID / CORPUS_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"ingestion_run_{run_id}.json").write_text(
        json.dumps(run_log.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    (out_dir / "corpus_manifest.json").write_text(
        json.dumps(corpus_manifest.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    click.echo(json.dumps({
        "run_id": run_id,
        "documents_ingested": run_log.documents_ingested,
        "chunks_emitted": run_log.chunks_emitted,
        "documents_skipped": run_log.documents_skipped,
        "documents_failed": run_log.documents_failed,
        "out_dir": str(out_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
