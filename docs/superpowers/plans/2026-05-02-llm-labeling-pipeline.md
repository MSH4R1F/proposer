# LLM-Assisted Gold-Set Labeling Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blocked two-paralegal Phase 3 + Phase 6 of `track-a-plan.md` with a defensible dual-LLM + auto-grounder + human-adjudication pipeline that produces gold-standard rows for `data/gold_standard/housing_v1.jsonl` without collapsing eval methodology into circularity.

**Architecture:** Two LLM providers label the same case in parallel against the `GoldCase` Pydantic schema. A deterministic auto-grounder rejects weakly-supported cells. A `DisagreementSet` plus `MandatoryReviewSet` are routed to a human adjudicator. A 10% audit overlay and a 10–20-case human-only anchor set defend calibration claims. Provenance is captured per case in a new `LabelingProvenance` schema field plus a per-case run artifact.

**Tech Stack:** Pydantic v2, the existing `packages/llm_orchestrator/clients/{factory,claude_client,openai_client,_schema}.py`, `packages/eval/schema.py`, pytest, hypothesis (light use for canonicalizer property tests).

**Reference doc:** `.sisyphus/codex/sha-tbd-llm-labeling-2026-05-02.md` (Codex-revised). Section numbers below cite that file.

---

## File structure (new artifacts)

```
packages/eval/
├── schema.py                              # extended: LabelingProvenance + LabelerModel + FieldLabelProvenance
└── auto_label/
    ├── __init__.py
    ├── canonicalize.py                    # NFKC, ligatures, dehyphen, whitespace
    ├── span_match.py                      # bounded-window quote matcher
    ├── disagreement.py                    # field-path identity + DisagreementSet
    ├── append_gate.py                     # real-gold append refusal logic
    ├── leakage_scan.py                    # facts verdict-leakage scanner
    ├── grounder.py                        # per-field auto-grounder orchestration
    ├── runner.py                          # dual-labeler dispatch + artifact writer
    ├── prompts/
    │   └── extraction.py                  # rendered prompts (template + version hash)
    └── lookups/
        ├── statutes.py                    # versioned UK statutes lookup (stub)
        └── authorities.py                 # versioned BAILII lookup (stub)

packages/llm_orchestrator/clients/
└── labeler_factory.py                     # LabelerModelSpec + build_labeler_client(spec)

scripts/eval/
├── auto_label.py                          # CLI: PDF -> dual labels -> grounded -> pending-adjudication
└── adjudicate.py                          # CLI: walk MandatoryReviewSet + DisagreementSet + audit; finalize row

docs/eval/
├── gold-schema.md                         # extended: provenance section
└── reviewer-guide.md                      # rewritten: adjudicator-only flow

data/eval/labeling_examples/positive/      # hand-labeled positive few-shot exemplars
data/eval_artifacts/labeling/<run_id>/     # per-case JSON artifacts
```

---

## Conventions

- Tests live in `packages/eval/tests/test_auto_label_<module>.py` for the eval package and `packages/llm_orchestrator/tests/test_labeler_factory.py` for the labeler factory.
- Run the eval suite from `packages/eval/` (it has its own `pytest.ini`): `cd packages/eval && python -m pytest tests/ -x -q`.
- Run the orchestrator suite from `packages/llm_orchestrator/`: `cd packages/llm_orchestrator && python -m pytest tests/ -x -q`.
- The existing baseline is **368/368 passing** at `main@29a0cf6`. Every phase below must finish with that count + the new tests passing, **no regressions**.
- Use the shared venv: `source venv/bin/activate` from the repo root before running pytest.
- Conventional commits per CLAUDE.md. Frequent commits per phase.

---

## Phase 1 — Schema additions: `LabelingProvenance` + `GoldCase.labeling_provenance`

**Cites:** sparring §6.

**Files:**
- Modify: `packages/eval/schema.py` (insertions only — no edits to existing classes)
- Create: `packages/eval/tests/test_labeling_provenance.py`
- Modify: `docs/eval/gold-schema.md` (append a "Labeling provenance" section)

### Task 1.1 — Failing test for `LabelerModel`

- [ ] **Step 1:** Create `packages/eval/tests/test_labeling_provenance.py` with:

```python
from datetime import datetime, timezone

import pytest

from packages.eval.schema import LabelerModel


class TestLabelerModel:
    def test_minimal_round_trip(self) -> None:
        m = LabelerModel(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        assert m.provider == "anthropic"
        assert m.model == "claude-sonnet-4-20250514"
        assert m.api_version is None

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(Exception):
            LabelerModel(provider="palm", model="bison-001")

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(Exception):
            LabelerModel(provider="openai", model="gpt-5", store=True)
```

- [ ] **Step 2:** Run `cd packages/eval && python -m pytest tests/test_labeling_provenance.py -v`. Expected: FAIL (ImportError on `LabelerModel`).

- [ ] **Step 3:** In `packages/eval/schema.py`, after `GroundTruthOutcome` (≈ line 196) and before `class GoldCase`, add:

