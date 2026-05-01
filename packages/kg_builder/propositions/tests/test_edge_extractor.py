"""Tests for the typed proposition edge extractor (SHA-36 Task 7).

Mirrors the AsyncMock pattern used in ``test_extractor.py``. The mock
returns an ``EdgeExtractionResponse`` directly, matching what
``generate_structured`` returns when called with
``response_model=EdgeExtractionResponse``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from kg_builder.propositions.edge_extractor import (
    EdgeExtractionResponse,
    ExtractedEdgeItem,
    LLMPropositionEdgeExtractor,
)
from kg_builder.propositions.models import (
    Proposition,
    PropositionType,
    deterministic_document_id,
    deterministic_edge_id,
    deterministic_proposition_id,
    sha256_hex,
)
from kg_builder.propositions.models import PropositionEdgeType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _document_id() -> UUID:
    return deterministic_document_id("test://edges", sha256_hex("content"))


def _make_proposition(
    document_id: UUID,
    text: str,
    *,
    proposition_type: PropositionType = PropositionType.fact,
    paragraph_ref: str = "1",
    source_passage: str = "Source passage for the proposition.",
) -> Proposition:
    return Proposition(
        proposition_id=deterministic_proposition_id(
            document_id, paragraph_ref, source_passage, proposition_type, text,
        ),
        document_id=document_id,
        case_reference="X",
        text=text,
        source_passage=source_passage,
        paragraph_ref=paragraph_ref,
        proposition_type=proposition_type,
        confidence=0.9,
    )


def _make_response(items: list[dict]) -> EdgeExtractionResponse:
    return EdgeExtractionResponse(
        edges=[ExtractedEdgeItem(**i) for i in items]
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_edges_empty_when_too_few_propositions():
    """0 or 1 propositions → empty result, no LLM call."""
    fake_llm = AsyncMock()
    ext = LLMPropositionEdgeExtractor(fake_llm)
    document_id = _document_id()

    # 0 propositions
    result0 = await ext.extract_edges(document_id, [])
    assert result0.edges == []
    assert result0.rejections == []

    # 1 proposition
    p1 = _make_proposition(document_id, "Single fact.")
    result1 = await ext.extract_edges(document_id, [p1])
    assert result1.edges == []
    assert result1.rejections == []

    fake_llm.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_edges_happy_path_supports():
    """Two facts; LLM returns one supports edge; accepted."""
    document_id = _document_id()
    p1 = _make_proposition(
        document_id, "Deposit was protected late.", paragraph_ref="1",
        source_passage="The deposit was protected late.",
    )
    p2 = _make_proposition(
        document_id, "Tenant awarded penalty.",
        proposition_type=PropositionType.outcome, paragraph_ref="2",
        source_passage="Tenant was awarded the statutory penalty.",
    )

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "supports",
        "rationale": "Late protection supports penalty award.",
        "confidence": 0.85,
    }])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.from_proposition_id == p1.proposition_id
    assert edge.to_proposition_id == p2.proposition_id
    assert edge.edge_type == PropositionEdgeType.supports
    assert edge.document_id == document_id
    assert edge.rationale == "Late protection supports penalty award."
    assert edge.confidence == pytest.approx(0.85)
    assert result.rejections == []


@pytest.mark.asyncio
async def test_extract_edges_rejects_unknown_endpoint():
    """LLM returns from_id not in input set → rejected."""
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    bogus = UUID("00000000-0000-0000-0000-000000000099")

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "from_proposition_id": str(bogus),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "supports",
        "rationale": "Bogus endpoint.",
        "confidence": 0.9,
    }])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert result.edges == []
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "unknown_endpoint"


@pytest.mark.asyncio
async def test_extract_edges_rejects_self_loop():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p1.proposition_id),
        "edge_type": "supports",
        "rationale": "self loop",
        "confidence": 0.9,
    }])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert result.edges == []
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "self_loop"


@pytest.mark.asyncio
async def test_extract_edges_rejects_invalid_edge_type():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "fabricated",
        "rationale": "made up",
        "confidence": 0.9,
    }])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert result.edges == []
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "invalid_edge_type"


@pytest.mark.asyncio
async def test_extract_edges_rejects_low_confidence():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "supports",
        "rationale": "low confidence",
        "confidence": 0.1,
    }])

    ext = LLMPropositionEdgeExtractor(fake_llm, min_confidence=0.5)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert result.edges == []
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "low_confidence"


@pytest.mark.asyncio
async def test_extract_edges_dedups_duplicate_triple():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    item = {
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "supports",
        "rationale": "first",
        "confidence": 0.9,
    }
    item_dup = dict(item)
    item_dup["rationale"] = "second"

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([item, item_dup])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert len(result.edges) == 1
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "duplicate_triple"


@pytest.mark.asyncio
async def test_extract_edges_rejects_long_rationale():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "supports",
        "rationale": "x" * 501,
        "confidence": 0.9,
    }])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    result = await ext.extract_edges(document_id, [p1, p2])

    assert result.edges == []
    assert len(result.rejections) == 1
    assert result.rejections[0].reason == "rationale_too_long"


@pytest.mark.asyncio
async def test_extract_edges_assigns_deterministic_ids():
    """Same inputs → same edge_id."""
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    item = {
        "from_proposition_id": str(p1.proposition_id),
        "to_proposition_id": str(p2.proposition_id),
        "edge_type": "supports",
        "rationale": "stable",
        "confidence": 0.9,
    }

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([item])
    ext = LLMPropositionEdgeExtractor(fake_llm)
    result1 = await ext.extract_edges(document_id, [p1, p2])

    fake_llm2 = AsyncMock()
    fake_llm2.generate_structured.return_value = _make_response([item])
    ext2 = LLMPropositionEdgeExtractor(fake_llm2)
    result2 = await ext2.extract_edges(document_id, [p1, p2])

    assert len(result1.edges) == 1
    assert len(result2.edges) == 1
    assert result1.edges[0].edge_id == result2.edges[0].edge_id
    expected = deterministic_edge_id(
        p1.proposition_id, p2.proposition_id, PropositionEdgeType.supports,
    )
    assert result1.edges[0].edge_id == expected


@pytest.mark.asyncio
async def test_extract_edges_does_not_pass_full_text_to_llm():
    """Critical: user prompt must contain text but NOT source_passage."""
    document_id = _document_id()
    secret_passage = "SECRET_DECISION_PASSAGE_DO_NOT_LEAK_42"
    p1 = _make_proposition(
        document_id, "Visible fact one.", paragraph_ref="1",
        source_passage=secret_passage,
    )
    p2 = _make_proposition(
        document_id, "Visible fact two.", paragraph_ref="2",
        source_passage=secret_passage + "_TWO",
    )

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    await ext.extract_edges(document_id, [p1, p2])

    # Inspect call args
    call_kwargs = fake_llm.generate_structured.call_args.kwargs
    messages = call_kwargs["messages"]
    user_content = "\n".join(m["content"] for m in messages)

    # Texts MUST appear (these are what the LLM reasons about)
    assert "Visible fact one." in user_content
    assert "Visible fact two." in user_content

    # source_passage MUST NOT appear
    assert secret_passage not in user_content
    assert "SECRET_DECISION_PASSAGE" not in user_content

    # Also: paragraph_ref and entities must not appear under those keys
    assert "paragraph_ref" not in user_content
    assert "entities" not in user_content


@pytest.mark.asyncio
async def test_extract_edges_calls_with_correct_response_model():
    document_id = _document_id()
    p1 = _make_proposition(document_id, "Fact one.", paragraph_ref="1")
    p2 = _make_proposition(document_id, "Fact two.", paragraph_ref="2")

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([])

    ext = LLMPropositionEdgeExtractor(fake_llm)
    await ext.extract_edges(document_id, [p1, p2])

    call_kwargs = fake_llm.generate_structured.call_args.kwargs
    assert call_kwargs["response_model"] is EdgeExtractionResponse
    assert "system_prompt" in call_kwargs
    assert call_kwargs["max_tokens"] == ext.max_tokens
