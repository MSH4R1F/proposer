"""Tests for Housing Ombudsman ingest path configuration."""

from __future__ import annotations

from pathlib import Path

from domain_core.spec import (
    ChunkKind,
    Forum,
    RetrievalNamespace,
    SourceKind,
    SourcePublisher,
)
from rag_engine.config import RAGConfig

from scripts.ingest.run_ombudsman_ingest import (
    _rag_config_for_namespace,
    _scraper_config_for_data_dir,
)


def _namespace() -> RetrievalNamespace:
    return RetrievalNamespace(
        namespace_id="housing_repairs_social_v1",
        vector_collection="housing_repairs_social_v1",
        bm25_index_path="data/embeddings/housing_repairs_social_v1_bm25.pkl",
        corpus_root="data/raw/housing_ombudsman",
        chunk_kinds=[ChunkKind.DOCUMENT_CHUNK],
        source_publishers=[SourcePublisher.HOUSING_OMBUDSMAN],
        source_kinds=[SourceKind.OMBUDSMAN_DETERMINATION],
        forums=[Forum.HOUSING_OMBUDSMAN],
        corpus_version="research_seed_2026_05",
    )


def test_data_dir_override_controls_raw_and_index_paths(tmp_path: Path):
    data_dir = tmp_path / "pilot-data"
    scraper_config = _scraper_config_for_data_dir(str(data_dir))
    assert scraper_config.output_dir == data_dir / "raw" / "housing_ombudsman"
    assert scraper_config.master_index_path == (
        data_dir / "raw" / "housing_ombudsman" / "master_index.json"
    )

    rag_config = _rag_config_for_namespace(
        _namespace(),
        base_rag=RAGConfig(openai_api_key="x", data_dir=data_dir),
        data_dir=str(data_dir),
    )
    expected_index_dir = (
        data_dir
        / "indices"
        / "housing_repairs_social_v1"
        / "research_seed_2026_05"
    )
    assert rag_config.data_dir == data_dir
    assert rag_config.bm25_index_path == expected_index_dir / "bm25.pkl"
    assert rag_config.chroma_persist_dir == expected_index_dir / "chroma"