```python
class LabelerModel(StrictBaseModel):
    """A single labeling pass's provider/model/version triple.

    Recorded per case so a published gold set can be re-derived from raw
    LLM outputs (frozen in the run artifact) even after the live model is
    retired. ``api_version`` is optional — set it when the provider exposes
    a stable response-API version string the team should pin.
    """

    provider: Literal["anthropic", "openai"]
    model: str = Field(min_length=1)
    api_version: Optional[str] = None
```

- [ ] **Step 4:** Run `cd packages/eval && python -m pytest tests/test_labeling_provenance.py -v`. Expected: PASS (3 tests).

- [ ] **Step 5:** Commit:

```bash
git add packages/eval/schema.py packages/eval/tests/test_labeling_provenance.py
git commit -m "feat(eval/schema): add LabelerModel for labeling-pass provenance"
```

### Task 1.2 — Failing test for `FieldLabelProvenance`

- [ ] **Step 1:** Append to `tests/test_labeling_provenance.py`:

```python
from packages.eval.schema import FieldLabelProvenance, Provenance


class TestFieldLabelProvenance:
    def test_minimal_deterministic(self) -> None:
        p = FieldLabelProvenance(field_path="domain_id", source="deterministic_manifest")
        assert p.source == "deterministic_manifest"
        assert p.source_spans == []
        assert p.match_strategy is None
        assert p.reviewer_rationale is None

    def test_with_source_span_and_strategy(self) -> None:
        p = FieldLabelProvenance(
            field_path="key_reasoning_quotes[0].text",
            source="model_agreement",
            source_spans=[Provenance(page=3, paragraph=12, text_span=(120, 380))],
            match_strategy="canonical_exact",
        )
        assert p.match_strategy == "canonical_exact"
        assert len(p.source_spans) == 1

    def test_rejects_unknown_source(self) -> None:
        with pytest.raises(Exception):
            FieldLabelProvenance(field_path="facts", source="model_lone_wolf")
```

- [ ] **Step 2:** Run pytest. Expected: FAIL (ImportError).

- [ ] **Step 3:** In `schema.py`, after `LabelerModel`, add:

```python
_PROVENANCE_SOURCES = Literal[
    "deterministic_manifest",
    "model_agreement",
    "human_mandatory_review",
    "human_disagreement_adjudication",
    "human_agreed_cell_audit",
    "human_only_anchor",
]


class FieldLabelProvenance(StrictBaseModel):
    """Per-cell audit trail for a single ``GoldCase`` field.

    ``field_path`` uses the granular notation defined in §4 of the sparring
    plan (e.g. ``"per_issue[issue=damages].winner"``); see
    ``packages/eval/auto_label/disagreement.py`` for the canonical builder.
    """

    field_path: str = Field(min_length=1)
    source: _PROVENANCE_SOURCES
    source_spans: list[Provenance] = Field(default_factory=list)
    match_strategy: Optional[str] = None
    reviewer_rationale: Optional[str] = None
```

- [ ] **Step 4:** Run pytest. Expected: PASS.

- [ ] **Step 5:** Commit:

```bash
git add packages/eval/schema.py packages/eval/tests/test_labeling_provenance.py
git commit -m "feat(eval/schema): add FieldLabelProvenance per-cell audit"
```

### Task 1.3 — Failing test for `LabelingProvenance`

- [ ] **Step 1:** Append:

```python
from packages.eval.schema import LabelingProvenance


def _valid_provenance_kwargs() -> dict:
    return dict(
        run_id="run-2026-05-02-001",
        labeled_at=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
        labeler_models=[
            LabelerModel(provider="anthropic", model="claude-sonnet-4-20250514"),
            LabelerModel(provider="openai", model="gpt-5.5"),
        ],
        source_pdf_sha256="a" * 64,
        ocr_text_sha256="b" * 64,
        prompt_template_hash="t" * 16,
        gold_schema_hash="s" * 16,
        corpus_manifest_hash="c" * 16,
        canonicalizer_version="1.0.0",
        grounder_version="1.0.0",
        audit_seed=42,
        adjudicated_fields=[],
        inter_model_agreement_rate=0.92,
        grounding_pass_rate=0.88,
        audit_flip_rate=0.04,
        mandatory_review_flip_rate=0.10,
        field_provenance=[],
    )


class TestLabelingProvenance:
    def test_minimal_round_trip(self) -> None:
        lp = LabelingProvenance(**_valid_provenance_kwargs())
        round_tripped = LabelingProvenance.model_validate(lp.model_dump())
        assert round_tripped.run_id == lp.run_id
        assert round_tripped.is_human_only_anchor is False

    def test_requires_at_least_one_labeler_model(self) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["labeler_models"] = []
        with pytest.raises(Exception, match="labeler_models"):
            LabelingProvenance(**kwargs)

    def test_anchor_case_flag(self) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["is_human_only_anchor"] = True
        kwargs["anchor_set_id"] = "anchor-housing-v1-2026-05"
        lp = LabelingProvenance(**kwargs)
        assert lp.is_human_only_anchor is True

    @pytest.mark.parametrize("rate", [0.0, 0.5, 1.0])
    def test_rates_within_unit_interval(self, rate: float) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["inter_model_agreement_rate"] = rate
        lp = LabelingProvenance(**kwargs)
        assert lp.inter_model_agreement_rate == rate

    def test_rejects_rate_out_of_unit_interval(self) -> None:
        kwargs = _valid_provenance_kwargs()
        kwargs["audit_flip_rate"] = 1.5
        with pytest.raises(Exception, match="audit_flip_rate"):
            LabelingProvenance(**kwargs)
```

