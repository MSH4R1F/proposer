import pytest

from eval.auto_label.canonicalize import (
    CANONICALIZER_VERSION,
    canonicalize_text,
)


class TestCanonicalizerVersion:
    def test_pinned_string(self) -> None:
        # Bumped only when the canonicalisation rules change. Used by
        # LabelingProvenance.canonicalizer_version.
        assert CANONICALIZER_VERSION == "1.0.0"


class TestCanonicalizeText:
    def test_idempotent(self) -> None:
        once = canonicalize_text("Hello world")
        twice = canonicalize_text(once)
        assert once == twice

    def test_nfkc_normalisation(self) -> None:
        # Compatibility-decomposed character (U+FB01 ligature 'fi')
        assert canonicalize_text("ﬁnal") == "final"

    def test_ligature_expansion(self) -> None:
        assert canonicalize_text("oﬀice") == "office"

    def test_dehyphenation_at_line_break(self) -> None:
        assert canonicalize_text("compen-\nsation") == "compensation"

    def test_does_not_dehyphenate_legitimate_compound(self) -> None:
        # Hyphen NOT followed by newline must survive.
        assert canonicalize_text("co-operation") == "co-operation"

    def test_whitespace_collapse(self) -> None:
        assert canonicalize_text("a   b\t\tc\n\n\nd") == "a b c d"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert canonicalize_text("   abc   ") == "abc"

    def test_empty_string(self) -> None:
        assert canonicalize_text("") == ""

    def test_preserves_internal_punctuation(self) -> None:
        # Hyphens, em dashes, quotes are preserved (only normalised).
        assert canonicalize_text("“quote” — ok") == '"quote" — ok'
