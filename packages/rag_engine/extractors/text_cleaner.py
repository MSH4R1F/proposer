"""
Text cleaning and normalization for legal documents.

Handles whitespace normalization, encoding fixes, and basic PII detection
while preserving legal terminology and citation references.
"""

import re
from typing import List, Tuple

import structlog

logger = structlog.get_logger()


class TextCleaner:
    """
    Clean and normalize extracted text from tribunal decisions.

    Focuses on making text suitable for embedding while preserving
    legal meaning and structure.
    """

    # Common UK postcode pattern
    POSTCODE_PATTERN = re.compile(
        r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}\b",
        re.IGNORECASE
    )

    # UK phone number patterns
    PHONE_PATTERN = re.compile(
        r"\b(?:0[0-9]{10}|(?:\+44|0044)\s?[0-9]{10}|\(?0[0-9]{3,4}\)?\s?[0-9]{3}\s?[0-9]{4})\b"
    )

    # Email pattern
    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )

    # Bank account/sort code patterns
    BANK_PATTERN = re.compile(
        r"\b(?:[0-9]{6}[-\s]?[0-9]{8}|[0-9]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{2})\b"
    )

    # Common noise patterns in tribunal PDFs
    NOISE_PATTERNS = [
        # Page numbers and headers
        re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.MULTILINE),
        re.compile(r"^\s*-\s*\d+\s*-\s*$", re.MULTILINE),
        # BAILII boilerplate
        re.compile(r"BAILII:\s*Copyright Policy.*?Donate to BAILII", re.DOTALL | re.IGNORECASE),
        # Repeated whitespace
        re.compile(r"\n{3,}"),
        # Non-breaking spaces and other unicode whitespace
        re.compile(r"[\xa0\u2000-\u200b\u2028\u2029]+"),
    ]

    # Patterns to preserve (legal citations)
    CITATION_PATTERN = re.compile(
        r"\[\d{4}\]\s*(?:UKFTT|EWCA|EWHC|UKUT|UKSC)\s+[A-Z0-9_]+(?:\s+\([^)]+\))?"
    )

    def __init__(self, redact_pii: bool = True) -> None:
        """
        Initialize the text cleaner.

        Args:
            redact_pii: Whether to redact PII patterns (default True)
        """
        self.redact_pii = redact_pii
        self.pii_stats = {
            "postcodes_redacted": 0,
            "phones_redacted": 0,
            "emails_redacted": 0,
            "bank_details_redacted": 0,
        }

    def clean(self, text: str) -> str:
        """
        Clean and normalize text.

        Args:
            text: Raw text from PDF extraction

        Returns:
            Cleaned text suitable for embedding
        """
        if not text:
            return ""

        # Fix common encoding issues
        text = self._fix_encoding(text)

        # Remove noise patterns
        text = self._remove_noise(text)

        # Normalize whitespace
        text = self._normalize_whitespace(text)

        # Optionally redact PII
        if self.redact_pii:
            text = self._redact_pii(text)

        return text.strip()

    def _fix_encoding(self, text: str) -> str:
        """Fix common encoding issues in extracted text."""
        replacements = {
            # Common mojibake patterns
            "\xe2\x80\x99": "'",
            "\xe2\x80\x9c": '"',
            "\xe2\x80\x9d": '"',
            "\xe2\x80\x94": "-",
            "\xe2\x80\x93": "-",
            "\xc2\xa3": "\u00a3",  # Pound sign
            "\xc2": "",
            # Smart quotes to simple
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            # Dashes
            "\u2013": "-",
            "\u2014": "-",
            # Ellipsis
            "\u2026": "...",
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _remove_noise(self, text: str) -> str:
        """Remove common noise patterns from tribunal PDFs."""
        for pattern in self.NOISE_PATTERNS:
            text = pattern.sub(" ", text)

        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace while preserving paragraph structure."""
        # Convert tabs to spaces
        text = text.replace("\t", " ")

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse multiple spaces to single space
        text = re.sub(r" +", " ", text)

        # Collapse multiple newlines to max 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove spaces at start/end of lines
        text = re.sub(r" *\n *", "\n", text)

        return text

    def _redact_pii(self, text: str) -> str:
        """Redact potential PII patterns."""
        # Preserve legal citations before redacting
        citations = self.CITATION_PATTERN.findall(text)

        # Redact postcodes
        matches = self.POSTCODE_PATTERN.findall(text)
        self.pii_stats["postcodes_redacted"] += len(matches)
        text = self.POSTCODE_PATTERN.sub("[POSTCODE]", text)

        # Redact phone numbers
        matches = self.PHONE_PATTERN.findall(text)
        self.pii_stats["phones_redacted"] += len(matches)
        text = self.PHONE_PATTERN.sub("[PHONE]", text)

        # Redact emails
        matches = self.EMAIL_PATTERN.findall(text)
        self.pii_stats["emails_redacted"] += len(matches)
        text = self.EMAIL_PATTERN.sub("[EMAIL]", text)

        # Redact bank details
        matches = self.BANK_PATTERN.findall(text)
        self.pii_stats["bank_details_redacted"] += len(matches)
        text = self.BANK_PATTERN.sub("[BANK_DETAILS]", text)

        return text

    def get_stats(self) -> dict:
        """Get PII redaction statistics."""
        return self.pii_stats.copy()

    def reset_stats(self) -> None:
        """Reset PII statistics."""
        self.pii_stats = {
            "postcodes_redacted": 0,
            "phones_redacted": 0,
            "emails_redacted": 0,
            "bank_details_redacted": 0,
        }


def detect_pii(text: str) -> List[Tuple[str, str, int, int]]:
    """
    Detect PII in text without redacting.

    Args:
        text: Text to scan

    Returns:
        List of (pii_type, matched_text, start_pos, end_pos)
    """
    cleaner = TextCleaner(redact_pii=False)
    findings = []

    for match in cleaner.POSTCODE_PATTERN.finditer(text):
        findings.append(("postcode", match.group(), match.start(), match.end()))

    for match in cleaner.PHONE_PATTERN.finditer(text):
        findings.append(("phone", match.group(), match.start(), match.end()))

    for match in cleaner.EMAIL_PATTERN.finditer(text):
        findings.append(("email", match.group(), match.start(), match.end()))

    for match in cleaner.BANK_PATTERN.finditer(text):
        findings.append(("bank_details", match.group(), match.start(), match.end()))

    return findings


def clean_text(text: str, redact_pii: bool = True) -> str:
    """
    Convenience function to clean text.

    Args:
        text: Raw text to clean
        redact_pii: Whether to redact PII patterns

    Returns:
        Cleaned text
    """
    cleaner = TextCleaner(redact_pii=redact_pii)
    return cleaner.clean(text)
