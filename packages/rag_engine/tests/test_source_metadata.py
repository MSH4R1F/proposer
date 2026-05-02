"""SHA-20 Phase 4: tests for SourceMetadata + CaseDocument/DocumentChunk back-compat."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from domain_core.spec import ChunkKind, Forum, SourceKind, SourcePublisher

from rag_engine.config import CaseDocument, DocumentChunk, SectionType
from rag_engine.source_metadata import SourceMetadata


def _meta(**overrides) -> SourceMetadata:
    base = dict(
        domain_id="housing.rro.v1",
        domain_family="housing",
        forum=Forum.FIRST_TIER_PROPERTY_CHAMBER,
        source_id="LON_00AB_HMA_2024_0123",
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=["rent_repayment_order"],
        decision_date=date(2024, 6, 15),
        corpus_version="2026Q2_te3s",
        parser_version="rpt_html_v3",
    )
    base.update(overrides)
    return SourceMetadata(**base)


class TestSourceMetadata:
    def test_required_fields_must_be_present(self):
        with pytest.raises(ValidationError):
            SourceMetadata(domain_id="housing.rro.v1")  # missing the rest

    def test_chroma_metadata_includes_phase4_keys(self):
        meta = _meta()
        d = meta.to_chroma_metadata()
        # Phase-4 keys present
        assert d["domain_id"] == "housing.rro.v1"
        assert d["domain_family"] == "housing"
        assert d["forum"] == Forum.FIRST_TIER_PROPERTY_CHAMBER.value
        assert d["source_id"] == "LON_00AB_HMA_2024_0123"
        assert d["source_publisher"] == SourcePublisher.GOVUK.value
        assert d["source_kind"] == SourceKind.CASE_DECISION.value
        assert d["corpus_version"] == "2026Q2_te3s"
        assert d["parser_version"] == "rpt_html_v3"
        assert d["chunk_kind"] == ChunkKind.DOCUMENT_CHUNK.value
        assert d["matter_types"] == "rent_repayment_order"
        assert d["decision_date"] == "2024-06-15"

    def test_round_trip_through_chroma_metadata(self):
        meta = _meta(
            paragraph=12,
            char_start=100,
            char_end=350,
            content_sha256="abc",
            source_url="https://www.gov.uk/x",
        )
        d = meta.to_chroma_metadata()
        roundtrip = SourceMetadata.from_chroma_metadata(d)
        assert roundtrip.matter_types == ["rent_repayment_order"]
        assert roundtrip.paragraph == 12
        assert roundtrip.char_start == 100
        assert roundtrip.char_end == 350
        assert roundtrip.decision_date == date(2024, 6, 15)
        assert roundtrip.source_url == "https://www.gov.uk/x"

    def test_char_end_must_not_precede_char_start(self):
        with pytest.raises(ValidationError):
            _meta(char_start=200, char_end=100)

    def test_chunk_kind_proposition_is_supported(self):
        meta = _meta(chunk_kind=ChunkKind.PROPOSITION)
        assert meta.chunk_kind == ChunkKind.PROPOSITION
        assert meta.to_chroma_metadata()["chunk_kind"] == "proposition"


class TestCaseDocumentBackCompat:
    """Existing constructors that did NOT pass source_metadata still work."""

    def test_legacy_case_document_works_without_metadata(self):
        doc = CaseDocument(
            case_reference="LON_00AB_HMF_2021_0001",
            year=2021,
            full_text="Some text.",
            source_path="/x/y.pdf",
        )
        assert doc.source_metadata is None

    def test_legacy_chunk_to_chroma_metadata_unchanged(self):
        chunk = DocumentChunk(
            chunk_id="x_0",
            case_reference="x",
            chunk_index=0,
            text="t",
            section_type=SectionType.DECISION,
            year=2021,
            region="LON",
            case_type="HMF",
            token_count=10,
        )
        meta = chunk.to_chroma_metadata()
        # Legacy keys preserved.
        assert meta["case_reference"] == "x"
        assert meta["chunk_index"] == 0
        assert meta["section_type"] == "decision"
        assert meta["year"] == 2021
        assert meta["region"] == "LON"
        assert meta["case_type"] == "HMF"
        assert meta["token_count"] == 10
        # No Phase-4 keys leak in.
        assert "source_publisher" not in meta
        assert "domain_id" not in meta

    def test_phase4_chunk_keeps_legacy_keys_and_adds_new_ones(self):
        chunk = DocumentChunk(
            chunk_id="x_0",
            case_reference="x",
            chunk_index=0,
            text="t",
            section_type=SectionType.DECISION,
            year=2021,
            region="LON",
            case_type="HMF",
            token_count=10,
            source_metadata=_meta(),
        )
        meta = chunk.to_chroma_metadata()
        # Legacy keys still there.
        assert meta["case_reference"] == "x"
        assert meta["section_type"] == "decision"
        # Phase-4 keys added.
        assert meta["domain_id"] == "housing.rro.v1"
        assert meta["source_publisher"] == SourcePublisher.GOVUK.value
        assert meta["source_id"] == "LON_00AB_HMA_2024_0123"
