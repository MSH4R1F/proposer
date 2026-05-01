"""Structured proposition extractor (SHA-36 Task 6).

Pure component: takes a loaded decision text plus an LLM client (duck-typed
to ``ClaudeClient.generate_structured``) and emits validated atomic
:class:`~kg_builder.propositions.models.Proposition` objects with
provenance preserved.

The extractor does NOT touch the database. Persistence happens in the
Task 9 CLI. The extractor's contract is:

  * Chunk input by paragraph, capped at ``max_chars_per_chunk``.
  * One LLM call per chunk via ``generate_structured``.
  * Each returned item is validated:
      - ``proposition_type`` must be a valid :class:`PropositionType`.
      - ``text`` <= 500 chars, ``source_passage`` <= 1500 chars.
      - ``confidence`` >= ``min_confidence``.
      - ``source_passage`` must verify against the chunk via
        :func:`find_source_span` (whitespace-tolerant substring).
  * Deterministic IDs are assigned **locally** via
    :func:`deterministic_proposition_id` — IDs from the LLM are ignored.
  * Duplicates (same proposition_id within a single run) are rejected,
    not raised.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from kg_builder.propositions.models import (
    Proposition,
    PropositionType,
    deterministic_proposition_id,
)
from kg_builder.propositions.prompts import (
    PROPOSITION_EXTRACTION_SYSTEM_PROMPT,
    PROPOSITION_EXTRACTION_USER_PROMPT,
    PROPOSITION_EXTRACTION_PROMPT_VERSION,
)
from kg_builder.propositions.provenance import find_source_span
from kg_builder.propositions.text_loader import LoadedDecisionText


# ---------------------------------------------------------------------------
# LLM response schema (Pydantic v2)
# ---------------------------------------------------------------------------


class ExtractedPropositionItem(BaseModel):
    """One proposition as the LLM returns it.

    Validated AGAIN by :meth:`LLMPropositionExtractor._convert_item` before
    persistence — Pydantic just guarantees the shape is well-typed.
    ``extra="ignore"`` so the LLM can return additional keys (e.g. ``id``)
    without breaking parsing.
    """

    model_config = ConfigDict(extra="ignore")

    text: str
    source_passage: str
    paragraph_ref: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    issue_tags: list[str] = Field(default_factory=list)
    proposition_type: str  # validated against PropositionType in the converter
    confidence: float


class PropositionExtractionResponse(BaseModel):
    """Top-level LLM response schema. ``extra="ignore"`` for forward compat."""

    model_config = ConfigDict(extra="ignore")

    propositions: list[ExtractedPropositionItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rejection accounting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RejectionRecord:
    """One rejected LLM-emitted item, with a reason code for telemetry.

    Reasons are a closed enum (string literals) so callers can aggregate
    counts without introspecting message text.
    """

    reason: str             # one of: "invalid_enum", "text_too_long", "passage_too_long",
                            # "low_confidence", "quote_not_found", "duplicate_id"
    snippet: str            # short hint for log/debug; truncated to 80 chars


@dataclass(frozen=True)
class ExtractionResult:
    """Output of :meth:`LLMPropositionExtractor.extract`."""

    propositions: list[Proposition]
    rejections: list[RejectionRecord]
    chunks_called: int       # how many LLM calls were made (>=1)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class LLMPropositionExtractor:
    """Extracts atomic propositions from a loaded decision document.

    See module docstring for the contract. The LLM client is duck-typed —
    we only need ``generate_structured(messages, system_prompt,
    response_model, max_tokens) -> response_model``.
    """

    def __init__(
        self,
        llm_client,
        *,
        max_chars_per_chunk: int = 12000,
        min_confidence: float = 0.5,
        max_tokens: int = 16384,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        if max_chars_per_chunk <= 0:
            raise ValueError("max_chars_per_chunk must be positive")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        self.llm = llm_client
        self.max_chars_per_chunk = max_chars_per_chunk
        self.min_confidence = min_confidence
        self.max_tokens = max_tokens
        self.log = logger or logging.getLogger(__name__)

    @property
    def prompt_version(self) -> str:
        """Expose the bundled prompt version for run-record bookkeeping."""
        return PROPOSITION_EXTRACTION_PROMPT_VERSION

    async def extract(
        self,
        *,
        document_id: UUID,
        case_reference: str,
        loaded: LoadedDecisionText,
        run_id: Optional[UUID] = None,
    ) -> ExtractionResult:
        """Run the extraction pipeline.

        Returns accepted propositions + rejection records. Always returns
        ``chunks_called >= 1`` even for short input.
        """
        chunks = self._chunk_by_paragraph(loaded.full_text)
        accepted: list[Proposition] = []
        rejections: list[RejectionRecord] = []
        seen_ids: set[UUID] = set()

        for idx, chunk in enumerate(chunks):
            chunk_span = find_source_span(chunk, loaded.full_text)
            response = await self._call_llm(case_reference, chunk, idx, len(chunks))
            for item in response.propositions:
                outcome = self._convert_item(
                    item,
                    document_id,
                    case_reference,
                    run_id,
                    chunk,
                    chunk_start_char=(
                        chunk_span.start_char if chunk_span is not None else None
                    ),
                )
                if isinstance(outcome, RejectionRecord):
                    self.log.debug(
                        "proposition_rejected",
                        extra={"reason": outcome.reason, "snippet": outcome.snippet},
                    )
                    rejections.append(outcome)
                    continue
                # dedup by deterministic id
                if outcome.proposition_id in seen_ids:
                    rejections.append(RejectionRecord(
                        reason="duplicate_id",
                        snippet=outcome.text[:80],
                    ))
                    continue
                seen_ids.add(outcome.proposition_id)
                accepted.append(outcome)

        return ExtractionResult(
            propositions=accepted,
            rejections=rejections,
            chunks_called=len(chunks),
        )

    # ----- Internals ----- #

    def _chunk_by_paragraph(self, full_text: str) -> list[str]:
        """Split on blank lines (paragraph boundaries), pack into chunks
        <= ``max_chars_per_chunk``.

        Greedy packing: walk paragraphs in order, accumulate until adding
        the next would exceed the budget; emit chunk and start a new one.
        If a single paragraph exceeds the budget, emit it as its own chunk
        (oversize allowed — better than splitting mid-paragraph).

        Returns at least 1 chunk (even for empty/short text — empty input
        yields a single empty chunk so the caller still records ``chunks_called=1``
        for telemetry symmetry).
        """
        if not full_text:
            return [""]

        # Split on blank-line paragraph boundaries; preserve internal whitespace.
        # We use a simple splitter rather than regex so the behaviour is obvious.
        raw_paragraphs = full_text.split("\n\n")
        # Strip purely empty paragraphs (consecutive blank lines).
        paragraphs = [p for p in raw_paragraphs if p.strip()]
        if not paragraphs:
            return [""]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        # Two newlines reconstruct the paragraph break.
        sep = "\n\n"
        sep_len = len(sep)

        for para in paragraphs:
            para_len = len(para)
            # Single paragraph larger than the budget — flush current and
            # emit oversize as its own chunk.
            if para_len > self.max_chars_per_chunk:
                if current:
                    chunks.append(sep.join(current))
                    current = []
                    current_len = 0
                chunks.append(para)
                continue

            extra = para_len if not current else para_len + sep_len
            if current_len + extra > self.max_chars_per_chunk and current:
                chunks.append(sep.join(current))
                current = [para]
                current_len = para_len
            else:
                current.append(para)
                current_len += extra

        if current:
            chunks.append(sep.join(current))

        return chunks or [""]

    async def _call_llm(
        self,
        case_reference: str,
        chunk: str,
        idx: int,
        total: int,
    ) -> PropositionExtractionResponse:
        user_prompt = PROPOSITION_EXTRACTION_USER_PROMPT.format(
            case_reference=case_reference,
            chunk_index=idx + 1,
            chunk_total=total,
            decision_chunk=chunk,
        )
        return await self.llm.generate_structured(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=PROPOSITION_EXTRACTION_SYSTEM_PROMPT,
            response_model=PropositionExtractionResponse,
            max_tokens=self.max_tokens,
        )

    def _convert_item(
        self,
        item: ExtractedPropositionItem,
        document_id: UUID,
        case_reference: str,
        run_id: Optional[UUID],
        chunk_text: str,
        chunk_start_char: Optional[int] = None,
    ) -> Union[Proposition, RejectionRecord]:
        """Validate one LLM item and convert to a domain Proposition,
        OR a RejectionRecord."""

        # 1. enum validation
        try:
            ptype = PropositionType(item.proposition_type)
        except ValueError:
            return RejectionRecord(reason="invalid_enum", snippet=item.text[:80])

        # 2. length checks (Pydantic on Proposition will catch these too,
        #    but rejecting here gives a cleaner reason code than a
        #    ValidationError swallowed in the catch-all below)
        if len(item.text) == 0 or len(item.text) > 500:
            return RejectionRecord(reason="text_too_long", snippet=item.text[:80])
        if len(item.source_passage) == 0 or len(item.source_passage) > 1500:
            return RejectionRecord(
                reason="passage_too_long", snippet=item.source_passage[:80]
            )

        # 3. confidence threshold
        if item.confidence < self.min_confidence:
            return RejectionRecord(reason="low_confidence", snippet=item.text[:80])

        # 4. quote verification — passage must be findable in the chunk
        span = find_source_span(item.source_passage, chunk_text)
        if span is None:
            return RejectionRecord(
                reason="quote_not_found", snippet=item.source_passage[:80]
            )
        source_start_char = span.start_char
        source_end_char = span.end_char
        if chunk_start_char is not None:
            source_start_char += chunk_start_char
            source_end_char += chunk_start_char

        # 5. assemble domain Proposition with deterministic id
        try:
            return Proposition(
                proposition_id=deterministic_proposition_id(
                    document_id,
                    item.paragraph_ref,
                    item.source_passage,
                    ptype,
                    item.text,
                ),
                document_id=document_id,
                run_id=run_id,
                case_reference=case_reference,
                text=item.text,
                source_passage=item.source_passage,
                paragraph_ref=item.paragraph_ref,
                source_start_char=source_start_char,
                source_end_char=source_end_char,
                proposition_type=ptype,
                issue_tags=list(item.issue_tags),
                entities=list(item.entities),
                confidence=item.confidence,
            )
        except Exception:
            # Pydantic validation failure on the domain model. Most common
            # cause at this point is paragraph_ref > 64 chars or
            # case_reference invariants — bucket conservatively.
            return RejectionRecord(reason="text_too_long", snippet=item.text[:80])


__all__ = [
    "ExtractedPropositionItem",
    "PropositionExtractionResponse",
    "RejectionRecord",
    "ExtractionResult",
    "LLMPropositionExtractor",
]
