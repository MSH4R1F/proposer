"""SHA-125/126 Phase 0 regression tests.

Two invariants are pinned here:

1. ``RAGPipeline(config=RAGConfig.from_namespace(ns))`` must open the
   namespace's collection — *not* the legacy ``"tribunal_cases"`` default.
   Before Phase 0 the ChromaStore default-arg shadowed the config and
   silently routed every namespace to the deposit collection.

2. The :func:`rag_engine.ingestion.chunk_source_document` adapter must
   propagate every Phase-4 :class:`SourceMetadata` field onto each chunk
   and produce deterministic chunk ids over
   ``(namespace_id, corpus_version, source_id, chunk_index, content)``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domain_core.spec import (
    ChunkKind,
    Forum,
    SourceKind,
    SourcePublisher,
)

from rag_engine.chunking.legal_chunker import LegalChunker
from rag_engine.config import DocumentChunk, RAGConfig, SectionType
from rag_engine.ingestion import (
    SourceDocument,
    chunk_source_document,
    deterministic_chunk_id,
    source_document_to_case_document,
)
from rag_engine.namespaces import EMBED_MODEL_NAME_TE3S
from rag_engine.pipeline import RAGPipeline
from rag_engine.source_metadata import SourceMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _rro_namespace():
    """Build the RRO retrieval namespace as the YAML defines it.

    We construct it directly rather than loading the YAML so this test
    keeps running even if the YAML loader path changes.
    """
    from domain_core.spec import RetrievalNamespace

    return RetrievalNamespace(
        namespace_id="housing_property_chamber_rro_v1_te3s",
        vector_collection="housing_property_chamber_rro_v1_te3s__2026Q2_te3s",
        bm25_index_path=(
            "data/indices/housing_property_chamber_rro_v1_te3s/"
            "2026Q2_te3s/bm25.pkl"
        ),
        corpus_root="data/raw",
        chunk_kinds=[ChunkKind.DOCUMENT_CHUNK],
        source_publishers=[SourcePublisher.BAILII, SourcePublisher.GOVUK],
        source_kinds=[SourceKind.CASE_DECISION],
        forums=[Forum.FIRST_TIER_PROPERTY_CHAMBER],
        allowed_cross_namespace_ids=[],
        metadata_filters={"matter_type": "rent_repayment_order"},
        corpus_version="2026Q2_te3s",
    )


def _govuk_rro_metadata(*, source_id: str = "GOVUK-RRO-0001") -> SourceMetadata:
    return SourceMetadata(
        domain_id="housing.property_chamber.rro.v1",
        domain_family="housing",
        forum=Forum.FIRST_TIER_PROPERTY_CHAMBER,
        source_id=source_id,
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["rent_repayment_order"],
        decision_date=date(2024, 6, 15),
        source_url="https://www.gov.uk/residential-property-tribunal-decisions/example",
        source_license="OGL-3.0",
        corpus_version="2026Q2_te3s",
        parser_version="govuk-rro-0.1.0",
        case_reference="LON/00BB/HMF/2024/0001",
    )


# ---------------------------------------------------------------------------
# Test 1: ChromaStore must honour config.collection_name (regression)
# ---------------------------------------------------------------------------


class TestRAGPipelineRoutesToNamespaceCollection:
    """Before Phase 0, RAGPipeline silently opened ``tribunal_cases`` for
    every namespace because the ChromaStore ``collection_name`` default
    was a non-empty string and the ``or config.collection_name`` fallback
    never triggered. This test pins that fix.
    """

    def test_rag_pipeline_opens_namespace_collection_not_default(
        self, tmp_path: Path
    ):
        ns = _rro_namespace()
        base = RAGConfig(
            openai_api_key="x",
            data_dir=tmp_path,
            embedding_model=EMBED_MODEL_NAME_TE3S,
        )
        cfg = RAGConfig.from_namespace(ns, base=base, project_root=tmp_path)
        # Sanity: namespace-derived collection must differ from legacy default.
        assert cfg.collection_name != "tribunal_cases"
        assert cfg.collection_name == ns.vector_collection

        captured: dict = {}

        # Spy on ChromaStore so we observe the resolved collection_name
        # without booting a real Chroma client.
        with patch("rag_engine.pipeline.ChromaStore") as mock_store:
            def _capture(config=None, persist_directory=None, collection_name=None):
                # Mirror the ChromaStore resolution rule:
                #   resolved = explicit collection_name OR config.collection_name
                resolved = collection_name or (
                    config.collection_name if config else None
                )
                captured["resolved_collection_name"] = resolved
                captured["passed_config"] = config
                return MagicMock()

            mock_store.side_effect = _capture
            with patch("rag_engine.pipeline.OpenAIEmbeddings") as mock_emb:
                mock_emb.return_value = MagicMock()
                RAGPipeline(config=cfg)

        assert captured["passed_config"] is cfg
        assert captured["resolved_collection_name"] == ns.vector_collection
        assert captured["resolved_collection_name"] != "tribunal_cases"


# ---------------------------------------------------------------------------
# Test 2: SourceMetadata flows through the ingestion adapter
# ---------------------------------------------------------------------------


class TestSourceDocumentAdapterCarriesMetadata:
    def test_source_document_to_case_document_keeps_metadata(self):
        sd = SourceDocument(
            metadata=_govuk_rro_metadata(),
            raw_text=(
                "FIRST-TIER TRIBUNAL PROPERTY CHAMBER\n"
                "Decision: rent repayment order under HPA 2016 s.41.\n"
                "The tribunal finds that the landlord operated an HMO without "
                "the required licence under section 72(1) of the Housing Act 2004."
            ),
            title="Example RRO",
            storage_path="data/raw/govuk/example.json",
        )
        case_doc = source_document_to_case_document(sd)
        assert case_doc.source_metadata is sd.metadata
        assert case_doc.case_reference == "LON/00BB/HMF/2024/0001"
        assert case_doc.year == 2024  # pulled from decision_date
        assert case_doc.full_text == sd.raw_text

    def test_chunk_source_document_propagates_phase4_fields(self):
        sd = SourceDocument(
            metadata=_govuk_rro_metadata(),
            raw_text=(
                "FIRST-TIER TRIBUNAL\n"
                "PROPERTY CHAMBER (RESIDENTIAL PROPERTY)\n\n"
                "BACKGROUND\n\n"
                "1. The applicant tenants apply for a rent repayment order under "
                "section 41 of the Housing and Planning Act 2016.\n\n"
                "2. The respondent landlord operated the property as an "
                "unlicensed HMO under Part 2 of the Housing Act 2004.\n\n"
                "FINDINGS\n\n"
                "3. The tribunal is satisfied beyond reasonable doubt that the "
                "respondent committed an offence under section 72(1) of the "
                "Housing Act 2004.\n\n"
                "DECISION\n\n"
                "4. Rent repayment of £6,000 is awarded."
            ),
        )
        chunker = LegalChunker(chunk_size=120, chunk_overlap=20)

        chunks = chunk_source_document(
            sd,
            namespace_id="housing_property_chamber_rro_v1_te3s",
            chunker=chunker,
        )
        assert chunks, "adapter should produce at least one chunk"

        # Every Phase-4 field should be present on every chunk.
        for chunk in chunks:
            md = chunk.source_metadata
            assert md is not None
            assert md.domain_id == "housing.property_chamber.rro.v1"
            assert md.domain_family == "housing"
            assert md.forum == Forum.FIRST_TIER_PROPERTY_CHAMBER
            assert md.source_id == "GOVUK-RRO-0001"
            assert md.source_publisher == SourcePublisher.GOVUK
            assert md.source_kind == SourceKind.CASE_DECISION
            assert md.matter_types == ["rent_repayment_order"]
            assert md.corpus_version == "2026Q2_te3s"
            assert md.parser_version == "govuk-rro-0.1.0"
            # Chunk-level fields must be set by the adapter.
            assert md.chunk_kind == ChunkKind.DOCUMENT_CHUNK
            assert md.content_sha256 is not None
            assert md.char_start is not None and md.char_end is not None
            assert md.char_end >= md.char_start

            # Chroma metadata projection must contain the same fields.
            row = md.to_chroma_metadata()
            assert row["domain_id"] == "housing.property_chamber.rro.v1"
            assert row["forum"] == "first_tier_property_chamber"
            assert row["source_publisher"] == "govuk"
            assert row["matter_types"] == "rent_repayment_order"
            assert row["corpus_version"] == "2026Q2_te3s"
            assert row["parser_version"] == "govuk-rro-0.1.0"

    def test_chunk_ids_are_deterministic_and_idempotent(self):
        sd = SourceDocument(
            metadata=_govuk_rro_metadata(source_id="GOVUK-RRO-DETERMINISM"),
            raw_text=(
                "Section 72(1) Housing Act 2004 offence is established.\n\n"
                "Rent repayment order is granted in the sum of £4,000."
            ),
        )
        chunker = LegalChunker(chunk_size=80, chunk_overlap=10)

        first = chunk_source_document(
            sd,
            namespace_id="housing_property_chamber_rro_v1_te3s",
            chunker=chunker,
        )
        second = chunk_source_document(
            sd,
            namespace_id="housing_property_chamber_rro_v1_te3s",
            chunker=chunker,
        )
        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
        # Differ by namespace -> ids must differ.
        third = chunk_source_document(
            sd,
            namespace_id="other_namespace",
            chunker=chunker,
        )
        assert [c.chunk_id for c in first] != [c.chunk_id for c in third]

    def test_fallback_spans_advance_after_exact_match_miss(self):
        """A rewritten chunk must not make later fallback spans overlap."""

        sd = SourceDocument(
            metadata=_govuk_rro_metadata(source_id="GOVUK-RRO-SPANS"),
            raw_text="alpha beta gamma delta epsilon",
        )

        class RewritingChunker:
            def chunk_document(self, case_doc):
                return [
                    DocumentChunk(
                        chunk_id="legacy-0",
                        case_reference=case_doc.case_reference,
                        chunk_index=0,
                        text="alpha beta",
                        section_type=SectionType.UNKNOWN,
                        year=case_doc.year,
                    ),
                    # This exact text is not present in raw_text.
                    DocumentChunk(
                        chunk_id="legacy-1",
                        case_reference=case_doc.case_reference,
                        chunk_index=1,
                        text="rewritten middle",
                        section_type=SectionType.UNKNOWN,
                        year=case_doc.year,
                    ),
                    DocumentChunk(
                        chunk_id="legacy-2",
                        case_reference=case_doc.case_reference,
                        chunk_index=2,
                        text="also rewritten",
                        section_type=SectionType.UNKNOWN,
                        year=case_doc.year,
                    ),
                ]

        chunks = chunk_source_document(
            sd,
            namespace_id="housing_property_chamber_rro_v1_te3s",
            chunker=RewritingChunker(),
        )

        spans = [
            (c.source_metadata.char_start, c.source_metadata.char_end)
            for c in chunks
        ]
        assert spans[0] == (0, len("alpha beta"))
        assert spans[1][0] == spans[0][1]
        assert spans[2][0] == spans[1][1]

    def test_deterministic_chunk_id_format(self):
        chunk_id = deterministic_chunk_id(
            namespace_id="housing_property_chamber_rro_v1_te3s",
            corpus_version="2026Q2_te3s",
            source_id="GOVUK-RRO-0007",
            chunk_index=3,
            chunk_text="example chunk text",
        )
        assert chunk_id.startswith(
            "housing_property_chamber_rro_v1_te3s::2026Q2_te3s::GOVUK-RRO-0007::0003::"
        )
        # Trailing 8-char hex digest.
        digest = chunk_id.rsplit("::", 1)[-1]
        assert len(digest) == 8
        int(digest, 16)  # parses as hex

    def test_deterministic_chunk_id_rejects_blank_inputs(self):
        with pytest.raises(ValueError):
            deterministic_chunk_id(
                namespace_id="",
                corpus_version="v1",
                source_id="x",
                chunk_index=0,
                chunk_text="t",
            )
        with pytest.raises(ValueError):
            deterministic_chunk_id(
                namespace_id="ns",
                corpus_version="v1",
                source_id="x",
                chunk_index=-1,
                chunk_text="t",
            )
