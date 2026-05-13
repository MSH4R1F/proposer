"""Tests for the SourceDocument bridge (incl. PII redaction)."""

from __future__ import annotations

from datetime import date

import pytest
from domain_core.spec import ChunkKind, Forum, SourceKind, SourcePublisher

from scripts.scrapers.employment_tribunal import OGL_V3_LICENCE_ID, PARSER_VERSION
from scripts.scrapers.employment_tribunal.config import ScraperConfig
from scripts.scrapers.employment_tribunal.models import (
    Country,
    ETAttachment,
    ETCaseMetadata,
)
from scripts.scrapers.employment_tribunal.to_source_document import (
    ET_DOMAIN_FAMILY,
    ET_DOMAIN_ID,
    ET_MATTER_TYPE,
    detect_ni_numbers,
    et_to_source_document,
    redact_model_facing_text,
)


def _meta(**overrides) -> ETCaseMetadata:
    base = dict(
        case_reference="acme-2024-001",
        title="Mx A v Acme Ltd",
        source_url="https://www.gov.uk/employment-tribunal-decisions/acme-2024-001",
        base_path="/employment-tribunal-decisions/acme-2024-001",
        case_numbers=["2200001/2024"],
        decision_date=date(2024, 4, 12),
        country=Country.ENGLAND_AND_WALES,
        jurisdiction_codes=["Unfair Dismissal"],
        outcome_raw="The claim is well-founded.",
        outcome_normalized="claim-succeeded",
        attachments=[
            ETAttachment(url="https://example.gov.uk/foo.pdf", title="Judgment"),
        ],
        source_license_observed=OGL_V3_LICENCE_ID,
    )
    base.update(overrides)
    return ETCaseMetadata(**base)


class TestRedaction:
    def test_postcode_phone_email_redacted(self):
        text = (
            "Contact claimant via email claimant@example.com or phone "
            "07700 900 123. Address: N1 1AA."
        )
        redacted, stats = redact_model_facing_text(text)
        assert "[POSTCODE]" in redacted
        assert "[PHONE]" in redacted
        assert "[EMAIL]" in redacted
        assert stats["emails_redacted"] >= 1
        assert stats["phones_redacted"] >= 1
        assert stats["postcodes_redacted"] >= 1

    def test_ni_number_redacted(self):
        text = "Claimant NI number AB 12 34 56 C should not survive."
        redacted, stats = redact_model_facing_text(text)
        assert "[NI_NUMBER]" in redacted
        assert "AB 12 34 56 C" not in redacted
        assert stats["ni_numbers_redacted"] == 1

    def test_ni_number_detected_for_audit(self):
        # Both prefixes use valid second letters per HMRC rules
        # ([A-CEGHJ-NPR-TW-Z] excludes D/F/I/O/Q/U/V from the second slot).
        text = "First AB123456C and second nl654321a present in same paragraph."
        hits = detect_ni_numbers(text)
        assert len(hits) == 2
        # Each hit returns (matched_text, start, end) — verify offsets line up.
        for matched, start, end in hits:
            assert text[start:end].lower() == matched.lower()

    def test_redaction_is_idempotent(self):
        text = "Email a@b.com, phone 07700 900 123, postcode SW1A 1AA, NI AB123456C."
        once, _ = redact_model_facing_text(text)
        twice, _ = redact_model_facing_text(once)
        assert once == twice  # placeholders should not re-trigger themselves


