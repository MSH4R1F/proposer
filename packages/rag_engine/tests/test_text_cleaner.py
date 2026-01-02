"""
Tests for text cleaning and normalization.
"""

import pytest

from rag_engine.extractors.text_cleaner import TextCleaner, clean_text, detect_pii


class TestTextCleaner:
    """Tests for the TextCleaner class."""

    def test_clean_empty_text(self):
        """Test cleaning empty text returns empty string."""
        cleaner = TextCleaner()
        assert cleaner.clean("") == ""
        assert cleaner.clean(None) == ""

    def test_clean_whitespace_normalization(self):
        """Test that whitespace is normalized correctly."""
        cleaner = TextCleaner(redact_pii=False)

        # Multiple spaces
        text = "The   landlord    failed   to   respond."
        result = cleaner.clean(text)
        assert "   " not in result
        assert "The landlord failed to respond." in result

        # Multiple newlines
        text = "Paragraph one.\n\n\n\n\nParagraph two."
        result = cleaner.clean(text)
        assert "\n\n\n" not in result

        # Tabs to spaces
        text = "Column1\tColumn2\tColumn3"
        result = cleaner.clean(text)
        assert "\t" not in result

    def test_clean_encoding_fixes(self):
        """Test that encoding issues are fixed."""
        cleaner = TextCleaner(redact_pii=False)

        # Smart quotes
        text = "\u201cQuoted text\u201d with \u2018single quotes\u2019"
        result = cleaner.clean(text)
        assert '"Quoted text"' in result
        assert "'single quotes'" in result

        # Dashes
        text = "2020\u20132021 and 2019\u20142020"
        result = cleaner.clean(text)
        assert "2020-2021" in result
        assert "2019-2020" in result

        # Ellipsis
        text = "And so on\u2026"
        result = cleaner.clean(text)
        assert "..." in result

    def test_redact_postcodes(self, sample_text_with_pii):
        """Test that UK postcodes are redacted."""
        cleaner = TextCleaner(redact_pii=True)
        result = cleaner.clean(sample_text_with_pii)

        assert "SW1A 1AA" not in result
        assert "[POSTCODE]" in result

    def test_redact_phone_numbers(self, sample_text_with_pii):
        """Test that phone numbers are redacted."""
        cleaner = TextCleaner(redact_pii=True)
        result = cleaner.clean(sample_text_with_pii)

        assert "07123456789" not in result
        assert "0207 123 4567" not in result
        assert "[PHONE]" in result

    def test_redact_emails(self, sample_text_with_pii):
        """Test that emails are redacted."""
        cleaner = TextCleaner(redact_pii=True)
        result = cleaner.clean(sample_text_with_pii)

        assert "john.smith@example.com" not in result
        assert "landlord@property.co.uk" not in result
        assert "[EMAIL]" in result

    def test_redact_bank_details(self, sample_text_with_pii):
        """Test that bank details are redacted."""
        cleaner = TextCleaner(redact_pii=True)
        result = cleaner.clean(sample_text_with_pii)

        assert "12-34-56" not in result
        assert "12345678" not in result
        assert "[BANK_DETAILS]" in result

    def test_pii_stats_tracking(self, sample_text_with_pii):
        """Test that PII redaction stats are tracked."""
        cleaner = TextCleaner(redact_pii=True)
        cleaner.clean(sample_text_with_pii)

        stats = cleaner.get_stats()
        assert stats["postcodes_redacted"] >= 1
        assert stats["phones_redacted"] >= 1
        assert stats["emails_redacted"] >= 1
        assert stats["bank_details_redacted"] >= 1

    def test_reset_stats(self, sample_text_with_pii):
        """Test that stats can be reset."""
        cleaner = TextCleaner(redact_pii=True)
        cleaner.clean(sample_text_with_pii)

        cleaner.reset_stats()
        stats = cleaner.get_stats()

        assert stats["postcodes_redacted"] == 0
        assert stats["phones_redacted"] == 0

    def test_no_pii_redaction_when_disabled(self, sample_text_with_pii):
        """Test that PII is preserved when redaction is disabled."""
        cleaner = TextCleaner(redact_pii=False)
        result = cleaner.clean(sample_text_with_pii)

        # PII should still be present
        assert "john.smith@example.com" in result
        assert "[EMAIL]" not in result

    def test_remove_bailii_boilerplate(self):
        """Test that BAILII boilerplate is removed."""
        cleaner = TextCleaner(redact_pii=False)
        text = """
        Case decision text here.

        BAILII: Copyright Policy | Disclaimers | Privacy Policy | Feedback | Donate to BAILII

        More text here.
        """
        result = cleaner.clean(text)
        assert "BAILII:" not in result or "Donate to BAILII" not in result

    def test_remove_page_numbers(self):
        """Test that page numbers are removed."""
        cleaner = TextCleaner(redact_pii=False)

        text = """
        Some content here.

        Page 1 of 10

        More content.

        - 2 -

        Final content.
        """
        result = cleaner.clean(text)
        assert "Page 1 of 10" not in result

    def test_preserve_legal_citations(self):
        """Test that legal citations are preserved."""
        cleaner = TextCleaner(redact_pii=True)
        text = "See [2021] UKFTT LON_00AB_HMF_2021_0001 (GRC) for reference."
        result = cleaner.clean(text)

        # The citation should still be present
        assert "2021" in result
        assert "UKFTT" in result


