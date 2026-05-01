"""Tests for the structured proposition extractor (SHA-36 Task 6).

Use ``unittest.mock.AsyncMock`` to stand in for ``ClaudeClient``. The mock
returns a ``PropositionExtractionResponse`` instance directly (matching
what ``generate_structured`` returns when called with
``response_model=PropositionExtractionResponse``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from kg_builder.propositions.extractor import (
    ExtractedPropositionItem,
    LLMPropositionExtractor,
    PropositionExtractionResponse,
)
from kg_builder.propositions.models import (
    PropositionType,
    deterministic_document_id,
    normalize_for_matching,
    sha256_hex,
)
from kg_builder.propositions.prompts import (
    PROPOSITION_EXTRACTION_PROMPT_VERSION,
    PROPOSITION_EXTRACTION_SYSTEM_PROMPT,
)
from kg_builder.propositions.text_loader import LoadedDecisionText


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loaded(passages: list[str]) -> LoadedDecisionText:
    """Build a fixture LoadedDecisionText with paragraphs separated by blank lines."""
    full = "\n\n".join(f"{i + 1}. {p}" for i, p in enumerate(passages))
    return LoadedDecisionText(
        full_text=full,
        extraction_method="fixture_text",
        page_count=None,
        metadata={},
    )


def _make_response(items: list[dict]) -> PropositionExtractionResponse:
    return PropositionExtractionResponse(
        propositions=[ExtractedPropositionItem(**i) for i in items]
    )


def _document_id() -> UUID:
    return deterministic_document_id("test://case", sha256_hex("content"))


# ---------------------------------------------------------------------------
# Happy-path / acceptance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_returns_accepted_propositions_when_quote_matches():
    quote = "The deposit was protected on 12 February."
    loaded = _make_loaded([quote, "Some other paragraph text."])

    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Deposit was protected.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }])

    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )

    assert len(result.propositions) == 1
    prop = result.propositions[0]
    assert prop.text == "Deposit was protected."
    assert prop.proposition_type == PropositionType.fact
    assert prop.case_reference == "X"
    assert prop.paragraph_ref == "1"
    assert prop.source_start_char is not None
    assert prop.source_end_char is not None
    normalized = normalize_for_matching(loaded.full_text)
    assert (
        normalized[prop.source_start_char : prop.source_end_char]
        == normalize_for_matching(quote)
    )
    assert prop.confidence == pytest.approx(0.9)
    assert result.rejections == []
    assert result.chunks_called == 1


@pytest.mark.asyncio
async def test_extract_passes_run_id_through():
    quote = "A factual paragraph for run-id check."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Run-id factual claim.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }])
    ext = LLMPropositionExtractor(fake_llm)
    run_id = UUID("12345678-1234-5678-1234-567812345678")
    result = await ext.extract(
        document_id=_document_id(),
        case_reference="X",
        loaded=loaded,
        run_id=run_id,
    )
    assert result.propositions[0].run_id == run_id


@pytest.mark.asyncio
async def test_extract_records_document_level_source_span_for_later_chunks():
    first_quote = "First paragraph about the tenancy deposit."
    second_quote = "Second paragraph says the landlord returned 100 pounds."
    loaded = _make_loaded([first_quote, second_quote])

    fake_llm = AsyncMock()
    fake_llm.generate_structured.side_effect = [
        _make_response([]),
        _make_response([{
            "text": "Landlord returned 100 pounds.",
            "source_passage": second_quote,
            "paragraph_ref": "2",
            "proposition_type": "fact",
            "confidence": 0.9,
        }]),
    ]

    ext = LLMPropositionExtractor(fake_llm, max_chars_per_chunk=80)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )

    prop = result.propositions[0]
    assert prop.source_start_char is not None
    assert prop.source_end_char is not None
    normalized = normalize_for_matching(loaded.full_text)
    assert (
        normalized[prop.source_start_char : prop.source_end_char]
        == normalize_for_matching(second_quote)
    )
    assert prop.source_start_char > len(normalize_for_matching(first_quote))


# ---------------------------------------------------------------------------
# Rejections — each branch of _convert_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_rejects_invalid_proposition_type():
    quote = "Section 213 of the Housing Act applies."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Bad",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fabricated_type",
        "confidence": 0.9,
    }])
    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert len(result.propositions) == 0
    assert any(r.reason == "invalid_enum" for r in result.rejections)


@pytest.mark.asyncio
async def test_extract_rejects_text_too_long():
    quote = "Short quote."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "x" * 600,
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }])
    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert len(result.propositions) == 0
    assert any(r.reason == "text_too_long" for r in result.rejections)


@pytest.mark.asyncio
async def test_extract_rejects_passage_too_long():
    quote = "Short quote in document."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Some claim.",
        # > 1500 chars; doesn't matter that it can't be located, length wins first
        "source_passage": "y" * 1600,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }])
    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert len(result.propositions) == 0
    assert any(r.reason == "passage_too_long" for r in result.rejections)


@pytest.mark.asyncio
async def test_extract_rejects_quote_not_found():
    quote_in_doc = "The deposit was paid."
    loaded = _make_loaded([quote_in_doc])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Some claim.",
        "source_passage": "This text does NOT appear anywhere in the decision document.",
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }])
    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert len(result.propositions) == 0
    assert any(r.reason == "quote_not_found" for r in result.rejections)


@pytest.mark.asyncio
async def test_extract_rejects_low_confidence():
    quote = "A claim text."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Some claim.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.1,
    }])
    ext = LLMPropositionExtractor(fake_llm, min_confidence=0.5)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert len(result.propositions) == 0
    assert any(r.reason == "low_confidence" for r in result.rejections)


# ---------------------------------------------------------------------------
# Determinism / dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_assigns_deterministic_ids():
    """Same inputs -> same proposition_id across two extract() calls."""
    quote = "A factual claim."
    loaded = _make_loaded([quote])
    item = {
        "text": "Factual claim.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }
    fake_llm_1 = AsyncMock()
    fake_llm_1.generate_structured.return_value = _make_response([item])
    fake_llm_2 = AsyncMock()
    fake_llm_2.generate_structured.return_value = _make_response([item])

    ext1 = LLMPropositionExtractor(fake_llm_1)
    ext2 = LLMPropositionExtractor(fake_llm_2)

    doc_id = _document_id()
    r1 = await ext1.extract(document_id=doc_id, case_reference="X", loaded=loaded)
    r2 = await ext2.extract(document_id=doc_id, case_reference="X", loaded=loaded)

    assert r1.propositions[0].proposition_id == r2.propositions[0].proposition_id


@pytest.mark.asyncio
async def test_extract_dedupes_within_run():
    """Same proposition returned across two chunks -> dedup."""
    quote = "Repeated claim."
    loaded = _make_loaded([quote, quote])  # two paragraphs with the same passage
    item = {
        "text": "Same text.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.9,
    }
    fake_llm = AsyncMock()
    fake_llm.generate_structured.side_effect = [
        _make_response([item]),
        _make_response([item]),
    ]
    # max_chars_per_chunk=20 forces two chunks (each paragraph "N. Repeated claim."
    # is 18 chars, so they cannot be packed together).
    ext = LLMPropositionExtractor(fake_llm, max_chars_per_chunk=20)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert result.chunks_called == 2
    assert len(result.propositions) == 1
    assert any(r.reason == "duplicate_id" for r in result.rejections)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_chunks_long_input():
    """Input > max_chars_per_chunk produces multiple LLM calls."""
    big = "\n\n".join(
        f"Paragraph {i} about deposit protection." for i in range(200)
    )
    loaded = LoadedDecisionText(
        full_text=big,
        extraction_method="fixture_text",
        page_count=None,
        metadata={},
    )
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([])

    ext = LLMPropositionExtractor(fake_llm, max_chars_per_chunk=500)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert result.chunks_called > 1
    assert fake_llm.generate_structured.call_count == result.chunks_called


@pytest.mark.asyncio
async def test_extract_oversized_paragraph_emitted_as_own_chunk():
    """A paragraph larger than max_chars_per_chunk gets its own oversize chunk."""
    huge_paragraph = "The deposit. " + "x" * 2000  # one paragraph, no blank lines
    small_paragraph = "Short."
    loaded = LoadedDecisionText(
        full_text=f"{huge_paragraph}\n\n{small_paragraph}",
        extraction_method="fixture_text",
        page_count=None,
        metadata={},
    )
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([])

    ext = LLMPropositionExtractor(fake_llm, max_chars_per_chunk=500)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    # Two chunks: oversize paragraph alone, then the small one.
    assert result.chunks_called == 2


@pytest.mark.asyncio
async def test_extract_empty_response_returns_empty_result():
    quote = "Some text in the document."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([])
    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert result.propositions == []
    assert result.rejections == []
    assert result.chunks_called == 1


# ---------------------------------------------------------------------------
# Prompt-handling / wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_injection_canary_does_not_break_extraction():
    """Decision text contains a unique canary string — it must end up in the
    USER message, not the SYSTEM prompt. (We can't use 'ignore previous
    instructions' as the canary because the system prompt itself contains
    that exact phrase as a defensive example.)"""
    canary = "PROPOSER_CANARY_OVERRIDE_42"
    quote = f"Section 213 {canary} applies to this dispute."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([{
        "text": "Section 213 applies.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "rule",
        "confidence": 0.9,
    }])
    ext = LLMPropositionExtractor(fake_llm)
    await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )

    call = fake_llm.generate_structured.call_args
    user_content = call.kwargs["messages"][0]["content"]
    system_content = call.kwargs["system_prompt"]
    assert canary in user_content
    assert canary not in system_content
    assert system_content == PROPOSITION_EXTRACTION_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_extract_calls_generate_structured_with_correct_response_model():
    """The extractor must pass response_model=PropositionExtractionResponse."""
    loaded = _make_loaded(["A short paragraph for the schema check."])
    fake_llm = AsyncMock()
    fake_llm.generate_structured.return_value = _make_response([])
    ext = LLMPropositionExtractor(fake_llm, max_tokens=2048)
    await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    call = fake_llm.generate_structured.call_args
    assert call.kwargs["response_model"] is PropositionExtractionResponse
    assert call.kwargs["max_tokens"] == 2048
    assert call.kwargs["system_prompt"] == PROPOSITION_EXTRACTION_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_extracted_response_tolerates_extra_keys_from_llm():
    """The LLM may return extra fields (e.g. "id") that we ignore."""
    quote = "A paragraph about deposit issues."
    loaded = _make_loaded([quote])
    fake_llm = AsyncMock()
    # Inject an extra key into the LLM-returned item; extra="ignore" must accept it.
    item = ExtractedPropositionItem.model_validate({
        "text": "Deposit issues exist.",
        "source_passage": quote,
        "paragraph_ref": "1",
        "proposition_type": "fact",
        "confidence": 0.8,
        "id": "should-be-ignored",            # extra
        "fabricated_field": [1, 2, 3],         # extra
    })
    fake_llm.generate_structured.return_value = PropositionExtractionResponse(
        propositions=[item],
    )
    ext = LLMPropositionExtractor(fake_llm)
    result = await ext.extract(
        document_id=_document_id(), case_reference="X", loaded=loaded,
    )
    assert len(result.propositions) == 1


@pytest.mark.asyncio
async def test_prompt_version_is_exposed():
    """Callers (Task 9 CLI) need the prompt version to populate run records."""
    fake_llm = AsyncMock()
    ext = LLMPropositionExtractor(fake_llm)
    assert ext.prompt_version == PROPOSITION_EXTRACTION_PROMPT_VERSION


def test_constructor_rejects_invalid_args():
    fake_llm = AsyncMock()
    with pytest.raises(ValueError):
        LLMPropositionExtractor(fake_llm, max_chars_per_chunk=0)
    with pytest.raises(ValueError):
        LLMPropositionExtractor(fake_llm, min_confidence=1.5)