class TestSourceDocumentBridge:
    def test_metadata_fields_correctly_populated(self):
        cfg = ScraperConfig()
        body = (
            "The tribunal considered section 98 ERA 1996. The dismissal "
            "was unfair. Polkey deduction of 25% applied."
        )
        doc = et_to_source_document(
            _meta(),
            body,
            kept_matter_types=["unfair_dismissal"],
            config=cfg,
        )

        md = doc.metadata
        assert md.domain_id == ET_DOMAIN_ID
        assert md.domain_family == ET_DOMAIN_FAMILY
        assert md.forum == Forum.EMPLOYMENT_TRIBUNAL
        assert md.source_publisher == SourcePublisher.GOVUK
        assert md.source_kind == SourceKind.CASE_DECISION
        assert md.chunk_kind == ChunkKind.DOCUMENT_CHUNK
        assert md.matter_types == ["unfair_dismissal"]
        assert md.decision_date == date(2024, 4, 12)
        assert md.source_license == OGL_V3_LICENCE_ID
        assert md.corpus_version == cfg.corpus_version
        assert md.parser_version == PARSER_VERSION
        assert md.content_sha256  # non-empty

    def test_default_matter_type_when_none_supplied(self):
        cfg = ScraperConfig()
        doc = et_to_source_document(
            _meta(),
            "section 98 ERA 1996 reasoning here.",
            kept_matter_types=[],
            config=cfg,
        )
        assert doc.metadata.matter_types == [ET_MATTER_TYPE]

    def test_raw_text_is_redacted(self):
        cfg = ScraperConfig()
        body = (
            "section 98 ERA 1996 was considered. Contact: claimant@example.com, "
            "07700 900 123, postcode N1 1AA, NI AB 12 34 56 C."
        )
        doc = et_to_source_document(
            _meta(),
            body,
            kept_matter_types=["unfair_dismissal"],
            config=cfg,
        )
        # The committed raw_text must not contain the unredacted PII.
        assert "claimant@example.com" not in doc.raw_text
        assert "07700 900 123" not in doc.raw_text
        assert "N1 1AA" not in doc.raw_text
        assert "AB 12 34 56 C" not in doc.raw_text
        # And placeholders are present.
        assert "[EMAIL]" in doc.raw_text
        assert "[PHONE]" in doc.raw_text
        assert "[POSTCODE]" in doc.raw_text
        assert "[NI_NUMBER]" in doc.raw_text

    def test_extra_carries_attachments_and_country(self):
        cfg = ScraperConfig()
        doc = et_to_source_document(
            _meta(),
            "section 98 ERA 1996.",
            kept_matter_types=["unfair_dismissal"],
            config=cfg,
        )
        assert doc.extra["country"] == "england_and_wales"
        assert doc.extra["attachments"][0]["url"].endswith(".pdf")
        assert doc.extra["jurisdiction_codes"] == ["Unfair Dismissal"]
        assert doc.extra["redaction_stats"]["ni_numbers_redacted"] == 0
        # raw_content_sha256 must differ from md.content_sha256 (post-redaction)
        # iff redaction changed any byte. Here no PII => they may match. Just
        # assert both exist and are 64 hex chars.
        assert len(doc.extra["raw_content_sha256"]) == 64
        assert len(doc.metadata.content_sha256) == 64

    def test_empty_redacted_text_raises(self):
        cfg = ScraperConfig()
        # Pre-redaction the entire body is PII placeholders + whitespace. The
        # cleaner won't strip them, so this is a sanity check on the
        # contract — empty raw_text upstream still raises.
        with pytest.raises(ValueError):
            et_to_source_document(
                _meta(),
                "",
                kept_matter_types=["unfair_dismissal"],
                config=cfg,
            )

    def test_content_hash_is_over_redacted_text(self):
        cfg = ScraperConfig()
        body = (
            "section 98 ERA 1996 here. Email: foo@example.com phone 07700 900 123 "
            "postcode N1 1AA NI AB123456C."
        )
        doc = et_to_source_document(
            _meta(),
            body,
            kept_matter_types=["unfair_dismissal"],
            config=cfg,
        )
        # The committed content_sha256 should match a fresh hash over the
        # committed raw_text (the redacted form), not the original body.
        import hashlib
        expected = hashlib.sha256(doc.raw_text.encode("utf-8")).hexdigest()
        assert doc.metadata.content_sha256 == expected
        # And the raw-content hash on extra is over the pre-redaction body.
        raw_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert doc.extra["raw_content_sha256"] == raw_hash


class TestLicenceAttribution:
    def test_observed_licence_overrides_config_default(self):
        cfg = ScraperConfig()
        # Pretend the page footer said OGL-unversioned.
        meta = _meta(source_license_observed="OGL-unversioned")
        doc = et_to_source_document(
            meta,
            "section 98 ERA 1996 here.",
            kept_matter_types=["unfair_dismissal"],
            config=cfg,
        )
        assert doc.metadata.source_license == "OGL-unversioned"

    def test_ogl_v3_attribution_string_constant_is_correct(self):
        # The attribution string must literally name OGL v3.0 — citation
        # mapper / disclaimers depend on this exact text.
        from scripts.scrapers.employment_tribunal import OGL_V3_ATTRIBUTION
        assert "Open Government Licence v3.0" in OGL_V3_ATTRIBUTION
        assert "nationalarchives.gov.uk" in OGL_V3_ATTRIBUTION
