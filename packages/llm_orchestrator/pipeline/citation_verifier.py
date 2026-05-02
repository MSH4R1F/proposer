"""Citation verifier (SHA-20 Phase 4).

The legal contract is *cite-or-abstain*: any factual claim that is not
backed by a retrieved chunk in this very run is removed (not silently
kept). Phase 4 strengthens the contract along three axes:

1. **source_id**: a citation matches only if a retrieved chunk shares
   its ``source_id`` (or, for legacy rows, its ``case_reference``).
2. **cited_span**: when a citation specifies a paragraph or character
   range, that span must overlap the retrieved chunk's span. This is
   how we stop the LLM from hallucinating *which paragraph* a quote
   came from.
3. **source_kind**: a citation's ``source_kind`` (when known) must
   match the retrieved chunk's ``source_kind``. Statute citations
   cannot be backed by a tribunal-decision chunk and vice versa.

For citations that don't carry the new fields (legacy ``case_reference``
only) the verifier degrades to the historical case-ref-only check, so
the deposit pipeline's existing behaviour is preserved end-to-end.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from ..models.prediction_v2 import (
    Citation,
    IssuePrediction,
    IssueRetrievalResult,
    IssueType,
    VerificationResult,
)

logger = structlog.get_logger()


def normalize_case_ref(ref: str) -> str:
    cleaned = (ref or "").strip().upper()
    cleaned = re.sub(r"/+", "/", cleaned)
    cleaned = cleaned.strip(" .,;:!?'\"()[]{}")

    parts = cleaned.split("/")
    normalized_parts: List[str] = []
    for part in parts:
        if re.fullmatch(r"\d+", part):
            stripped = part.lstrip("0")
            normalized_parts.append(stripped if stripped else "0")
        else:
            normalized_parts.append(part)
    return "/".join(normalized_parts)


# ---------------------------------------------------------------------------
# Span / source-kind helpers
# ---------------------------------------------------------------------------


def _parse_paragraph_field(value: Any) -> Optional[Tuple[int, int]]:
    """Parse a ``Citation.paragraph`` value into a (start, end) span.

    Accepts:
    * ``None`` / empty string                          -> ``None``
    * an int / numeric string ``"7"``                  -> ``(7, 7)``
    * a range ``"7-9"``                                -> ``(7, 9)``
    * ranges with whitespace ``"7 - 9"``               -> ``(7, 9)``
    * any other shape                                  -> ``None`` (no constraint)
    """
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return (value, value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return (min(a, b), max(a, b))
        if re.fullmatch(r"\d+", s):
            n = int(s)
            return (n, n)
    return None


def _spans_overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


def _chunk_paragraph_span(meta: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """Best-effort paragraph span for a retrieved chunk's metadata.

    Falls back to ``None`` when the chunk doesn't carry a paragraph
    annotation (e.g. legacy deposit chunks). In that case the span check
    is treated as vacuously true — Phase 4 only *adds* signal, it must
    not remove citations the legacy path would have accepted.
    """
    p = meta.get("paragraph")
    if p is None:
        return None
    if isinstance(p, int):
        return (p, p)
    if isinstance(p, str) and p.strip():
        parsed = _parse_paragraph_field(p)
        if parsed:
            return parsed
    return None


class CitationVerifier:
    @staticmethod
    def empty_verification() -> VerificationResult:
        """Vacuously-valid result for modes that don't run retrieval (LLM_ONLY, KG_ONLY).

        Used by SHA-33 ablation paths where there are no retrieved cases to verify
        citations against, and the prompt forces an empty supporting_cases list.
        """
        return VerificationResult(
            verified_citations=[],
            removed_citations=[],
            removal_rate=0.0,
            needs_reprediction=False,
            all_citations_valid=True,
        )

    def verify(
        self,
        issue_predictions: List[IssuePrediction],
        retrieval_results: Dict[IssueType, IssueRetrievalResult],
    ) -> Tuple[List[IssuePrediction], VerificationResult]:
        # Index chunks keyed by both case_reference AND source_id (Phase-4)
        # so callers using either resolution path can verify.
        ref_to_chunks: Dict[str, List[Dict[str, Any]]] = {}
        # Proposition indices (SHA-36 Phase 2): kept separate so the chunk
        # path remains semantically simple.
        valid_propositions_by_id: Dict[str, object] = {}
        valid_proposition_results: List[object] = []

        def _add(key: str, meta: Dict[str, Any]) -> None:
            if not key:
                return
            ref_to_chunks.setdefault(key, []).append(meta)

        for retrieval in retrieval_results.values():
            for result in retrieval.results:
                proposition_id = self._get_value(result, "proposition_id", None)
                kind = str(self._get_value(result, "kind", "")).lower()
                if kind == "proposition" or proposition_id:
                    if proposition_id:
                        valid_propositions_by_id[str(proposition_id)] = result
                    valid_proposition_results.append(result)
                    continue

                case_reference = str(self._get_value(result, "case_reference", "") or "")
                source_id = str(self._get_value(result, "source_id", "") or "")
                source_kind = self._get_value(result, "source_kind", None)
                paragraph = self._get_value(result, "paragraph", None)
                meta = {
                    "case_reference": case_reference,
                    "source_id": source_id,
                    "source_kind": source_kind,
                    "paragraph": paragraph,
                }
                _add(normalize_case_ref(case_reference), meta)
                if source_id:
                    # Source ids are publisher-stable; do not case-fold like
                    # case refs — trim and dedupe only.
                    _add(source_id.strip(), meta)

        verified_citations: List[Citation] = []
        removed_citations: List[Citation] = []
        total_citations = 0

        for prediction in issue_predictions:
            kept: List[Citation] = []
            for citation in prediction.supporting_cases:
                total_citations += 1
                # Proposition citations verify via the proposition-specific
                # path (SHA-36 Phase 2). Everything else uses the Phase-4
                # source_id / source_kind / span match.
                if citation.proposition_id:
                    matched = self._verify_proposition_citation(
                        citation,
                        valid_propositions_by_id,
                        valid_proposition_results,
                    )
                else:
                    matched = self._citation_matches(citation, ref_to_chunks)
                if matched:
                    citation.verified = True
                    verified_citations.append(citation)
                    kept.append(citation)
                else:
                    citation.verified = False
                    removed_citations.append(citation)
            prediction.supporting_cases = kept

        removal_rate = (
            len(removed_citations) / total_citations if total_citations > 0 else 0.0
        )
        verification_result = VerificationResult(
            verified_citations=verified_citations,
            removed_citations=removed_citations,
            removal_rate=removal_rate,
            needs_reprediction=removal_rate > 0.3,
            all_citations_valid=len(removed_citations) == 0,
        )

        logger.info(
            "citation_verification_completed",
            total_citations=total_citations,
            verified=len(verified_citations),
            removed=len(removed_citations),
            removal_rate=removal_rate,
            needs_reprediction=verification_result.needs_reprediction,
        )

        return issue_predictions, verification_result

    @staticmethod
    def _get_value(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def _citation_matches(
        cls,
        citation: Citation,
        ref_to_chunks: Dict[str, List[Dict[str, Any]]],
    ) -> bool:
        """Return True iff a retrieved chunk in this run backs this citation.

        Phase-4 contract:
        * source_id (or normalised case_reference) must match a chunk in
          this run.
        * If the chunk carries a ``source_kind`` and the citation also
          carries one (via attribute or model_extra), they must match.
        * If the citation specifies a paragraph/span and the chunk also
          carries one, the spans must overlap. Missing spans on either
          side are treated as a vacuous pass — Phase-4 only *adds*
          signal; we don't reject legacy citations that the historical
          path would have accepted.
        """
        # 1. Resolve candidate chunks
        keys: List[str] = []
        # Phase-4 source_id (carried via Pydantic model_extra or attr)
        source_id_val = (
            getattr(citation, "source_id", None)
            or (
                citation.model_extra.get("source_id")
                if getattr(citation, "model_extra", None)
                else None
            )
        )
        if isinstance(source_id_val, str) and source_id_val.strip():
            keys.append(source_id_val.strip())
        # Legacy case-ref path
        normalized_ref = normalize_case_ref(citation.case_reference)
        if normalized_ref:
            keys.append(normalized_ref)

        candidates: List[Dict[str, Any]] = []
        seen: Set[int] = set()
        for k in keys:
            for chunk in ref_to_chunks.get(k, []):
                if id(chunk) in seen:
                    continue
                seen.add(id(chunk))
                candidates.append(chunk)
        if not candidates:
            return False

        # 2. Optional source_kind match
        cited_kind = getattr(citation, "source_kind", None)
        if cited_kind is None and getattr(citation, "model_extra", None):
            cited_kind = citation.model_extra.get("source_kind")
        cited_kind_str = (
            cited_kind.value if hasattr(cited_kind, "value") else cited_kind
        )

        # 3. Optional paragraph-span overlap
        cited_span = _parse_paragraph_field(citation.paragraph)

        for chunk in candidates:
            chunk_kind = chunk.get("source_kind")
            chunk_kind_str = (
                chunk_kind.value if hasattr(chunk_kind, "value") else chunk_kind
            )
            if (
                cited_kind_str
                and chunk_kind_str
                and cited_kind_str != chunk_kind_str
            ):
                continue
            if cited_span is not None:
                chunk_span = _chunk_paragraph_span(chunk)
                if chunk_span is not None and not _spans_overlap(
                    cited_span, chunk_span
                ):
                    continue
            return True
        return False

    def _verify_proposition_citation(
        self,
        citation: Citation,
        by_id: Dict[str, object],
        results: List[object],
    ) -> bool:
        if citation.proposition_id:
            result = by_id.get(str(citation.proposition_id))
            if result is None:
                return False
            result_ref = normalize_case_ref(
                str(self._get_value(result, "case_reference", ""))
            )
            if normalize_case_ref(citation.case_reference) != result_ref:
                return False
            if citation.paragraph:
                result_paragraph = str(
                    self._get_value(
                        result,
                        "paragraph",
                        self._get_value(result, "paragraph_ref", ""),
                    )
                    or ""
                ).strip()
                if result_paragraph and citation.paragraph.strip() != result_paragraph:
                    return False
            return self._citation_quote_matches_result(citation, result)

        normalized_ref = normalize_case_ref(citation.case_reference)
        paragraph = (citation.paragraph or "").strip()
        for result in results:
            result_ref = normalize_case_ref(
                str(self._get_value(result, "case_reference", ""))
            )
            if result_ref != normalized_ref:
                continue
            result_paragraph = str(
                self._get_value(
                    result,
                    "paragraph",
                    self._get_value(result, "paragraph_ref", ""),
                )
                or ""
            ).strip()
            if paragraph and result_paragraph and paragraph != result_paragraph:
                continue
            if self._citation_quote_matches_result(citation, result):
                return True
        return False

    def _citation_quote_matches_result(self, citation: Citation, result: object) -> bool:
        citation_quote = _normalize_quote(citation.quote)
        if not citation_quote:
            return False
        result_quote = _normalize_quote(
            str(
                self._get_value(
                    result,
                    "quote",
                    self._get_value(
                        result,
                        "source_passage",
                        self._get_value(result, "chunk_text", ""),
                    ),
                )
            )
        )
        if not result_quote:
            return False
        return citation_quote in result_quote


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())