- [ ] **Step 2:** Run pytest. Expected: FAIL.

- [ ] **Step 3:** In `schema.py`, after `FieldLabelProvenance`, add:

```python
class LabelingProvenance(StrictBaseModel):
    """Per-case audit trail produced by ``packages/eval/auto_label/runner.py``.

    Carries every hash and version needed to replay a labeling decision
    once labeler models, OCR engines, or authority indexes drift. Raw LLM
    outputs are NOT stored here — they live in the per-case run artifact
    under ``data/eval_artifacts/labeling/<run_id>/<case_id>.json``. This
    keeps ``housing_v1.jsonl`` rows readable and diffable.
    """

    run_id: str = Field(min_length=1)
    labeled_at: datetime
    labeler_models: list[LabelerModel] = Field(min_length=1)

    # Reproducibility hashes / versions
    source_pdf_sha256: str
    ocr_text_sha256: str
    ocr_engine: Optional[str] = None
    ocr_engine_version: Optional[str] = None
    prompt_template_hash: str = Field(min_length=1)
    prompt_pack_hash: Optional[str] = None
    gold_schema_hash: str = Field(min_length=1)
    corpus_manifest_hash: str = Field(min_length=1)
    domain_spec_hash: Optional[str] = None
    authority_index_id: Optional[str] = None
    authority_index_hash: Optional[str] = None
    statute_index_id: Optional[str] = None
    statute_index_hash: Optional[str] = None
    canonicalizer_version: str = Field(min_length=1)
    grounder_version: str = Field(min_length=1)
    audit_seed: int

    # Human-control status
    is_human_only_anchor: bool = False
    anchor_set_id: Optional[str] = None
    mandatory_review_completed_at: Optional[datetime] = None
    human_adjudicator: Optional[str] = None
    adjudicated_fields: list[str] = Field(default_factory=list)

    # Reported metrics — raw rates, NOT Cohen's kappa.
    inter_model_agreement_rate: float = Field(ge=0.0, le=1.0)
    grounding_pass_rate: float = Field(ge=0.0, le=1.0)
    audit_flip_rate: float = Field(ge=0.0, le=1.0)
    mandatory_review_flip_rate: float = Field(ge=0.0, le=1.0)
    field_provenance: list[FieldLabelProvenance] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_sha256_fields(self) -> "LabelingProvenance":
        for field_name in ("source_pdf_sha256", "ocr_text_sha256"):
            value = getattr(self, field_name)
            if not _SHA256_RE.match(value):
                raise ValueError(
                    f"{field_name} must be 64 lowercase hex chars; got {value!r}"
                )
        return self
```

Also add at the top of `schema.py` (with the other stdlib imports):

```python
from datetime import date, datetime, timezone
```

- [ ] **Step 4:** Run pytest. Expected: PASS.

- [ ] **Step 5:** Commit:

```bash
git add packages/eval/schema.py packages/eval/tests/test_labeling_provenance.py
git commit -m "feat(eval/schema): add LabelingProvenance per-case audit"
```

### Task 1.4 — Wire `labeling_provenance` into `GoldCase`

- [ ] **Step 1:** Append to `tests/test_labeling_provenance.py`:

```python
from packages.eval.tests.conftest import gold_case_minimal_kwargs  # see note


class TestGoldCaseLabelingProvenance:
    def test_optional_default_none(self, gold_case_minimal: dict) -> None:
        from packages.eval.schema import GoldCase

        gc = GoldCase(**gold_case_minimal)
        assert gc.labeling_provenance is None

    def test_round_trip_with_provenance(self, gold_case_minimal: dict) -> None:
        from packages.eval.schema import GoldCase

        gold_case_minimal["labeling_provenance"] = LabelingProvenance(
            **_valid_provenance_kwargs()
        ).model_dump(mode="json")
        gc = GoldCase(**gold_case_minimal)
        assert gc.labeling_provenance is not None
        assert gc.labeling_provenance.run_id == "run-2026-05-02-001"
```

If `packages/eval/tests/conftest.py` does not already expose a `gold_case_minimal` fixture, define one inline in this test file using `tests/fixtures/gold_case_minimal.json` (read + json.loads).

- [ ] **Step 2:** Run pytest. Expected: FAIL (`labeling_provenance` not on `GoldCase`).

