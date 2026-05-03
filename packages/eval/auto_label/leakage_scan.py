"""Facts leakage scanner — firewall between LLM-summarised ``GoldCase.facts``
and the prediction prompt.

``GoldCase.facts`` is copied verbatim into ``CaseFile.tenant_narrative`` by
``apps/api/src/services/case_file_adapter.py`` at prediction time. That adapter
is our leakage contract — we cannot edit it. So if the LLM-summarised facts
text contains tribunal-finding language ("we find", "we award", "the
respondent is liable"), the verdict bleeds straight into the prediction
prompt. The prediction model then echoes the tribunal's actual outcome
instead of reasoning independently — a hard correctness failure that would
silently inflate accuracy on the gold set.

This scanner runs after the labeler emits ``facts`` and before the case is
written to disk. Two checks:

1. **Tribunal-finding phrase scan** — substring match against a curated
   phrase list, performed on ``canonicalize_text(facts).lower()`` so curly
   quotes, ligatures, and casing cannot bypass the scanner. Matches are
   reported with the offending phrase and its char offset in the canonical
   string.

2. **Span-section check** — every ``Provenance`` the labeler attached as a
   source span for ``facts`` must point at a paragraph whose section tag is
   ``"pre_decision_record"``. Spans pointing into ``"tribunal_reasoning"``
   or ``"order_outcome"`` (or any unknown/unmapped section) are flagged —
   we fail closed.

The phrase list is seeded from sparring §3 of
``.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md`` and Codex finding [1]
in the same doc. Tweaking the set requires bumping
``CANONICALIZER_VERSION`` in ``canonicalize.py`` is **not** required, but
the phrase set itself is a labeling contract: if you change it, re-scan
the corpus and bump the labeling provenance ``model_spec`` version so old
labels are not silently grandfathered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from eval.auto_label.canonicalize import canonicalize_text
from eval.schema import Provenance


# Tribunal-finding phrases. ALL stored lower-case; matched after
# ``canonicalize_text(facts).lower()`` so casing, curly quotes, and
# ligatures cannot bypass the scan.
#
# Positive set (from sparring §3): each phrase is a verdict marker that has
# no business appearing in a neutral facts summary. Descriptive party
# submissions ("the applicant submitted", "the respondent argued",
# "the parties agreed", "the applicant claims", "the respondent contends")
# do not contain any of these substrings, so no exclusions are needed —
# the negative set is enforced by the test suite, not by the data.
LEAKAGE_PHRASES: tuple[str, ...] = (
    "the tribunal finds",
    "we find that",
    "we award",
    "we order",
    "we conclude",
    "we determine",
    "we accept the applicant",
    "we accept the respondent",
    "in our view",
    "judgment for the applicant",
    "judgment for the respondent",
    "the respondent is liable",
    "the applicant is liable",
    "we hold that",
)


_PRE_DECISION_TAG = "pre_decision_record"


@dataclass(frozen=True)
class LeakageFinding:
    """A single leakage signal emitted by ``scan_facts_for_leakage``.

    ``rule`` discriminates the two checks; ``detail`` is human-readable
    (the matched phrase, or the offending section tag). For phrase
    findings, ``char_offset`` is the index into ``canonicalize_text(facts)``
    where the phrase begins. For span findings, ``provenance`` is the
    offending ``Provenance`` instance copied from ``source_spans``.
    """

    rule: Literal["tribunal_finding_phrase", "span_outside_pre_decision"]
    detail: str
    char_offset: Optional[int] = None
    provenance: Optional[Provenance] = None


def scan_facts_for_leakage(
    facts: str,
    source_spans: list[Provenance],
    page_sections: dict[tuple[int, int], str],
) -> list[LeakageFinding]:
    """Return all leakage findings; an empty list means ``facts`` is clean.

    Parameters
    ----------
    facts:
        The LLM-summarised facts string about to be written to
        ``GoldCase.facts``. Canonicalised before phrase matching.
    source_spans:
        Every ``Provenance`` the labeler claims as a source for ``facts``.
        Each must point at a paragraph tagged ``"pre_decision_record"``.
    page_sections:
        Section-tag map keyed by ``(page, paragraph)``. Paragraphs missing
        from the map are treated as outside ``pre_decision_record`` (fail
        closed) — the unitization layer is responsible for tagging every
        paragraph the labeler is allowed to cite.
    """
    findings: list[LeakageFinding] = []

    # 1. Phrase scan over canonicalised, lower-cased facts.
    canonical = canonicalize_text(facts).lower()
    for phrase in LEAKAGE_PHRASES:
        # Phrases are already lower-case; search yields all occurrences but
        # we report the first to keep findings deduplicated per phrase.
        idx = canonical.find(phrase)
        if idx != -1:
            findings.append(
                LeakageFinding(
                    rule="tribunal_finding_phrase",
                    detail=phrase,
                    char_offset=idx,
                )
            )

    # 2. Span-section check.
    for span in source_spans:
        section = page_sections.get((span.page, span.paragraph))
        if section != _PRE_DECISION_TAG:
            # Surface the actual tag (or "<unknown>") so reviewers can tell
            # a misrouted span from a missing unitization entry.
            tag_repr = section if section is not None else "<unknown>"
            findings.append(
                LeakageFinding(
                    rule="span_outside_pre_decision",
                    detail=(
                        f"span at (page={span.page}, paragraph={span.paragraph}) "
                        f"is in section '{tag_repr}', expected '{_PRE_DECISION_TAG}'"
                    ),
                    provenance=span,
                )
            )

    return findings
