"""SHA-20 Phase 4: tests for namespace resolution + cross-domain guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain_core.spec import (
    ChunkKind,
    Forum,
    RetrievalNamespace,
    SourceKind,
    SourcePublisher,
)

from rag_engine.config import RAGConfig
from rag_engine.namespaces import (
    CrossDomainRetrievalNotAllowed,
    EMBED_MODEL_NAME_TE3S,
    EMBED_MODEL_TAG_TE3S,
    EmbeddingModelMismatch,
    LEGACY_DEPOSIT_BM25_PATH,
    LEGACY_DEPOSIT_COLLECTION,
    LEGACY_DEPOSIT_CORPUS_VERSION,
    assert_cross_domain_allowed,
    bm25_index_path_for,
    is_legacy_deposit_namespace,
    resolve_embedding_model,
    vector_collection_for,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _legacy_deposit_namespace() -> RetrievalNamespace:
    return RetrievalNamespace(
        namespace_id="housing_deposit_v1_legacy",
        vector_collection=LEGACY_DEPOSIT_COLLECTION,
        bm25_index_path=LEGACY_DEPOSIT_BM25_PATH,
        corpus_root="data/raw/bailii",
        chunk_kinds=[ChunkKind.DOCUMENT_CHUNK],
        source_publishers=[SourcePublisher.BAILII],
        source_kinds=[SourceKind.CASE_DECISION],
        forums=[Forum.DEPOSIT_SCHEME_ADJUDICATION, Forum.COUNTY_COURT],
        allowed_cross_namespace_ids=[],
        metadata_filters={},
        corpus_version=LEGACY_DEPOSIT_CORPUS_VERSION,
    )


def _modern_namespace(
    namespace_id: str = "housing_rro_v1_te3s",
    corpus_version: str = "2026Q2_te3s",
    allowed_cross: list | None = None,
) -> RetrievalNamespace:
    return RetrievalNamespace(
        namespace_id=namespace_id,
        vector_collection=f"{namespace_id}__{corpus_version}",
        bm25_index_path=f"data/indices/{namespace_id}/{corpus_version}/bm25.pkl",
        corpus_root="data/raw/govuk_rpt",
        chunk_kinds=[ChunkKind.DOCUMENT_CHUNK, ChunkKind.PROPOSITION],
        source_publishers=[SourcePublisher.GOVUK],
        source_kinds=[SourceKind.CASE_DECISION],
        forums=[Forum.FIRST_TIER_PROPERTY_CHAMBER],
        allowed_cross_namespace_ids=list(allowed_cross or []),
        metadata_filters={},
        corpus_version=corpus_version,
    )


# ---------------------------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------------------------


class TestLegacyCompatibility:
    def test_default_deposit_namespace_uses_legacy_chroma_collection(self):
        ns = _legacy_deposit_namespace()
        assert is_legacy_deposit_namespace(ns)
        assert vector_collection_for(ns) == "tribunal_cases"

    def test_default_deposit_namespace_resolves_legacy_bm25_path(self, tmp_path):
        ns = _legacy_deposit_namespace()
        assert (
            bm25_index_path_for(ns, tmp_path)
            == tmp_path / "data" / "embeddings" / "bm25_index.pkl"
        )

    def test_modern_namespace_resolves_per_namespace_bm25_path(self, tmp_path):
        ns = _modern_namespace()
        assert (
            bm25_index_path_for(ns, tmp_path)
            == tmp_path
            / "data"
            / "indices"
            / "housing_rro_v1_te3s"
            / "2026Q2_te3s"
            / "bm25.pkl"
        )


# ---------------------------------------------------------------------------
# Embedding-model fail-fast
# ---------------------------------------------------------------------------


class TestEmbeddingModel:
    def test_te3s_tag_resolves_to_text_embedding_3_small(self):
        ns = _modern_namespace()
        assert resolve_embedding_model(ns) == EMBED_MODEL_NAME_TE3S
        assert EMBED_MODEL_TAG_TE3S in ns.namespace_id

    def test_legacy_deposit_namespace_returns_no_tag(self):
        ns = _legacy_deposit_namespace()
        assert resolve_embedding_model(ns) is None

    def test_from_namespace_raises_on_embedding_mismatch(self, tmp_path):
        ns = _modern_namespace()
        # Live config declares a different embedding model.
        base = RAGConfig(
            openai_api_key="x",
            data_dir=tmp_path,
            embedding_model="text-embedding-3-large",  # wrong
        )
        with pytest.raises(EmbeddingModelMismatch):
            RAGConfig.from_namespace(ns, base=base, project_root=tmp_path)

    def test_from_namespace_passes_when_model_matches(self, tmp_path):
        ns = _modern_namespace()
        base = RAGConfig(
            openai_api_key="x",
            data_dir=tmp_path,
            embedding_model=EMBED_MODEL_NAME_TE3S,
        )
        cfg = RAGConfig.from_namespace(ns, base=base, project_root=tmp_path)
        assert cfg.collection_name == ns.vector_collection
        assert (
            cfg.bm25_index_path
            == tmp_path
            / "data"
            / "indices"
            / "housing_rro_v1_te3s"
            / "2026Q2_te3s"
            / "bm25.pkl"
        )

    def test_from_namespace_legacy_deposit_keeps_legacy_paths(self, tmp_path):
        ns = _legacy_deposit_namespace()
        base = RAGConfig(openai_api_key="x", data_dir=tmp_path)
        cfg = RAGConfig.from_namespace(ns, base=base, project_root=tmp_path)
        assert cfg.collection_name == "tribunal_cases"
        assert (
            cfg.bm25_index_path
            == tmp_path / "data" / "embeddings" / "bm25_index.pkl"
        )

    def test_two_namespaces_can_be_opened_in_one_process(self, tmp_path):
        legacy = _legacy_deposit_namespace()
        modern = _modern_namespace()
        base = RAGConfig(
            openai_api_key="x",
            data_dir=tmp_path,
            embedding_model=EMBED_MODEL_NAME_TE3S,
        )
        c1 = RAGConfig.from_namespace(legacy, base=base, project_root=tmp_path)
        c2 = RAGConfig.from_namespace(modern, base=base, project_root=tmp_path)
        assert c1.collection_name != c2.collection_name
        assert c1.bm25_index_path != c2.bm25_index_path


# ---------------------------------------------------------------------------
# Cross-domain guard
# ---------------------------------------------------------------------------


class TestCrossDomainGuard:
    def test_same_namespace_is_always_allowed(self):
        ns = _modern_namespace()
        # No flags set; same namespace is fine.
        assert (
            assert_cross_domain_allowed(
                target_namespace=ns,
                requesting_namespace=ns,
                cross_domain_allowed=False,
                eval_only=False,
            )
            is None
        )

    def test_no_requesting_namespace_skips_guard(self):
        ns = _modern_namespace()
        assert (
            assert_cross_domain_allowed(
                target_namespace=ns,
                requesting_namespace=None,
                cross_domain_allowed=False,
                eval_only=False,
            )
            is None
        )

    def test_cross_domain_blocked_without_eval_only(self):
        target = _modern_namespace("housing_rro_v1_te3s", allowed_cross=["other"])
        other = _modern_namespace("other", "2026Q2_te3s")
        with pytest.raises(CrossDomainRetrievalNotAllowed) as exc:
            assert_cross_domain_allowed(
                target_namespace=target,
                requesting_namespace=other,
                cross_domain_allowed=True,
                eval_only=False,
            )
        assert "eval_only=True" in str(exc.value)

    def test_cross_domain_blocked_without_cross_domain_allowed(self):
        target = _modern_namespace("housing_rro_v1_te3s")
        other = _modern_namespace("other", "2026Q2_te3s")
        with pytest.raises(CrossDomainRetrievalNotAllowed):
            assert_cross_domain_allowed(
                target_namespace=target,
                requesting_namespace=other,
                cross_domain_allowed=False,
                eval_only=True,
            )

    def test_cross_domain_blocked_when_target_does_not_list_requester(self):
        # cross_domain_allowed=True and eval_only=True, but target's
        # allowed_cross_namespace_ids is empty.
        target = _modern_namespace("housing_rro_v1_te3s", allowed_cross=[])
        other = _modern_namespace("other", "2026Q2_te3s")
        with pytest.raises(CrossDomainRetrievalNotAllowed):
            assert_cross_domain_allowed(
                target_namespace=target,
                requesting_namespace=other,
                cross_domain_allowed=True,
                eval_only=True,
            )

    def test_cross_domain_allowed_with_both_flags_and_listed_requester(self):
        target = _modern_namespace("housing_rro_v1_te3s", allowed_cross=["other"])
        other = _modern_namespace("other", "2026Q2_te3s")
        # Should not raise.
        assert_cross_domain_allowed(
            target_namespace=target,
            requesting_namespace=other,
            cross_domain_allowed=True,
            eval_only=True,
        )