- [ ] **Step 3:** In `schema.py`, inside `GoldCase`, after the SHA-20 Phase 7 block (after `expected_redacted_text`), append:

```python
    labeling_provenance: Optional[LabelingProvenance] = Field(
        default=None,
        description=(
            "When set, this row was produced by the auto-label pipeline "
            "(dual-LLM + auto-grounder + human adjudication). None means "
            "the row predates the pipeline (legacy hand-annotated cases). "
            "See packages/eval/auto_label/runner.py and "
            "docs/eval/gold-schema.md."
        ),
    )
```

- [ ] **Step 4:** Run pytest. Expected: PASS. Then run the full eval suite to prove no regression: `cd packages/eval && python -m pytest tests/ -x -q`. Expect 368 + new ones passing.

- [ ] **Step 5:** Commit:

```bash
git add packages/eval/schema.py packages/eval/tests/test_labeling_provenance.py
git commit -m "feat(eval/schema): wire optional labeling_provenance onto GoldCase"
```

### Task 1.5 — Document provenance in `docs/eval/gold-schema.md`

- [ ] **Step 1:** Append a section titled "Labeling provenance (sparring plan §6)" describing `LabelerModel`, `FieldLabelProvenance`, `LabelingProvenance`, the `_PROVENANCE_SOURCES` literal, and that `labeling_provenance is None` means the row predates the pipeline. Note: raw LLM outputs live in `data/eval_artifacts/labeling/<run_id>/<case_id>.json`, NOT in the JSONL row.

- [ ] **Step 2:** Commit:

```bash
git add docs/eval/gold-schema.md
git commit -m "docs(eval): document LabelingProvenance fields"
```

---

## Phase 2 — Deterministic text canonicalizer

**Cites:** sparring §3 ("canonicalisation: NFKC, ligature expansion, dehyphenation, whitespace collapse").

**Files:**
- Create: `packages/eval/auto_label/__init__.py`
- Create: `packages/eval/auto_label/canonicalize.py`
- Create: `packages/eval/tests/test_auto_label_canonicalize.py`

### Task 2.1 — Create the package skeleton

- [ ] **Step 1:** Create `packages/eval/auto_label/__init__.py`:

```python
"""Deterministic auto-grounding pipeline for LLM-assisted gold labeling.

Modules in this package are pure: no LLM calls, no I/O beyond explicit
artifact writers. The dual-LLM dispatcher and CLI live in ``runner.py``
and the ``scripts/eval/auto_label.py`` / ``scripts/eval/adjudicate.py``
entry points respectively.
"""
```

- [ ] **Step 2:** Commit:

```bash
git add packages/eval/auto_label/__init__.py
git commit -m "feat(eval/auto_label): create package skeleton"
```

### Task 2.2 — Failing test for `canonicalize_text`

- [ ] **Step 1:** Create `packages/eval/tests/test_auto_label_canonicalize.py`:

```python
import pytest

from packages.eval.auto_label.canonicalize import (
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
        once = canonicalize_text("Hello world")
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
```

- [ ] **Step 2:** Run pytest. Expected: FAIL (ImportError).

- [ ] **Step 3:** Create `packages/eval/auto_label/canonicalize.py`:

```python
"""Deterministic text canonicalisation for the auto-grounder.

The grounder relies on stable string equality between an LLM-emitted
quote and the bytes of the source PDF span. Running both sides through
``canonicalize_text`` collapses the common OCR-noise sources: NFKC
compatibility forms, ligature glyphs (``ﬀ``/``ﬁ``/``ﬂ``),
soft-hyphen line breaks (``"compen-\ncompensation"`` becoming
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
```

- [ ] **Step 4:** Run pytest. Expected: PASS (all canonicalize tests).

- [ ] **Step 5:** Commit:

```bash
git add packages/eval/auto_label/canonicalize.py packages/eval/tests/test_auto_label_canonicalize.py
git commit -m "feat(eval/auto_label): deterministic text canonicalizer"
```

---

## Phase 3 — Bounded-window quote span matcher

**Cites:** sparring §3 ("Bounded OCR drift recovery: allow small deterministic edit distance only inside the claimed span window; record `match_strategy`").

**Files:**
- Create: `packages/eval/auto_label/span_match.py`
- Create: `packages/eval/tests/test_auto_label_span_match.py`

### Task 3.1 — Failing test for `match_quote_in_span`

- [ ] **Step 1:** Create `packages/eval/tests/test_auto_label_span_match.py`:

