"""Deterministic text canonicalisation for the auto-grounder.

The grounder relies on stable string equality between an LLM-emitted
quote and the bytes of the source PDF span. Running both sides through
``canonicalize_text`` collapses the common OCR-noise sources: NFKC
compatibility forms, ligature glyphs (``ﬀ``/``ﬁ``/``ﬂ``),
soft-hyphen line breaks (``"compen-\\ncompensation"`` becoming
``"compensation"``), and whitespace runs. Curly quotes are converted to
straight ASCII; em-dashes are preserved.

The version string is pinned and bumped whenever the rule set changes;
``LabelingProvenance.canonicalizer_version`` records it per case so a
schema/prompt/grounder update forces a new corpus version rather than
silently re-baselining old labels.
"""
from __future__ import annotations

import re
import unicodedata

CANONICALIZER_VERSION = "1.0.0"

# Ligatures NFKC does not always normalise to ASCII letters on every
# platform — apply our own table to be safe.
_LIGATURE_TABLE = str.maketrans(
    {
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }
)

# Curly/typographic quotes -> ASCII. Em-dashes and ellipses are preserved.
_QUOTE_TABLE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "′": "'",
        "″": '"',
    }
)

_DEHYPHENATE_RE = re.compile(r"-\n+")
_WS_RUN_RE = re.compile(r"\s+")


def canonicalize_text(text: str) -> str:
    """Return the canonical form of ``text`` for grounder comparison.

    Idempotent: ``canonicalize_text(canonicalize_text(t)) == canonicalize_text(t)``.
    """
    if not text:
        return ""

    # 1. NFKC for compatibility decomposition (handles many ligatures).
    out = unicodedata.normalize("NFKC", text)

    # 2. Belt-and-braces ligature table (NFKC misses some on older Pythons).
    out = out.translate(_LIGATURE_TABLE)

    # 3. Curly quotes -> ASCII.
    out = out.translate(_QUOTE_TABLE)

    # 4. Soft-hyphen line breaks: "compen-\ncompensation" -> "compensation".
    out = _DEHYPHENATE_RE.sub("", out)

    # 5. Whitespace runs (incl. NBSP via NFKC) collapsed to single space.
    out = _WS_RUN_RE.sub(" ", out)

    return out.strip()
