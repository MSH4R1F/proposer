"""SHA-20 Phase 4: BM25 must respect ``RetrievalFilterEnvelope``.

The legal contract: hybrid retrieval is correct iff Chroma and BM25
apply the *same* filter set. These tests verify the BM25 side of that
contract for every filter the envelope exposes.
"""

from __future__ import annotations

from datetime import date

import pytest

from domain_core.spec import ChunkKind, Forum, SourceKind, SourcePublisher

from rag_engine.config import (
    DocumentChunk,
    RetrievalFilterEnvelope,
    SectionType,
)
from rag_engine.retrieval.bm25_index import BM25Index
from rag_engine.source_metadata import SourceMetadata


def _meta(
    *,
    source_id: str,
    source_publisher: SourcePublisher = SourcePublisher.BAILII,
    source_kind: SourceKind = SourceKind.CASE_DECISION,
    forum: Forum = Forum.DEPOSIT_SCHEME_ADJUDICATION,
    decision_date: date | None = None,
    matter_types: list[str] | None = None,
) -> SourceMetadata:
    return SourceMetadata(
        domain_id="housing.deposit.v1",
        domain_family="housing",
        forum=forum,
        source_id=source_id,
        source_publisher=source_publisher,
        source_kind=source_kind,
        matter_types=matter_types or ["deposit_deduction"],
        decision_date=decision_date,
        corpus_version="legacy_2025_pre_sha20",
        parser_version="bailii_pdf_v1",
    )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    case_reference: str = "case_x",
    metadata: SourceMetadata | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        case_reference=case_reference,
        chunk_index=int(chunk_id.split("_")[-1]) if chunk_id.split("_")[-1].isdigit() else 0,
        text=text,
        section_type=SectionType.DECISION,
        year=2024,
        region="LON",
        case_type="HMF",
        token_count=len(text.split()),
        source_metadata=metadata,
    )


@pytest.fixture
def index() -> BM25Index:
    # BM25 IDF goes to zero (or negative) when a term appears in more than
    # half the corpus. We make each target doc share a hit term but have
    # a distinctive "anchor" word, then we query for the union — the
    # anchor terms drive the score above zero. The filler docs ensure
    # the shared term is not majority-frequency.
    chunks = [
        _chunk(
            "a_0",
            "tenancy alpha alpha alpha alpha alpha case-a anchor",
            case_reference="case_a",
            metadata=_meta(
                source_id="case_a",
                decision_date=date(2020, 1, 1),
                forum=Forum.DEPOSIT_SCHEME_ADJUDICATION,
                source_publisher=SourcePublisher.BAILII,
            ),
        ),
        _chunk(
            "b_0",
            "tenancy beta beta beta beta beta case-b anchor",
            case_reference="case_b",
            metadata=_meta(
                source_id="case_b",
                decision_date=date(2024, 6, 15),
                forum=Forum.COUNTY_COURT,
                source_publisher=SourcePublisher.GOVUK,
                source_kind=SourceKind.STATUTE,
            ),
        ),
        _chunk(
            "c_0",
            "tenancy gamma gamma gamma gamma gamma case-c anchor",
            case_reference="case_c",
            metadata=_meta(
                source_id="case_c",
                decision_date=date(2025, 3, 1),
                forum=Forum.HOUSING_OMBUDSMAN,
                source_publisher=SourcePublisher.HOUSING_OMBUDSMAN,
                source_kind=SourceKind.OMBUDSMAN_DETERMINATION,
                matter_types=["disrepair"],
            ),
        ),
        # Filler docs with completely different vocabulary, so the
        # anchor words "alpha"/"beta"/"gamma" are unique-per-doc.
        _chunk("f_0", "noise complaint procedure escalation", case_reference="filler1", metadata=_meta(source_id="filler1")),
        _chunk("f_1", "service charge dispute calculation", case_reference="filler2", metadata=_meta(source_id="filler2")),
        _chunk("f_2", "lease management agreement clause", case_reference="filler3", metadata=_meta(source_id="filler3")),
        _chunk("f_3", "rent arrears outstanding payment", case_reference="filler4", metadata=_meta(source_id="filler4")),
        _chunk("f_4", "eviction notice possession claim", case_reference="filler5", metadata=_meta(source_id="filler5")),
    ]
    idx = BM25Index(lite_mode=False)
    idx.build_index(chunks)
    return idx


QUERY = "alpha beta gamma"


class TestExcludedSourceIds:
    def test_excluded_source_ids_filters_via_envelope(self, index):
        env = RetrievalFilterEnvelope(excluded_source_ids=["case_b"])
        results = index.search(QUERY, top_k=10, filters=env)
        ids = {chunk.chunk_id for chunk, _, _ in results}
        assert "b_0" not in ids
        assert "a_0" in ids

    def test_excluded_source_ids_kwarg_shortcut(self, index):
        results = index.search(
            QUERY,
            top_k=10,
            excluded_source_ids=["case_b"],
        )
        ids = {chunk.chunk_id for chunk, _, _ in results}
        assert "b_0" not in ids


class TestDateFilters:
    def test_max_decision_date_excludes_later_decisions(self, index):
        env = RetrievalFilterEnvelope(max_decision_date=date(2023, 12, 31))
        results = index.search(QUERY, top_k=10, filters=env)
        ids = {chunk.chunk_id for chunk, _, _ in results}
        assert "a_0" in ids  # 2020
        assert "b_0" not in ids  # 2024
        assert "c_0" not in ids  # 2025


class TestEnumFilters:
    def test_forum_filter(self, index):
        env = RetrievalFilterEnvelope(forum=Forum.HOUSING_OMBUDSMAN)
        results = index.search(QUERY, top_k=10, filters=env)
        ids = {chunk.chunk_id for chunk, _, _ in results}
        assert ids == {"c_0"}

    def test_source_kind_filter(self, index):
        env = RetrievalFilterEnvelope(source_kind=SourceKind.STATUTE)
        results = index.search(QUERY, top_k=10, filters=env)
        ids = {chunk.chunk_id for chunk, _, _ in results}
        assert ids == {"b_0"}

    def test_source_publisher_filter(self, index):
        env = RetrievalFilterEnvelope(source_publisher=SourcePublisher.HOUSING_OMBUDSMAN)
        results = index.search(QUERY, top_k=10, filters=env)
        ids = {chunk.chunk_id for chunk, _, _ in results}
        assert ids == {"c_0"}


class TestMatterTypeFilter:
    def test_matter_type_uses_in_check_against_pipe_string(self, index):
        env = RetrievalFilterEnvelope(matter_type="deposit_deduction")
        results = index.search(QUERY, top_k=10, filters=env)
        ids = {chunk.chunk_id for chunk, _, _ in results}
        # case_c has matter_types=["disrepair"] so should be excluded.
        assert "c_0" not in ids
        assert "a_0" in ids