```python
import pytest

from packages.eval.auto_label.span_match import (
    MatchResult,
    MatchStrategy,
    match_quote_in_span,
)


PAGE_TEXT = (
    "1. The tribunal heard evidence on 12 March 2024.\n"
    "2. The respondent argued the deposit was protected within 30 days.\n"
    "3. We accept the applicant's evidence on the timing of the protection.\n"
    "4. Section 213 of the Housing Act 2004 applies."
)


class TestMatchQuoteInSpan:
    def test_exact_canonical_match(self) -> None:
        # text_span covers paragraph 2 in PAGE_TEXT.
        start = PAGE_TEXT.index("The respondent")
        end = PAGE_TEXT.index("days.") + len("days.")
        result = match_quote_in_span(
            quote="The respondent argued the deposit was protected within 30 days.",
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
        )
        assert result.matched is True
        assert result.strategy == MatchStrategy.CANONICAL_EXACT
        assert result.edit_distance == 0

    def test_canonical_normalisation_match(self) -> None:
        # OCR drift: ligature for "fi", curly quote, doubled whitespace.
        start = PAGE_TEXT.index("Section")
        end = len(PAGE_TEXT)
        result = match_quote_in_span(
            quote="“Section 213 of the Housing Act 2004 applies.”",
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
        )
        # Canonicalise both sides and re-check exact membership.
        assert result.matched is True
        assert result.strategy == MatchStrategy.CANONICAL_EXACT

    def test_bounded_edit_distance_inside_window(self) -> None:
        # Quote has a single OCR substitution ("0" -> "O"), span window is
        # large enough that fuzzy match within budget succeeds.
        start = PAGE_TEXT.index("Section")
        end = len(PAGE_TEXT)
        result = match_quote_in_span(
            quote="Section 213 of the Housing Act 2OO4 applies.",
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
            max_edit_distance=3,
        )
        assert result.matched is True
        assert result.strategy == MatchStrategy.BOUNDED_FUZZY
        assert 0 < result.edit_distance <= 3

    def test_outside_span_window_does_not_match(self) -> None:
        # Quote exists in the page, but caller pointed at a span that does
        # NOT contain it. The matcher must REFUSE — no whole-document
        # fallback (this is exactly the prompt-injection hardening rule).
        para1_start = 0
        para1_end = PAGE_TEXT.index("\n2.")
        result = match_quote_in_span(
            quote="Section 213 of the Housing Act 2004 applies.",
            page_text=PAGE_TEXT,
            char_start=para1_start,
            char_end=para1_end,
        )
        assert result.matched is False
        assert result.strategy == MatchStrategy.NO_MATCH

    def test_edit_distance_above_budget_rejects(self) -> None:
        start = PAGE_TEXT.index("Section")
        end = len(PAGE_TEXT)
        result = match_quote_in_span(
            quote="Section 999 of the Housing Act 1066 was repealed.",  # very different
            page_text=PAGE_TEXT,
            char_start=start,
            char_end=end,
            max_edit_distance=3,
        )
        assert result.matched is False

    def test_empty_quote_rejected(self) -> None:
        with pytest.raises(ValueError):
            match_quote_in_span(quote="", page_text=PAGE_TEXT, char_start=0, char_end=10)

    def test_invalid_span_rejected(self) -> None:
        with pytest.raises(ValueError):
            match_quote_in_span(
                quote="anything",
                page_text=PAGE_TEXT,
                char_start=10,
                char_end=5,
            )
```

- [ ] **Step 2:** Run pytest. Expected: FAIL (ImportError).

- [ ] **Step 3:** Create `packages/eval/auto_label/span_match.py`:

```python
"""Bounded-window quote/span matcher.

The auto-grounder rejects any LLM-emitted quote that does not appear
inside its declared ``(page, paragraph, text_span)`` window, even if the
text exists elsewhere in the PDF. This is the prompt-injection hardening
rule from the sparring plan §3: no whole-document fuzzy fallback.

Two strategies are accepted:

* ``CANONICAL_EXACT`` — after canonicalisation, the quote is a substring
  of the canonicalised span window. Always preferred.
* ``BOUNDED_FUZZY`` — Levenshtein distance to the best-scoring substring
  of the canonicalised span window is <= ``max_edit_distance``. Used only
  to recover from genuine OCR drift inside the claimed window.

Anything else is ``NO_MATCH``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .canonicalize import canonicalize_text


class MatchStrategy(str, Enum):
    CANONICAL_EXACT = "canonical_exact"
    BOUNDED_FUZZY = "bounded_fuzzy"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    strategy: MatchStrategy
    edit_distance: int  # 0 for exact; -1 for NO_MATCH.


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Standard DP, O(len(a)*len(b)) — fine for sentence-length spans.
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _best_window_distance(needle: str, haystack: str, budget: int) -> int:
    """Return the minimum Levenshtein distance between ``needle`` and any
    contiguous substring of ``haystack`` whose length is within
    ``[len(needle) - budget, len(needle) + budget]``. Returns ``budget + 1``
    if no candidate window beats the budget — callers treat that as
    no-match.
    """
    n = len(needle)
    h = len(haystack)
    if n == 0 or h == 0:
        return budget + 1

    best = budget + 1
    min_w = max(1, n - budget)
    max_w = min(h, n + budget)
    for w in range(min_w, max_w + 1):
        for i in range(0, h - w + 1):
            d = _levenshtein(needle, haystack[i : i + w])
            if d < best:
                best = d
                if best == 0:
                    return 0
    return best


def match_quote_in_span(
    *,
    quote: str,
    page_text: str,
    char_start: int,
    char_end: int,
    max_edit_distance: int = 0,
) -> MatchResult:
    """Determine whether ``quote`` is grounded in ``page_text[char_start:char_end]``.

    Args:
        quote: The string the LLM claims to be quoting.
        page_text: The full canonicalised-or-raw page text the labeler saw.
        char_start, char_end: The labeler's declared span window
            (half-open). Searching is restricted to this window.
        max_edit_distance: 0 disables fuzzy matching. >0 allows OCR-drift
            recovery inside the window only.

    Raises:
        ValueError: empty quote, or invalid (start >= end) span.
    """
    if not quote:
        raise ValueError("quote must be non-empty")
    if char_start < 0 or char_end <= char_start:
        raise ValueError(
            f"invalid span window: char_start={char_start}, char_end={char_end}"
        )

    canon_quote = canonicalize_text(quote)
    window = page_text[char_start:char_end]
    canon_window = canonicalize_text(window)

    if canon_quote and canon_quote in canon_window:
        return MatchResult(
            matched=True,
            strategy=MatchStrategy.CANONICAL_EXACT,
            edit_distance=0,
        )

    if max_edit_distance > 0:
        distance = _best_window_distance(canon_quote, canon_window, max_edit_distance)
        if distance <= max_edit_distance:
            return MatchResult(
                matched=True,
                strategy=MatchStrategy.BOUNDED_FUZZY,
                edit_distance=distance,
            )

    return MatchResult(
        matched=False,
        strategy=MatchStrategy.NO_MATCH,
        edit_distance=-1,
    )
```

