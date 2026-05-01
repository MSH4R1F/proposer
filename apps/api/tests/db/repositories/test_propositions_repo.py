from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.propositions_repo import PropositionsRepo
from packages.kg_builder.propositions import (
    DecisionDocument,
    ExtractionRunStatus,
    Proposition,
    PropositionEdge,
    PropositionEdgeType,
    PropositionExtractionRun,
    PropositionType,
    deterministic_document_id,
    deterministic_edge_id,
    deterministic_proposition_id,
    sha256_hex,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(case_ref: str = "LON_TEST_2022_0001") -> DecisionDocument:
    """Helper: build a valid DecisionDocument with deterministic id."""
    content_sha = sha256_hex(f"content::{case_ref}")
    text_sha = sha256_hex(f"text::{case_ref}")
    return DecisionDocument(
        document_id=deterministic_document_id(case_ref, content_sha),
        case_reference=case_ref,
        content_sha256=content_sha,
        text_sha256=text_sha,
        char_count=1234,
        extraction_method="fixture_text",
        metadata={"source": "fixture"},
    )


def _make_prop(
    doc: DecisionDocument,
    *,
    paragraph_ref: str | None,
    text: str,
    ptype: PropositionType = PropositionType.fact,
    run_id=None,
    source_passage: str = "the source passage",
) -> Proposition:
    return Proposition(
        proposition_id=deterministic_proposition_id(
            doc.document_id, paragraph_ref, source_passage, ptype, text,
        ),
        document_id=doc.document_id,
        run_id=run_id,
        case_reference=doc.case_reference,
        text=text,
        source_passage=source_passage,
        paragraph_ref=paragraph_ref,
        proposition_type=ptype,
        confidence=0.9,
    )


def _make_run(doc: DecisionDocument) -> PropositionExtractionRun:
    return PropositionExtractionRun(
        document_id=doc.document_id,
        extractor_version="extractor-v1",
        prompt_version="prompt-v1",
        prompt_sha256=sha256_hex("test-prompt-v1"),
        model="gpt-4o-mini",
        status=ExtractionRunStatus.started,
        input_chars=1234,
        chunk_count=1,
        proposition_count=0,
        edge_count=0,
        rejected_count=0,
    )


def _make_edge(
    from_p: Proposition,
    to_p: Proposition,
    *,
    edge_type: PropositionEdgeType = PropositionEdgeType.supports,
) -> PropositionEdge:
    return PropositionEdge(
        edge_id=deterministic_edge_id(
            from_p.proposition_id, to_p.proposition_id, edge_type,
        ),
        from_proposition_id=from_p.proposition_id,
        to_proposition_id=to_p.proposition_id,
        document_id=from_p.document_id,
        edge_type=edge_type,
        confidence=0.85,
    )


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_document_then_get(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    await db_session.commit()

    loaded = await repo.get_document(doc.document_id)
    assert loaded is not None
    assert loaded.document_id == doc.document_id
    assert loaded.case_reference == doc.case_reference
    assert loaded.content_sha256 == doc.content_sha256
    assert loaded.text_sha256 == doc.text_sha256
    assert loaded.char_count == doc.char_count
    assert loaded.extraction_method == doc.extraction_method
    assert loaded.metadata == {"source": "fixture"}


@pytest.mark.asyncio
async def test_upsert_document_idempotent(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    await repo.upsert_document(doc)
    await db_session.commit()

    from sqlalchemy import func, select
    from apps.api.src.db.models import DecisionDocumentRow

    result = await db_session.execute(
        select(func.count()).select_from(DecisionDocumentRow)
    )
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_get_document_by_hash(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    await db_session.commit()

    loaded = await repo.get_document_by_hash(doc.content_sha256)
    assert loaded is not None
    assert loaded.document_id == doc.document_id


@pytest.mark.asyncio
async def test_get_document_returns_none_when_missing(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    assert await repo.get_document(doc.document_id) is None
    assert await repo.get_document_by_hash(doc.content_sha256) is None


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_then_finish_run_succeeded(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    run = _make_run(doc)
    await repo.create_run(run)
    await db_session.commit()

    await repo.finish_run(
        run.run_id,
        status=ExtractionRunStatus.succeeded,
        counts={
            "input_chars": 5000,
            "chunk_count": 3,
            "proposition_count": 12,
            "edge_count": 5,
            "rejected_count": 1,
            "tokens_in": 800,
            "tokens_out": 200,
        },
    )
    await db_session.commit()

    from apps.api.src.db.models import PropositionExtractionRunRow

    row = await db_session.get(PropositionExtractionRunRow, run.run_id)
    assert row is not None
    assert row.status == ExtractionRunStatus.succeeded.value
    assert row.input_chars == 5000
    assert row.chunk_count == 3
    assert row.proposition_count == 12
    assert row.edge_count == 5
    assert row.rejected_count == 1
    assert row.tokens_in == 800
    assert row.tokens_out == 200
    assert row.error_message is None


@pytest.mark.asyncio
async def test_finish_run_failed_records_error_message(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    run = _make_run(doc)
    await repo.create_run(run)
    await db_session.commit()

    await repo.finish_run(
        run.run_id,
        status=ExtractionRunStatus.failed,
        counts={"chunk_count": 0},
        error_message="LLM timeout after 60s",
    )
    await db_session.commit()

    from apps.api.src.db.models import PropositionExtractionRunRow

    row = await db_session.get(PropositionExtractionRunRow, run.run_id)
    assert row is not None
    assert row.status == ExtractionRunStatus.failed.value
    assert row.error_message == "LLM timeout after 60s"
    # Only chunk_count was provided to finish_run; others remain at create_run values.
    assert row.chunk_count == 0
    assert row.input_chars == run.input_chars  # untouched


# ---------------------------------------------------------------------------
# Bulk upserts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_upsert_propositions_returns_inserted_count(
    db_session: AsyncSession,
) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    run = _make_run(doc)
    await repo.create_run(run)
    await db_session.commit()

    props = [
        _make_prop(doc, paragraph_ref="1", text="The deposit was £1500.", run_id=run.run_id),
        _make_prop(doc, paragraph_ref="2", text="Tenancy ended on 2022-06-30.", run_id=run.run_id),
        _make_prop(doc, paragraph_ref="3", text="Cleaning costs were claimed.", run_id=run.run_id),
    ]
    inserted = await repo.bulk_upsert_propositions(props)
    await db_session.commit()
    assert inserted == 3


@pytest.mark.asyncio
async def test_bulk_upsert_propositions_idempotent_on_repeat(
    db_session: AsyncSession,
) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    await db_session.commit()

    props = [
        _make_prop(doc, paragraph_ref="1", text="Fact one."),
        _make_prop(doc, paragraph_ref="2", text="Fact two."),
    ]
    first = await repo.bulk_upsert_propositions(props)
    await db_session.commit()
    second = await repo.bulk_upsert_propositions(props)
    await db_session.commit()

    assert first == 2
    assert second == 0


@pytest.mark.asyncio
async def test_bulk_upsert_edges_idempotent_on_triple(
    db_session: AsyncSession,
) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    p1 = _make_prop(doc, paragraph_ref="1", text="Fact A.")
    p2 = _make_prop(doc, paragraph_ref="2", text="Fact B.")
    await repo.bulk_upsert_propositions([p1, p2])
    await db_session.commit()

    edge = _make_edge(p1, p2, edge_type=PropositionEdgeType.supports)
    first = await repo.bulk_upsert_edges([edge])
    await db_session.commit()
    second = await repo.bulk_upsert_edges([edge])
    await db_session.commit()

    assert first == 1
    assert second == 0

    # Different edge_type on the same triple is a distinct row.
    edge2 = _make_edge(p1, p2, edge_type=PropositionEdgeType.cites)
    third = await repo.bulk_upsert_edges([edge2])
    await db_session.commit()
    assert third == 1


@pytest.mark.asyncio
async def test_bulk_upsert_empty_inputs_return_zero(
    db_session: AsyncSession,
) -> None:
    repo = PropositionsRepo(db_session)
    assert await repo.bulk_upsert_propositions([]) == 0
    assert await repo.bulk_upsert_edges([]) == 0


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_case_filters_and_orders(db_session: AsyncSession) -> None:
    """Two docs share a case_ref. Mixed paragraph_refs incl. None.

    Order must be paragraph_ref ASC NULLS LAST, then proposition_id ASC.
    """
    repo = PropositionsRepo(db_session)

    # Two distinct documents under the same case_reference.
    case_ref = "LON_TEST_2022_SHARED"
    doc_a = DecisionDocument(
        document_id=deterministic_document_id(case_ref + "::a", sha256_hex("a")),
        case_reference=case_ref,
        content_sha256=sha256_hex("content-a"),
        text_sha256=sha256_hex("text-a"),
        char_count=100,
        extraction_method="fixture_text",
    )
    doc_b = DecisionDocument(
        document_id=deterministic_document_id(case_ref + "::b", sha256_hex("b")),
        case_reference=case_ref,
        content_sha256=sha256_hex("content-b"),
        text_sha256=sha256_hex("text-b"),
        char_count=200,
        extraction_method="fixture_text",
    )
    other = DecisionDocument(
        document_id=deterministic_document_id("OTHER", sha256_hex("other")),
        case_reference="OTHER_CASE",
        content_sha256=sha256_hex("content-other"),
        text_sha256=sha256_hex("text-other"),
        char_count=50,
        extraction_method="fixture_text",
    )
    await repo.upsert_document(doc_a)
    await repo.upsert_document(doc_b)
    await repo.upsert_document(other)

    p1 = _make_prop(doc_a, paragraph_ref="2", text="Para two prop.")
    p2 = _make_prop(doc_a, paragraph_ref=None, text="No para prop A.")
    p3 = _make_prop(doc_b, paragraph_ref="1", text="Para one prop.")
    p4 = _make_prop(doc_b, paragraph_ref=None, text="No para prop B.")
    p_other = _make_prop(other, paragraph_ref="1", text="Other case prop.")
    await repo.bulk_upsert_propositions([p1, p2, p3, p4, p_other])
    await db_session.commit()

    listed = await repo.list_by_case(case_ref)
    assert len(listed) == 4
    # First two have paragraph_refs "1" then "2"; last two have None.
    refs = [p.paragraph_ref for p in listed]
    assert refs[0] == "1"
    assert refs[1] == "2"
    assert refs[2] is None
    assert refs[3] is None
    # Stable tiebreaker on proposition_id for the None bucket.
    none_ids = [p.proposition_id for p in listed if p.paragraph_ref is None]
    assert none_ids == sorted(none_ids)


@pytest.mark.asyncio
async def test_list_by_document(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    other = _make_doc(case_ref="LON_OTHER_2022")
    await repo.upsert_document(doc)
    await repo.upsert_document(other)

    p1 = _make_prop(doc, paragraph_ref="3", text="C.")
    p2 = _make_prop(doc, paragraph_ref="1", text="A.")
    p3 = _make_prop(doc, paragraph_ref="2", text="B.")
    p_other = _make_prop(other, paragraph_ref="1", text="Other.")
    await repo.bulk_upsert_propositions([p1, p2, p3, p_other])
    await db_session.commit()

    listed = await repo.list_by_document(doc.document_id)
    assert [p.paragraph_ref for p in listed] == ["1", "2", "3"]
    assert all(p.document_id == doc.document_id for p in listed)


@pytest.mark.asyncio
async def test_list_edges_for_document(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    other = _make_doc(case_ref="LON_OTHER_2023")
    await repo.upsert_document(doc)
    await repo.upsert_document(other)

    a = _make_prop(doc, paragraph_ref="1", text="A.")
    b = _make_prop(doc, paragraph_ref="2", text="B.")
    c = _make_prop(other, paragraph_ref="1", text="C.")
    d = _make_prop(other, paragraph_ref="2", text="D.")
    await repo.bulk_upsert_propositions([a, b, c, d])

    e1 = _make_edge(a, b, edge_type=PropositionEdgeType.supports)
    e2 = _make_edge(c, d, edge_type=PropositionEdgeType.supports)
    await repo.bulk_upsert_edges([e1, e2])
    await db_session.commit()

    listed = await repo.list_edges_for_document(doc.document_id)
    assert len(listed) == 1
    assert listed[0].edge_id == e1.edge_id
    assert listed[0].from_proposition_id == a.proposition_id
    assert listed[0].to_proposition_id == b.proposition_id


@pytest.mark.asyncio
async def test_list_neighbors_outgoing_only(db_session: AsyncSession) -> None:
    """A->B, B->C: neighbors of A should be [B], not [B, C]."""
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)

    a = _make_prop(doc, paragraph_ref="1", text="A.")
    b = _make_prop(doc, paragraph_ref="2", text="B.")
    c = _make_prop(doc, paragraph_ref="3", text="C.")
    await repo.bulk_upsert_propositions([a, b, c])

    ab = _make_edge(a, b, edge_type=PropositionEdgeType.supports)
    bc = _make_edge(b, c, edge_type=PropositionEdgeType.supports)
    await repo.bulk_upsert_edges([ab, bc])
    await db_session.commit()

    neighbors = await repo.list_neighbors(a.proposition_id)
    ids = {p.proposition_id for p in neighbors}
    assert ids == {b.proposition_id}
    # And the source itself is not included.
    assert a.proposition_id not in ids


@pytest.mark.asyncio
async def test_list_neighbors_filtered_by_edge_type(db_session: AsyncSession) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)

    a = _make_prop(doc, paragraph_ref="1", text="A.")
    b = _make_prop(doc, paragraph_ref="2", text="B.")
    c = _make_prop(doc, paragraph_ref="3", text="C.")
    await repo.bulk_upsert_propositions([a, b, c])

    e_supports = _make_edge(a, b, edge_type=PropositionEdgeType.supports)
    e_cites = _make_edge(a, c, edge_type=PropositionEdgeType.cites)
    await repo.bulk_upsert_edges([e_supports, e_cites])
    await db_session.commit()

    only_supports = await repo.list_neighbors(
        a.proposition_id, edge_types=[PropositionEdgeType.supports]
    )
    assert {p.proposition_id for p in only_supports} == {b.proposition_id}

    both = await repo.list_neighbors(a.proposition_id)
    assert {p.proposition_id for p in both} == {b.proposition_id, c.proposition_id}

    only_cites = await repo.list_neighbors(
        a.proposition_id, edge_types=[PropositionEdgeType.cites]
    )
    assert {p.proposition_id for p in only_cites} == {c.proposition_id}


@pytest.mark.asyncio
async def test_list_methods_return_empty_when_no_matches(
    db_session: AsyncSession,
) -> None:
    repo = PropositionsRepo(db_session)
    doc = _make_doc()
    await repo.upsert_document(doc)
    await db_session.commit()

    assert await repo.list_by_case("UNKNOWN_CASE") == []
    assert await repo.list_by_document(doc.document_id) == []
    assert await repo.list_edges_for_document(doc.document_id) == []

    a = _make_prop(doc, paragraph_ref="1", text="A.")
    await repo.bulk_upsert_propositions([a])
    await db_session.commit()
    assert await repo.list_neighbors(a.proposition_id) == []
