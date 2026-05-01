"""SHA-20 Phase 4: tests for ingestion contract Pydantic models."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from domain_core.spec import ChunkKind, Forum, SourceKind, SourcePublisher

from rag_engine.ingestion import (
    CorpusManifest,
    IngestionRunManifest,
    SourceChunk,
    SourceDocument,
)
from rag_engine.source_metadata import SourceMetadata


def _meta(**overrides) -> SourceMetadata:
    base = dict(
        domain_id="housing.rro.v1",
        domain_family="housing",
        forum=Forum.FIRST_TIER_PROPERTY_CHAMBER,
        source_id="LON_X",
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["rent_repayment_order"],
        decision_date=date(2024, 6, 15),
        corpus_version="2026Q2_te3s",
        parser_version="rpt_html_v3",
    )
    base.update(overrides)
    return SourceMetadata(**base)


class TestSourceDocument:
    def test_requires_metadata_and_text(self):
        with pytest.raises(ValidationError):
            SourceDocument(metadata=_meta())  # missing raw_text

    def test_rejects_empty_text(self):
        with pytest.raises(ValidationError):
            SourceDocument(metadata=_meta(), raw_text="   ")

    def test_constructs_with_required_fields(self):
        doc = SourceDocument(metadata=_meta(), raw_text="hello world")
        assert doc.metadata.source_id == "LON_X"


class TestSourceChunk:
    def test_chunk_kind_must_be_chunkkind_enum(self):
        meta = _meta()
        chunk = SourceChunk(chunk_id="x", metadata=meta, text="t")
        assert chunk.metadata.chunk_kind == ChunkKind.DOCUMENT_CHUNK

    def test_proposition_chunk_round_trip(self):
        meta = _meta(chunk_kind=ChunkKind.PROPOSITION)
        chunk = SourceChunk(chunk_id="x", metadata=meta, text="prop text")
        assert chunk.metadata.chunk_kind == ChunkKind.PROPOSITION


class TestCorpusManifest:
    def _kwargs(self, **overrides):
        base = dict(
            domain_id="housing.rro.v1",
            domain_family="housing",
            forum=Forum.FIRST_TIER_PROPERTY_CHAMBER,
            corpus_version="2026Q2_te3s",
            embed_model="text-embedding-3-small",
            parser_version="rpt_html_v3",
            ingestion_started_at=datetime(2026, 5, 1, 9, 0),
            ingestion_finished_at=datetime(2026, 5, 1, 10, 0),
            total_documents=10,
            total_chunks=200,
            chunk_kind_counts={"document_chunk": 200},
        )
        base.update(overrides)
        return base

    def test_finished_must_not_precede_started(self):
        with pytest.raises(ValidationError):
            CorpusManifest(
                **self._kwargs(
                    ingestion_started_at=datetime(2026, 5, 1, 12, 0),
                    ingestion_finished_at=datetime(2026, 5, 1, 11, 0),
                )
            )

    def test_chunk_kind_counts_must_use_known_kinds(self):
        with pytest.raises(ValidationError):
            CorpusManifest(
                **self._kwargs(chunk_kind_counts={"unknown_kind": 1})
            )

    def test_known_chunk_kinds_accepted(self):
        manifest = CorpusManifest(
            **self._kwargs(
                chunk_kind_counts={"document_chunk": 100, "proposition": 50}
            )
        )
        assert manifest.chunk_kind_counts == {
            "document_chunk": 100,
            "proposition": 50,
        }


class TestIngestionRunManifest:
    def test_finished_must_not_precede_started(self):
        with pytest.raises(ValidationError):
            IngestionRunManifest(
                run_id="r1",
                domain_id="housing.rro.v1",
                corpus_version="2026Q2_te3s",
                started_at=datetime(2026, 5, 1, 12, 0),
                finished_at=datetime(2026, 5, 1, 11, 0),
                parser_version="v3",
                embed_model="text-embedding-3-small",
            )

    def test_open_run_finished_can_be_none(self):
        m = IngestionRunManifest(
            run_id="r1",
            domain_id="housing.rro.v1",
            corpus_version="2026Q2_te3s",
            started_at=datetime(2026, 5, 1, 12, 0),
            parser_version="v3",
            embed_model="text-embedding-3-small",
        )
        assert m.finished_at is None