- [ ] **Step 4:** Run pytest. Expected: PASS (all span-match tests).

- [ ] **Step 5:** Commit:

```bash
git add packages/eval/auto_label/span_match.py packages/eval/tests/test_auto_label_span_match.py
git commit -m "feat(eval/auto_label): bounded-window quote span matcher"
```

---

## Phase 4 — `LabelerModelSpec` + dual-provider factory helper

**Cites:** sparring §2 (Codex finding [4]: explicit two-provider construction).

**Files:**
- Create: `packages/llm_orchestrator/clients/labeler_factory.py`
- Create: `packages/llm_orchestrator/tests/test_labeler_factory.py` (or extend existing test file if conventions match)

### Task 4.1 — Spec dataclass

- [ ] **Step 1 (test):** `LabelerModelSpec(provider, model, ...)` round-trips; rejects unknown providers; refuses `store=True` for OpenAI; api_version optional.
- [ ] **Step 2:** Implement `LabelerModelSpec` as a Pydantic `StrictBaseModel` (or frozen dataclass).
- [ ] **Step 3:** Test rejects unsupported provider strings explicitly (different code path from the existing role-based config).

### Task 4.2 — `build_labeler_client(spec)`

- [ ] **Step 1 (test):** Given an Anthropic spec, returns a `ClaudeClient` with the spec's model. Given an OpenAI spec, returns an `OpenAIClient` with `store=False` and the spec's model. Both clients implement `BaseLLMClient`.
- [ ] **Step 2 (test):** Two specs with different providers produce clients of different concrete types in one call sequence — pytest assertion that A vs B do not share an instance and have distinct providers.
- [ ] **Step 3:** Implement using existing `ClaudeClient` / `OpenAIClient` constructors. **Do not** call `get_llm_client(LLMRole.EXTRACTION)` — that's the bug Codex flagged.
- [ ] **Step 4 (integration):** Test that `OpenAIClient.generate_structured(...)` is callable with a strict-mode schema generated from a small Pydantic model via `_schema.strict_json_schema(...)`. (Use a stub HTTP layer or the existing test mocks if present.)

### Task 4.3 — Document and commit

- [ ] **Step 1:** Brief module docstring referencing sparring §2 and Codex finding [4].
- [ ] **Step 2:** Commit: `feat(orchestrator/clients): LabelerModelSpec + dual-provider factory helper for SHA-28 LLM labeling`

---

## Phase 5 — Field-path disagreement set

**Cites:** sparring §4.

**Files:**
- Create: `packages/eval/auto_label/disagreement.py`
- Create: `packages/eval/tests/test_auto_label_disagreement.py`

### Tasks
- [ ] **5.1:** Define `FieldPath` builder that produces stable identity strings:
  - `evidence[stable_key].kind` etc., where `stable_key` is `(kind, normalised_description_first_n)`.
  - `claimed_amounts[issue|by_party].amount_gbp` etc.
  - `ground_truth_outcome.per_issue[issue].winner` etc.
  - `cited_authorities[normalised_name|cited_date].cited_date` etc.
  - `statutory_basis[normalised_statute|section].section` etc.
  - **Tests:** identity stability across reordering; collision rejection when two list elements share the same key.
