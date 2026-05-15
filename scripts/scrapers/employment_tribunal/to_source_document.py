"""Bridge from :class:`ETCaseMetadata` -> :class:`SourceDocument`.

This is the seam every GOV.UK ET ingestion run goes through. Phase-4
:class:`SourceMetadata` fields are filled exactly per the SHA-145 plan:
``domain_id="employment.unfair_dismissal.v1"`` (compatibility ID; the
namespaced ``employment.et.unfair_dismissal.v1`` migration is out of scope
for this PR — spec §3.1), ``domain_family="employment"``,
``forum=Forum.EMPLOYMENT_TRIBUNAL``,
``source_publisher=SourcePublisher.GOVUK``,
``source_kind=SourceKind.CASE_DECISION``.

PII redaction is wired on the model-facing ``raw_text``. The redactor reuses
``rag_engine.extractors.text_cleaner.TextCleaner`` (postcodes, phones,
emails, bank details) and adds an Employment-Tribunal-specific National
Insurance number sweep — claimants and respondents often have NI numbers
quoted in body text. Raw public source is *not* committed; only the
redacted SourceDocument crosses the trust boundary.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple

from rag_engine.extractors.text_cleaner import TextCleaner
from rag_engine.ingestion.contracts import SourceDocument
from rag_engine.source_metadata import SourceMetadata
from domain_core.spec import ChunkKind, Forum, SourceKind, SourcePublisher

from . import PARSER_VERSION
from .config import ScraperConfig
from .models import ETCaseMetadata


# UK National Insurance number pattern. Strict variant: two letters (avoiding
# the disallowed prefixes), six digits, single trailing letter A-D.
# We allow optional internal whitespace ("AB 12 34 56 C") to catch the form
# people write into letters even though HMRC strips it.
_NI_NUMBER_PATTERN = re.compile(
    r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s*"
    r"\d{2}\s*\d{2}\s*\d{2}\s*[A-D]\b",
    re.IGNORECASE,
)

# UK mobile phone numbers (``07XXX XXX XXX`` with optional spaces). The
# upstream :class:`TextCleaner` only matches the no-space form so a number
# like ``07700 900 123`` survives its sweep. ET decisions routinely quote
# numbers in the space-separated form on the cover letter / contact block.
_UK_MOBILE_SPACED_PATTERN = re.compile(
    r"\b0\d{3,4}\s*\d{3}\s*\d{3,4}\b",
)

# Domain id used today on the YAML (`packages/domain_core/domains/
# employment_unfair_dismissal_v1.yaml`). Spec §3.1 forbids renaming this
# in the same PR as the scraper — keep the compatibility ID.
ET_DOMAIN_ID = "employment.unfair_dismissal.v1"
ET_DOMAIN_FAMILY = "employment"
ET_MATTER_TYPE = "unfair_dismissal"


def _content_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def redact_model_facing_text(raw_text: str) -> Tuple[str, Dict[str, int]]:
    """Redact model-facing text for ET ingestion.

    Returns ``(redacted_text, redaction_stats)``. ``redaction_stats`` is the
    union of :class:`TextCleaner`'s counters plus
    ``ni_numbers_redacted`` and ``uk_mobiles_spaced_redacted``.

    Order of passes matters:

    1. NI number sweep first — the upstream TextCleaner's bank-details
       regex (six digits + eight digits) cannibalises the middle of an
       NI like ``AB 12 34 56 C`` if it runs first.
    2. Spaced UK mobile sweep second — TextCleaner's phone regex only
       handles the no-space form, so ``07700 900 123`` survives unless
       we redact it here.
    3. TextCleaner last — picks up postcodes, emails, no-space phones,
       bank details, and normalises whitespace.

    The caller is responsible for persisting the source hash and span
    offsets *before* calling this if it needs to preserve citation
    fidelity across redaction (per spec §5.1). This function intentionally
    does not return positional offsets — see :func:`detect_ni_numbers`
    if a caller needs them.
    """
    text = raw_text or ""
    ni_hits = list(_NI_NUMBER_PATTERN.finditer(text))
    text = _NI_NUMBER_PATTERN.sub("[NI_NUMBER]", text)
    mobile_hits = list(_UK_MOBILE_SPACED_PATTERN.finditer(text))
    text = _UK_MOBILE_SPACED_PATTERN.sub("[PHONE]", text)

    cleaner = TextCleaner(redact_pii=True)
    cleaned = cleaner.clean(text)

    stats = dict(cleaner.get_stats())
    stats["ni_numbers_redacted"] = len(ni_hits)
    stats["uk_mobiles_spaced_redacted"] = len(mobile_hits)
    # Roll the spaced-mobile count into the canonical phones_redacted total
    # so a single key answers "how many phone-like strings were redacted?"
    # for the SHA-65b regression sweep.
    stats["phones_redacted"] = stats.get("phones_redacted", 0) + len(mobile_hits)
    return cleaned, stats


def detect_ni_numbers(text: str) -> List[Tuple[str, int, int]]:
    """Return ``(matched_text, start, end)`` for every NI number in ``text``.

    Exposed for the SHA-65b PII regression sweep (manifest spot-check) so
    the pilot report can prove no NI numbers survived into the committed
    SourceDocument output.
    """
    return [(m.group(), m.start(), m.end()) for m in _NI_NUMBER_PATTERN.finditer(text or "")]


def et_to_source_document(
    meta: ETCaseMetadata,
    raw_text: str,
    *,
    kept_matter_types: List[str],
    config: ScraperConfig,
) -> SourceDocument:
    """Build a :class:`SourceDocument` from a GOV.UK ET decision.

    ``raw_text`` is the body text as parsed; this function applies model-facing
    PII redaction before sealing it into the SourceDocument. ``kept_matter_types``
    is the list returned by :func:`filter.keep_unfair_dismissal_merits_only`
    (typically ``["unfair_dismissal"]``).
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text must be non-empty for SourceDocument creation")

    redacted_text, redaction_stats = redact_model_facing_text(raw_text)
    if not redacted_text or not redacted_text.strip():
        # If redaction stripped the whole thing the case is unusable; surface
        # this as a contract error so SHA-65b/c can quarantine the row
        # rather than silently emitting empty SourceDocuments.
        raise ValueError(
            "redacted text is empty after PII sweep — refusing to emit "
            "SourceDocument for case "
            f"{meta.case_reference!r}; quarantine and inspect"
        )

    metadata = SourceMetadata(
        domain_id=ET_DOMAIN_ID,
        domain_family=ET_DOMAIN_FAMILY,
        forum=Forum.EMPLOYMENT_TRIBUNAL,
        source_id=meta.case_reference,
        source_publisher=SourcePublisher.GOVUK,
        source_kind=SourceKind.CASE_DECISION,
        matter_types=list(kept_matter_types or [ET_MATTER_TYPE]),
        decision_date=meta.decision_date,
        outcome_raw=meta.outcome_raw,
        outcome_normalized=meta.outcome_normalized,
        source_url=meta.source_url,
        source_license=meta.source_license_observed or config.source_license,
        corpus_version=config.corpus_version,
        parser_version=PARSER_VERSION,
        content_sha256=_content_sha256(redacted_text),
        case_reference=meta.case_reference,
        chunk_kind=ChunkKind.DOCUMENT_CHUNK,
    )

    extra: Dict[str, Any] = {
        "jurisdiction_codes": list(meta.jurisdiction_codes or []),
        "case_numbers": list(meta.case_numbers or []),
        "country": meta.country.value,
        "outcome_raw": meta.outcome_raw,
        "outcome_normalized": meta.outcome_normalized,
        "attachments": [
            {
                "url": a.url,
                "title": a.title,
                "content_type": a.content_type,
                "file_size_bytes": a.file_size_bytes,
            }
            for a in (meta.attachments or [])
        ],
        "source_license_observed": meta.source_license_observed,
        "redaction_stats": redaction_stats,
        "parser_diagnostics": list(meta.parser_diagnostics or []),
        # Raw content hash of pre-redaction text — preserved so a redaction
        # regression can be detected (spec §5.1).
        "raw_content_sha256": _content_sha256(raw_text),
    }

    return SourceDocument(
        metadata=metadata,
        raw_text=redacted_text,
        title=meta.title,
        storage_path=meta.raw_storage_path,
        extra=extra,
    )


__all__ = [
    "ET_DOMAIN_ID",
    "ET_DOMAIN_FAMILY",
    "ET_MATTER_TYPE",
    "et_to_source_document",
    "redact_model_facing_text",
    "detect_ni_numbers",
]