class TestDetectPII:
    """Tests for the detect_pii function."""

    def test_detect_postcode(self):
        """Test detecting postcodes."""
        text = "Address: 123 Test St, London SW1A 1AA"
        findings = detect_pii(text)

        postcode_findings = [f for f in findings if f[0] == "postcode"]
        assert len(postcode_findings) >= 1
        assert "SW1A 1AA" in postcode_findings[0][1]

    def test_detect_email(self):
        """Test detecting emails."""
        text = "Contact: test@example.com for more info"
        findings = detect_pii(text)

        email_findings = [f for f in findings if f[0] == "email"]
        assert len(email_findings) >= 1
        assert "test@example.com" in email_findings[0][1]

    def test_detect_phone(self):
        """Test detecting phone numbers."""
        text = "Call us on 07123456789"
        findings = detect_pii(text)

        phone_findings = [f for f in findings if f[0] == "phone"]
        assert len(phone_findings) >= 1

    def test_detect_returns_positions(self):
        """Test that positions are returned correctly."""
        text = "Email: test@example.com"
        findings = detect_pii(text)

        email_findings = [f for f in findings if f[0] == "email"]
        assert len(email_findings) >= 1

        # Check positions
        pii_type, matched, start, end = email_findings[0]
        assert text[start:end] == matched

    def test_no_pii_detected(self):
        """Test when no PII is present."""
        text = "The tribunal finds in favor of the applicant."
        findings = detect_pii(text)
        assert len(findings) == 0


class TestCleanTextFunction:
    """Tests for the clean_text convenience function."""

    def test_clean_text_with_defaults(self):
        """Test clean_text with default parameters."""
        text = "Email: test@example.com  Multiple   spaces"
        result = clean_text(text)

        assert "[EMAIL]" in result
        assert "   " not in result

    def test_clean_text_without_pii_redaction(self):
        """Test clean_text with PII redaction disabled."""
        text = "Email: test@example.com"
        result = clean_text(text, redact_pii=False)

        assert "test@example.com" in result
        assert "[EMAIL]" not in result


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_unicode_characters(self):
        """Test handling of unicode characters."""
        cleaner = TextCleaner(redact_pii=False)
        text = "Amount: £1,200 and €500"
        result = cleaner.clean(text)
        assert "£1,200" in result

    def test_very_long_text(self):
        """Test handling of very long text."""
        cleaner = TextCleaner(redact_pii=False)
        text = "Word " * 10000  # 50,000 characters
        result = cleaner.clean(text)
        assert len(result) > 0
        assert "Word" in result

    def test_special_legal_terms(self):
        """Test that legal terms are preserved."""
        cleaner = TextCleaner(redact_pii=False)
        text = """
        The landlord failed to comply with section 213 of the Housing Act 2004.
        The prescribed information was not provided within 30 days.
        """
        result = cleaner.clean(text)

        assert "section 213" in result
        assert "Housing Act 2004" in result
        assert "prescribed information" in result

    def test_mixed_content(self, sample_legal_text):
        """Test cleaning a full legal document."""
        cleaner = TextCleaner(redact_pii=True)
        result = cleaner.clean(sample_legal_text)

        # Legal content should be preserved
        assert "FIRST-TIER TRIBUNAL" in result
        assert "rent repayment order" in result
        assert "Housing Act" in result

        # PII should be redacted
        assert "[POSTCODE]" in result  # SW1A 1AA