- [ ] **5.2:** `class PartialGoldCase` (or a typed dict) representing one labeling pass — same shape as `GoldCase` but with all fields optional.
- [ ] **5.3:** `build_disagreement_set(a: PartialGoldCase, b: PartialGoldCase, grounding: GroundingResult) -> DisagreementSet` returning the set of `(field_path, a_value, b_value, reason)` rows where reason ∈ `{"a_b_mismatch", "a_ungrounded", "b_ungrounded", "invariant_failed", "basis_span_missing", "null_xor"}`.
- [ ] **5.4:** Tests: scalar mismatch enters set; matched list elements with subfield mismatch enter set per-subfield; identity-key conflict enters as "list_identity_unresolved"; null-XOR rule.

---

## Phase 6 — Real-gold append gate

**Cites:** sparring §8.

**Files:**
- Create: `packages/eval/auto_label/append_gate.py`
- Create: `packages/eval/tests/test_auto_label_append_gate.py`

### Tasks
- [ ] **6.1 (test, then impl):** `assert_real_gold_appendable(gc: GoldCase, *, run_artifact_path: Path) -> None` raises `AppendGateError` when:
  - `labeling_provenance is None`
  - `negative_kind is not None`
  - `target_source_id is None`
  - any of the SHA-20 Phase 7 manifest fields (`domain_id`, `forum`, `retrieval_namespace_id`, `corpus_version`, `source_publisher`, `source_kind`, `source_license`) is None
  - the `MandatoryReviewSet` (computed from labeling_provenance.field_provenance) does not cover all entries in §1.MandatoryReviewSet of the sparring plan
  - `run_artifact_path` does not exist or its hash does not match `labeling_provenance.source_pdf_sha256` and `ocr_text_sha256`
- [ ] **6.2 (test):** Negative-set passing: with a synthetic case that has every gate failure listed, the test parameterises the failure mode and asserts the error message names the failing rule.

---

## Phase 7 — Facts leakage scanner

**Cites:** sparring §3 ("Facts leakage scan") + Codex finding [1].

**Files:**
- Create: `packages/eval/auto_label/leakage_scan.py`
- Create: `packages/eval/tests/test_auto_label_leakage_scan.py`

### Tasks
- [ ] **7.1 (test):** Tribunal-finding language detector — phrase list seeded with: "the tribunal finds", "we award", "we order", "we conclude", "the respondent is liable", "we determine", "judgment for the", "in our view", "we accept the [applicant|respondent]". Negative phrases ("the applicant submitted", "the respondent argued", "the parties agreed") MUST NOT trigger.
- [ ] **7.2 (test):** Span-section check — `facts` whose source spans fall outside `section_tag == "pre_decision_record"` are rejected.
- [ ] **7.3 (impl):** Pure function `scan_facts_for_leakage(facts: str, source_spans: list[Provenance], page_sections: dict[Provenance, str]) -> list[LeakageFinding]` returning empty on clean input, populated on rejection.
- [ ] **7.4 (test):** Round-trip with `tests/fixtures/gold_case_minimal.json`: fixture's facts string passes; an injected "the tribunal finds for the applicant" string fails.

---

## Phase 8 — Auto-grounder orchestration

**Cites:** sparring §3 (full table).

**Files:**
- Create: `packages/eval/auto_label/grounder.py`
- Create: `packages/eval/auto_label/lookups/__init__.py`, `statutes.py`, `authorities.py` (stubs behind a Protocol)
- Create: `packages/eval/tests/test_auto_label_grounder.py`

### Tasks (skeleton — expand once Phases 1–7 land)
- [ ] **8.1:** Define `GroundingProtocol` for authority + statute lookups; ship in-memory test stubs that return KNOWN/UNKNOWN/AMBIGUOUS.
- [ ] **8.2:** Per-field check functions: `check_quote`, `check_authority`, `check_statute`, `check_outcome_basis`, `check_label_basis`, `check_facts_leakage`, `check_date_sanity`, `check_amount_sanity`, `check_invariants`, `check_real_gold_audit`.
- [ ] **8.3:** Top-level `ground(case: PartialGoldCase, page_text: dict[int, str], spans: list[Provenance], stubs) -> GroundingResult` aggregating all checks and emitting `{field_path: GROUNDED|UNGROUNDED, reason}` plus a summary `grounding_pass_rate` float.
- [ ] **8.4:** `grounder_version = "1.0.0"` constant, used by `LabelingProvenance.grounder_version`.
- [ ] **8.5:** Tests: every per-field check has a positive + negative case; the orchestrator's pass rate matches a hand-counted fixture.

---

## Phase 9 — Labeler runner + run artifact writer

**Cites:** sparring §2 + §7.

**Files:**
- Create: `packages/eval/auto_label/runner.py`
- Create: `packages/eval/auto_label/prompts/__init__.py`, `extraction.py`
- Create: `packages/eval/tests/test_auto_label_runner.py`

