"""End-to-end CI-safe integration test for the proposition ingestion path
(SHA-36 Task 10).

Exercises the full in-process pipeline against:

  * a real PDF (generated in tmp_path via PyMuPDF — never committed)
  * the real :func:`kg_builder.propositions.text_loader.load_decision_text`
  * a real :class:`apps.api.src.db.repositories.propositions_repo.PropositionsRepo`
    against an isolated migrated Postgres DB (``db_session`` fixture)
  * a mocked LLM client — both the proposition extractor and the edge
    extractor share an :class:`unittest.mock.AsyncMock` whose
    ``generate_structured`` return value is swapped between calls.

Why this sits between unit tests and a full smoke test:

  * Unit tests (Tasks 1-9) cover each component in isolation.
  * The full smoke test (run manually) needs the real BAILII corpus and a
    real Anthropic API key — not safe in CI.
  * This test is CI-safe: zero network, zero secrets, no committed corpus.

Verification commands:

    cd worktrees/sha-36-proposition-kg
    PYTHONPATH=packages python3 -m pytest \\
        apps/api/tests/integration/test_proposition_ingestion.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
from unittest.mock import AsyncMock

import pytest

from apps.api.src.db.repositories.propositions_repo import PropositionsRepo
from packages.kg_builder.propositions import (
    DecisionDocument,
    ExtractionRunStatus,
    PropositionExtractionRun,
    PropositionType,
    deterministic_document_id,
    deterministic_proposition_id,
    sha256_hex,
)
from packages.kg_builder.propositions.edge_extractor import (
    EdgeExtractionResponse,
    ExtractedEdgeItem,
    LLMPropositionEdgeExtractor,
)
from packages.kg_builder.propositions.extractor import (
    ExtractedPropositionItem,
    LLMPropositionExtractor,
    PropositionExtractionResponse,
)
from packages.kg_builder.propositions.graph_validator import validate_graph
from packages.kg_builder.propositions.text_loader import load_decision_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PARAGRAPHS = [
    (
        "The deposit of one thousand five hundred pounds was protected with "
        "the DPS on 12 February 2022, well within the statutory period."
    ),
    (
        "Section 213 of the Housing Act 2004 requires deposit protection "
        "within 30 days of receipt by the landlord."
    ),
    (
        "The Tribunal awarded the tenant the sum of three thousand pounds "
        "in respect of the late protection."
    ),
    (
        "The Respondent cited Superstrike Ltd v Rodrigues 2013 EWCA Civ 669 "
        "as authority for the strict construction of section 213."
    ),
]


def _make_pdf(path: Path, paragraphs: Sequence[str]) -> None:
    """Write a tiny PDF at ``path`` containing the given paragraphs.

    One page per paragraph keeps PyMuPDF's text extraction predictable (no
    line-wrap surprises under the 11pt font on a default-letter page).
    Uses PyMuPDF (``fitz``) which is already a project dependency via
    :mod:`rag_engine.extractors.pdf_extractor`.
    """
    import fitz  # local import: tests are skipped/fail loudly if missing

    doc = fitz.open()
    try:
        for i, text in enumerate(paragraphs):
            page = doc.new_page()
            page.insert_text((50, 72), f"{i + 1}. {text}", fontsize=11)
        doc.save(str(path))
    finally:
        doc.close()


def _build_document(pdf_path: Path, case_ref: str, full_text: str, page_count: int | None) -> DecisionDocument:
    """Helper: build a DecisionDocument from the loaded PDF text.

    ``content_sha256`` is taken over the PDF *bytes* (not the text), so two
    repeat ingestions of the same fixture produce the same document_id —
    this is what the idempotency test relies on.
    """
    content_sha = sha256_hex(
        pdf_path.read_bytes().decode("latin-1", errors="ignore")
    )
    text_sha = sha256_hex(full_text)
    return DecisionDocument(
        document_id=deterministic_document_id(str(pdf_path), content_sha),
        case_reference=case_ref,
        content_sha256=content_sha,
        text_sha256=text_sha,
        char_count=len(full_text),
        page_count=page_count,
        local_path=str(pdf_path),
        extraction_method="pymupdf_pdf",
    )


def _passages_for_default_pdf() -> list[ExtractedPropositionItem]:
    """The three accepted-by-design propositions for the default fixture
    PDF, in paragraph order. Every ``source_passage`` is a verbatim
    substring of one of ``_PARAGRAPHS`` so quote-verification passes.
    """
    return [
        ExtractedPropositionItem(
            text="The deposit of GBP 1,500 was protected on 12 February 2022.",
            source_passage=(
                "The deposit of one thousand five hundred pounds was "
                "protected with the DPS on 12 February 2022"
            ),
            paragraph_ref="1",
            entities=["GBP 1500", "12 February 2022", "DPS"],
            issue_tags=["deposit_protection"],
            proposition_type="fact",
            confidence=0.95,
        ),
        ExtractedPropositionItem(
            text=(
                "Section 213 of the Housing Act 2004 requires protection "
                "within 30 days."
            ),
            source_passage=(
                "Section 213 of the Housing Act 2004 requires deposit "
                "protection within 30 days of receipt by the landlord"
            ),
            paragraph_ref="2",
            entities=["Section 213", "Housing Act 2004"],
            issue_tags=["deposit_protection"],
            proposition_type="rule",
            confidence=0.99,
        ),
        ExtractedPropositionItem(
            text="The Tribunal awarded GBP 3,000 for late protection.",
            source_passage=(
                "The Tribunal awarded the tenant the sum of three thousand "
                "pounds in respect of the late protection"
            ),
            paragraph_ref="3",
            entities=["GBP 3000"],
            issue_tags=["deposit_protection"],
            proposition_type="outcome",
            confidence=0.95,
        ),
    ]


async def _run_full_pipeline(
    pdf_path: Path,
    case_ref: str,
    db_session,
):
    """Execute the full pipeline end-to-end against ``db_session``.

    Returns a small dict with the artefacts the test then asserts on:
    ``{"doc", "run", "props", "edges", "inserted_props", "inserted_edges"}``.
    Used by the happy-path test directly, and twice by the idempotency
    test to prove second-run dedup.
    """
    loaded = load_decision_text(pdf_path)
    doc = _build_document(pdf_path, case_ref, loaded.full_text, loaded.page_count)

    fake_llm = AsyncMock()
    extractor = LLMPropositionExtractor(fake_llm)
    fake_llm.generate_structured.return_value = PropositionExtractionResponse(
        propositions=_passages_for_default_pdf(),
    )
    extraction = await extractor.extract(
        document_id=doc.document_id,
        case_reference=case_ref,
        loaded=loaded,
    )

    # Edge extractor: same AsyncMock, swap return value for the second call.
    rule_id = extraction.propositions[1].proposition_id
    outcome_id = extraction.propositions[2].proposition_id
    fake_llm.generate_structured.return_value = EdgeExtractionResponse(
        edges=[
            ExtractedEdgeItem(
                from_proposition_id=rule_id,
                to_proposition_id=outcome_id,
                edge_type="supports",
                rationale="The rule about section 213 supports the awarded outcome.",
                confidence=0.85,
            ),
        ],
    )
    edge_extractor = LLMPropositionEdgeExtractor(fake_llm)
    edge_result = await edge_extractor.extract_edges(
        doc.document_id, extraction.propositions,
    )

    accepted_edges, _ = validate_graph(
        edge_result.edges,
        extraction.propositions,
        expected_document_id=doc.document_id,
    )

    repo = PropositionsRepo(db_session)
    await repo.upsert_document(doc)

    run = PropositionExtractionRun(
        document_id=doc.document_id,
        extractor_version="sha36-test-v1",
        prompt_version=extractor.prompt_version,
        prompt_sha256=sha256_hex("test-prompt"),
        model="mock",
        status=ExtractionRunStatus.started,
        input_chars=len(loaded.full_text),
        chunk_count=extraction.chunks_called,
        proposition_count=0,
        edge_count=0,
        rejected_count=0,
    )
    await repo.create_run(run)

    props_with_run = [
        p.model_copy(update={"run_id": run.run_id})
        for p in extraction.propositions
    ]
    inserted_props = await repo.bulk_upsert_propositions(props_with_run)
    inserted_edges = await repo.bulk_upsert_edges(accepted_edges)

    await repo.finish_run(
        run.run_id,
        status=ExtractionRunStatus.succeeded,
        counts={
            "input_chars": len(loaded.full_text),
            "chunk_count": extraction.chunks_called,
            "proposition_count": inserted_props,
            "edge_count": inserted_edges,
            "rejected_count": len(extraction.rejections),
        },
    )
    await db_session.commit()

    return {
        "doc": doc,
        "run": run,
        "props": props_with_run,
        "edges": accepted_edges,
        "inserted_props": inserted_props,
        "inserted_edges": inserted_edges,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingestion_pipeline_persists_propositions_and_edges(
    tmp_path, db_session,
):
    """Whole-pipeline happy path against real Postgres + mocked LLM."""
    pdf_path = tmp_path / "fixture_decision.pdf"
    _make_pdf(pdf_path, _PARAGRAPHS)

    # Sanity-check the loader path before we drive the rest of the pipeline.
    loaded = load_decision_text(pdf_path)
    assert loaded.extraction_method == "pymupdf_pdf"
    assert len(loaded.full_text) > 100

    case_ref = "FIXTURE_LON_TEST_2026_0001"
    artefacts = await _run_full_pipeline(pdf_path, case_ref, db_session)

    assert artefacts["inserted_props"] == 3
    assert artefacts["inserted_edges"] == 1
    assert len(artefacts["edges"]) == 1

    # Read-back: prove the rows landed.
    repo = PropositionsRepo(db_session)
    rows = await repo.list_by_case(case_ref)
    assert len(rows) == 3
    assert {r.proposition_type for r in rows} == {
        PropositionType.fact,
        PropositionType.rule,
        PropositionType.outcome,
    }
    assert {r.run_id for r in rows} == {artefacts["run"].run_id}

    edges_back = await repo.list_edges_for_document(artefacts["doc"].document_id)
    assert len(edges_back) == 1
    edge = edges_back[0]
    assert edge.edge_type.value == "supports"
    assert edge.document_id == artefacts["doc"].document_id


@pytest.mark.asyncio
async def test_ingestion_idempotent_on_repeat(tmp_path, db_session):
    """Re-running the pipeline against the same fixture must not duplicate
    document / proposition / edge rows.

    A fresh run row IS created each time (the unique constraint on runs
    was dropped in Task 9 to allow retries), so we expect 2 run rows.
    """
    pdf_path = tmp_path / "fixture_decision.pdf"
    _make_pdf(pdf_path, _PARAGRAPHS)
    case_ref = "FIXTURE_IDEMPOTENT_2026_0001"

    first = await _run_full_pipeline(pdf_path, case_ref, db_session)
    assert first["inserted_props"] == 3
    assert first["inserted_edges"] == 1

    second = await _run_full_pipeline(pdf_path, case_ref, db_session)
    # ON CONFLICT DO NOTHING: the second pass writes zero new prop / edge rows.
    assert second["inserted_props"] == 0
    assert second["inserted_edges"] == 0
    # Same deterministic document id across both runs.
    assert first["doc"].document_id == second["doc"].document_id
    # But two distinct run rows.
    assert first["run"].run_id != second["run"].run_id

    # Read-back: still 3 props, 1 edge for this case.
    repo = PropositionsRepo(db_session)
    rows = await repo.list_by_case(case_ref)
    assert len(rows) == 3
    edges_back = await repo.list_edges_for_document(first["doc"].document_id)
    assert len(edges_back) == 1


@pytest.mark.asyncio
async def test_ingestion_quote_verification_rejects_unfindable_passage(
    tmp_path, db_session,
):
    """A proposition whose ``source_passage`` isn't in the PDF text must
    be rejected by the extractor, never reach the repo, and leave no
    proposition rows for the case."""
    pdf_path = tmp_path / "fixture_quote_reject.pdf"
    _make_pdf(
        pdf_path,
        [
            "The actual decision text only mentions deposit protection. "
            "Nothing else of substance appears in this single-page fixture, "
            "but it is more than one hundred characters long so the loader "
            "accepts it.",
        ],
    )
    loaded = load_decision_text(pdf_path)
    assert len(loaded.full_text) > 100

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = PropositionExtractionResponse(
        propositions=[
            ExtractedPropositionItem(
                text="A wholly fabricated claim.",
                source_passage=(
                    "THIS QUOTE DOES NOT APPEAR IN THE FIXTURE PDF AT ALL"
                ),
                paragraph_ref="1",
                proposition_type="fact",
                confidence=0.99,
            ),
        ],
    )

    case_ref = "FIXTURE_QUOTE_REJECT_2026_0001"
    content_sha = sha256_hex(
        pdf_path.read_bytes().decode("latin-1", errors="ignore"),
    )
    doc_id = deterministic_document_id(str(pdf_path), content_sha)

    extractor = LLMPropositionExtractor(fake_llm)
    result = await extractor.extract(
        document_id=doc_id,
        case_reference=case_ref,
        loaded=loaded,
    )
    assert result.propositions == []
    assert any(r.reason == "quote_not_found" for r in result.rejections)

    # Even if the caller mistakenly tried to persist an empty list, no rows
    # should appear under this case_reference. Use the repo to confirm.
    repo = PropositionsRepo(db_session)
    inserted = await repo.bulk_upsert_propositions(result.propositions)
    assert inserted == 0
    await db_session.commit()
    assert await repo.list_by_case(case_ref) == []


@pytest.mark.asyncio
async def test_ingestion_validator_drops_invalid_edge_after_extraction(
    tmp_path, db_session,
):
    """An edge that the LLM emits but :func:`validate_graph` rejects must
    NOT land in ``proposition_edges``.

    Scenario: the LLM emits ``applies_rule_to_fact`` between two ``fact``
    propositions. The per-item edge extractor accepts it (the endpoint
    types are not checked there) but the graph validator hard-rejects:
    ``applies_rule_to_fact`` requires from=rule, to=fact.
    """
    pdf_path = tmp_path / "fixture_validator_reject.pdf"
    _make_pdf(
        pdf_path,
        [
            (
                "The deposit of one thousand five hundred pounds was "
                "protected with the DPS on 12 February 2022, well within "
                "the statutory period."
            ),
            (
                "The Tribunal awarded the tenant the sum of three thousand "
                "pounds in respect of the late protection."
            ),
        ],
    )
    loaded = load_decision_text(pdf_path)
    case_ref = "FIXTURE_VALIDATOR_REJECT_2026_0001"
    doc = _build_document(pdf_path, case_ref, loaded.full_text, loaded.page_count)

    # Two FACT propositions — applies_rule_to_fact between facts is illegal.
    fact_items = [
        ExtractedPropositionItem(
            text="The deposit of GBP 1,500 was protected on 12 February 2022.",
            source_passage=(
                "The deposit of one thousand five hundred pounds was "
                "protected with the DPS on 12 February 2022"
            ),
            paragraph_ref="1",
            proposition_type="fact",
            confidence=0.95,
        ),
        ExtractedPropositionItem(
            text="The Tribunal awarded GBP 3,000 for late protection.",
            source_passage=(
                "The Tribunal awarded the tenant the sum of three thousand "
                "pounds in respect of the late protection"
            ),
            paragraph_ref="2",
            proposition_type="fact",
            confidence=0.95,
        ),
    ]

    fake_llm = AsyncMock()
    extractor = LLMPropositionExtractor(fake_llm)
    fake_llm.generate_structured.return_value = PropositionExtractionResponse(
        propositions=fact_items,
    )
    extraction = await extractor.extract(
        document_id=doc.document_id,
        case_reference=case_ref,
        loaded=loaded,
    )
    assert len(extraction.propositions) == 2

    fake_llm.generate_structured.return_value = EdgeExtractionResponse(
        edges=[
            ExtractedEdgeItem(
                from_proposition_id=extraction.propositions[0].proposition_id,
                to_proposition_id=extraction.propositions[1].proposition_id,
                edge_type="applies_rule_to_fact",
                rationale="LLM-emitted but illegal between two facts.",
                confidence=0.9,
            ),
        ],
    )
    edge_extractor = LLMPropositionEdgeExtractor(fake_llm)
    edge_result = await edge_extractor.extract_edges(
        doc.document_id, extraction.propositions,
    )
    # Per-item extractor accepts (endpoint-type rules live in the validator).
    assert len(edge_result.edges) == 1

    accepted_edges, validator_rejections = validate_graph(
        edge_result.edges,
        extraction.propositions,
        expected_document_id=doc.document_id,
    )
    assert accepted_edges == []
    assert any(
        r.reason == "applies_rule_to_fact_endpoint_types"
        for r in validator_rejections
    )

    # Persist what the validator approved (nothing) and confirm no edge
    # rows exist for this document.
    repo = PropositionsRepo(db_session)
    await repo.upsert_document(doc)
    run = PropositionExtractionRun(
        document_id=doc.document_id,
        extractor_version="sha36-test-v1",
        prompt_version=extractor.prompt_version,
        prompt_sha256=sha256_hex("test-prompt"),
        model="mock",
        status=ExtractionRunStatus.started,
        input_chars=len(loaded.full_text),
        chunk_count=extraction.chunks_called,
        proposition_count=0,
        edge_count=0,
        rejected_count=0,
    )
    await repo.create_run(run)
    props_with_run = [
        p.model_copy(update={"run_id": run.run_id})
        for p in extraction.propositions
    ]
    inserted_props = await repo.bulk_upsert_propositions(props_with_run)
    inserted_edges = await repo.bulk_upsert_edges(accepted_edges)
    await repo.finish_run(
        run.run_id,
        status=ExtractionRunStatus.succeeded,
        counts={
            "input_chars": len(loaded.full_text),
            "chunk_count": extraction.chunks_called,
            "proposition_count": inserted_props,
            "edge_count": inserted_edges,
            "rejected_count": (
                len(extraction.rejections) + len(validator_rejections)
            ),
        },
    )
    await db_session.commit()

    assert inserted_props == 2
    assert inserted_edges == 0
    edges_back = await repo.list_edges_for_document(doc.document_id)
    assert edges_back == []