### Tasks (skeleton)
- [ ] **9.1:** `class LabelingRun` capturing `run_id`, two `LabelerModelSpec`s, paths.
- [ ] **9.2:** Prompt template + `prompt_template_hash` (sha256 of the rendered template).
- [ ] **9.3:** `run_one_case(pdf_text, span_index, run, *, clients_by_spec) -> CasePass` invoking each labeler in parallel via threads or asyncio.
- [ ] **9.4:** Artifact writer: `data/eval_artifacts/labeling/<run_id>/<case_id>.json` with the schema described in sparring §7 (raw outputs, prompts after rendering, hashes, grounding decisions, final adjudicated label, MandatoryReviewSet status, anchor-set flag).
- [ ] **9.5:** Tests use stub `BaseLLMClient` instances that return canned `PartialGoldCase`-shaped JSON.

---

## Phase 10 — `scripts/eval/auto_label.py` CLI

**Cites:** sparring §5 (pre-adjudication phase).

### Tasks (skeleton)
- [ ] **10.1:** CLI signature `python -m scripts.eval.auto_label --case-id <id> --pdf <path> --domain-id <id> --run-id <id> --labeler-a <provider:model> --labeler-b <provider:model>`.
- [ ] **10.2:** End-to-end on a synthetic fixture, no real network call: emits the run artifact and a "pending adjudication" stub row.
- [ ] **10.3:** Refuses to write to `data/gold_standard/housing_v1.jsonl` directly — output goes to `data/eval_artifacts/labeling/<run_id>/`. Append happens only via `scripts/eval/adjudicate.py`.

---

## Phase 11 — `scripts/eval/adjudicate.py` CLI (replaces the annotate.py flow)

**Cites:** sparring §5.

### Tasks (skeleton)
- [ ] **11.1:** Walks MandatoryReviewSet for every real gold case, regardless of A/B agreement.
- [ ] **11.2:** Walks DisagreementSet next, showing both values + grounded PDF excerpt + grounding result.
- [ ] **11.3:** 10% deterministic random sample of agreed cells surfaced as "audit" rows. Records `audit_flip_rate` in `LabelingProvenance`.
- [ ] **11.4:** Final write goes through `assert_real_gold_appendable`, then appends to `data/gold_standard/housing_v1.jsonl`.
- [ ] **11.5:** Mirrors `scripts/eval/annotate.py` UX (the existing CLI is the closest reference).
- [ ] **11.6:** Reviewer log entries appended to `docs/eval/reviewer-log.md`.

---

## Phase 12 — Plan rewrite + decision log

**Files:**
- Modify: `.sisyphus/plans/track-a-plan.md`
- Create: `.sisyphus/notepads/llm-labeling/D-019-llm-assisted-labeling.md`
- Modify: `docs/eval/reviewer-guide.md` (adjudicator-only reframe)

### Tasks
- [ ] **12.1:** Rewrite Phase 3 row: drop "first 10 cases" with one paralegal, replace with "auto-label pipeline + first 10 cases adjudicated end-to-end".
- [ ] **12.2:** Rewrite Phase 6 row: drop "two reviewers, blind double annotation, Cohen's κ ≥ 0.8", replace with "MandatoryReviewSet completed for every row + 10% audit sample + 10–20-case human-only anchor set + split-metric reporting".
- [ ] **12.3:** Add new section "Annotation reliability under LLM-assisted labeling" to track-a-plan.md superseding the old SHA-96 section.
- [ ] **12.4:** Decision-log entry D-019 (or next available; check existing notepads): records the choice, the circularity counter-arguments, the divergence threshold for combined-metric reporting, and that `inter_model_agreement_rate` is NOT Cohen's kappa.
- [ ] **12.5:** Reviewer guide: rewrite the "single primary reviewer" section as "adjudicator walks DisagreementSet + MandatoryReviewSet". Drop kappa target. Note 10% audit overlay and human-only anchor set.

---

## Self-review checklist (run after the plan is committed)

- [ ] Every phase has a concrete file path
- [ ] Phase 1–3 have full code blocks (the foundational deterministic surface)
- [ ] Phase 4–7 have task lists tight enough for a subagent to execute
- [ ] Phase 8–11 are skeleton only; expand once Phases 1–7 land and reviewer feedback is in
- [ ] No placeholder `TODO` / `TBD` / "implement later" survives in Phase 1–3
- [ ] Type names used in later phases (`PartialGoldCase`, `GroundingResult`) appear at first definition

---

## Execution order

1. Phases 1, 2 in parallel (independent: schema vs canonicalizer).
2. Phase 3 after Phase 2 (span matcher depends on canonicalizer).
3. Phase 4 in parallel with Phases 1–3 (orchestrator-side, no eval deps).
4. Phases 5, 6, 7 after Phase 1 (need `LabelingProvenance` + new fields).
5. Phase 8 after Phases 2, 3, 5, 7 (auto-grounder consumes all deterministic surface).
6. Phase 9 after Phases 4, 5, 8 (runner needs labelers + grounder + DisagreementSet).
7. Phases 10, 11 after Phase 9.
8. Phase 12 last (plan rewrite reflects what actually shipped).
