# Stream C Recovery Sprint Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pivot Stream C from "did our hybrid beat RAG-only on raw accuracy" (which today reads no, by 21pp) to a multi-axis evaluation where the prediction system *always answers*, the validator audits rather than vetoes, and Stream C is judged on accuracy + calibration + auditability + counterfactual robustness.

**Operating principle:** No final `UNCERTAIN`. Every case gets a measurable prediction. The validator records evidence-support metadata; the assembler caps confidence on failed chains; downstream eval slices on `kg_used_for_prediction` and `evidence_path_supported`.

**Why:** Today's 48-case ablation found `rag_only` at 83.3% vs `hybrid` at 62.5%. The new architecture's factor-constrained retrieval and evidence-path validator gracefully fall back to chunk-RAG when factor data is empty (design decision D5). Combined with `STREAM_C_EVIDENCE_PATH_STRICT=1` and `kg_only`/`llm_only` modes treating UNCERTAIN as a final label, the headline numbers under-represent system capability and the abstention rates (kg_only 67%, llm_only 65%) make raw-accuracy comparison meaningless. The recovery plan fixes both.

**Tech Stack:** existing — Python 3.11+, Pydantic v2, pytest, asyncio. No new dependencies. Reuses everything Stream C already shipped.

**Spec reference:** [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](../specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md). Stream C plan: [`2026-05-07-stream-c-prediction-path-swap.md`](2026-05-07-stream-c-prediction-path-swap.md). Today's ablation report: [`docs/eval/stream-c-ablation-2026-05-07.md`](../../eval/stream-c-ablation-2026-05-07.md). Supervisor briefing: [`docs/eval/stream-c-supervisor-briefing-2026-05-07.md`](../../eval/stream-c-supervisor-briefing-2026-05-07.md).

---

## New Evaluation Axes (replaces "hybrid > rag_only on accuracy")

| Axis | Why it matters |
|---|---|
| Accuracy / macro F1 / balanced accuracy | Does it predict the right outcome? |
| Calibration (ECE, Brier) | Does confidence mean anything? |
| Citation validity / evidence support rate | Are claims grounded? |
| Counterfactual factor sensitivity | Does flipping legally relevant factors change the outcome appropriately? |
| Graph gate-pass rate / `kg_used_for_prediction` | Was the hybrid actually using the KG, or pretending? |

**New target:** "Hybrid should either beat RAG-only on accuracy, OR match it while improving calibration, auditability, and counterfactual robustness." Multi-axis success criterion.

---

## Hard Constraints

1. **No final `UNCERTAIN`.** When `STREAM_C_FORCE_ANSWER=1` (new flag, default on after Task 4), every prediction's `outcome` must be one of `tenant_wins`, `landlord_wins`, `split`. Validator-rejected chains get `confidence` capped at 0.60 and structured failure metadata, not an outcome flip.
2. **Empty factor cards never reach the prompt.** When `STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1` (new, default on), an empty `kg_fact_card` causes the `{kg_fact_card}` placeholder section to be stripped from the IRAC prompt entirely.
3. **Validator is audit-only by default.** `STREAM_C_EVIDENCE_PATH_STRICT=0` stays default. Strict mode is opt-in for stratified analysis, not for production headlines.
4. **Metadata serialisation is regression-tested.** Commit `6917d32` patched `_serialise_prediction` to carry `pipeline_metadata`. Add a test that asserts the full §17.6 schema is present on every artifact row.
5. **No real LLM calls in unit tests.** Continue the existing fakes pattern.
6. **PageRank stays optional** (existing Hard Constraint #11 from Stream C).
7. **All existing 1,580 unit tests must still pass.** No regressions on byte-equivalence, gate logic, or schema fields.

---

## File Structure

### New files
- `packages/llm_orchestrator/tests/test_force_answer_mode.py` — forced-answer behaviour tests
- `packages/llm_orchestrator/tests/test_empty_factor_card_suppression.py` — empty-card suppression tests
- `packages/llm_orchestrator/tests/test_validator_audit_only.py` — validator-no-veto tests
- `data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/` — one-case positive-control fixture (Task 7)
- `docs/eval/stream-c-pr4-off-diagnostic-2026-05-07.md` — PR4=0 diagnostic note (Task 1 result)
- `docs/eval/stream-c-recovery-ablation-2026-05-07.md` — forced-answer ablation report (Task 6 result)

### Modified files
- `packages/llm_orchestrator/pipeline/issue_predictor.py` — empty-card suppression hook + forced-answer prompt + confidence-cap on failed chain
- `packages/llm_orchestrator/prompts/prediction_v2.py` — IRAC_USER_PROMPT becomes a function that strips empty placeholders + IRAC_JSON_SCHEMA gains forced-answer language
- `packages/llm_orchestrator/pipeline/output_assembler.py` — confidence cap when validator rejects chain (audit-only path) + forced-answer post-process for any final-UNCERTAIN that slips through
- `packages/llm_orchestrator/models/prediction_v2.py` — possibly add `evidence_support` and `unsupported_claim_count` fields to `PipelineMetadata`
- `docs/eval/stream-c-supervisor-briefing-2026-05-07.md` — append recovery-plan results

---

## Build Sequence

```
Task 1 (DIAGNOSTIC, parallel)       Task 2-5 (PATCHES, sequential)
   │                                   │
   ├── PR4=0 hybrid ablation, 48 cases ├── Task 2: empty-card suppression
   │   ~£2, ~10 min wall               ├── Task 3: validator audit-only + confidence cap
   │                                   ├── Task 4: forced-answer mode
   │                                   └── Task 5: tests
   │                                   │
   └── ANALYSIS (Task 1B)              │
                                       │
                              JOIN: Task 6 (forced-answer ablation, 48 cases)
                                                              │
                                                              │
                              Task 7 (positive-control fixture, parallel from start)
                                                              │
                                                              │
                              Task 8: update supervisor briefing
```

Tasks 1 + 7 can run from the start (independent). Tasks 2-5 sequential on the codebase. Task 6 needs both 1 and 5. Task 8 closes out.

---

## Task 1 — STREAM_C_PR4=0 Diagnostic Ablation (CHEAP, IMMEDIATE)

**Files:**
- Out: `eval/predictions/stream_c_pr4_off_diag_2026_05_07/`
- Out: `eval/results/stream_c_pr4_off_diag_2026_05_07/`
- Out: `docs/eval/stream-c-pr4-off-diagnostic-2026-05-07.md`

**Why:** if removing the pack-rendered factor card closes the 21pp hybrid-vs-rag_only gap, the empty card was the smoking gun. ~£2.

- [ ] **Step 1 — Launch 8 parallel workers, hybrid mode only**

```bash
mkdir -p eval/predictions/stream_c_pr4_off_diag_2026_05_07_chunked
for i in 0 1 2 3 4 5 6 7; do
  mkdir -p "eval/predictions/stream_c_pr4_off_diag_2026_05_07_chunked/chunk_$i"
  STREAM_C_PR4=0 STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_EVIDENCE_PATH_STRICT=1 \
    ./venv/bin/python -m scripts.eval.predict_all \
    --gold "/tmp/stream_c_chunks/chunk_$i.jsonl" \
    --out-dir "eval/predictions/stream_c_pr4_off_diag_2026_05_07_chunked/chunk_$i" \
    --engine live --client claude --modes hybrid --top-k 10 \
    > "/tmp/stream_c_pr4_off_chunk_$i.log" 2>&1 &
done
```

- [ ] **Step 2 — Merge chunks**

```bash
mkdir -p eval/predictions/stream_c_pr4_off_diag_2026_05_07
cat eval/predictions/stream_c_pr4_off_diag_2026_05_07_chunked/chunk_*/hybrid.jsonl \
  > eval/predictions/stream_c_pr4_off_diag_2026_05_07/hybrid.jsonl
```

- [ ] **Step 3 — Run analysis**

```bash
PYTHONPATH=packages ./venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --predictions-dir eval/predictions/stream_c_pr4_off_diag_2026_05_07 \
  --out-dir eval/results/stream_c_pr4_off_diag_2026_05_07 \
  --modes hybrid
```

- [ ] **Step 4 — Diagnostic note**

Write `docs/eval/stream-c-pr4-off-diagnostic-2026-05-07.md` with:
- accuracy + 95% CI for `hybrid` (PR4=0) vs `hybrid` (PR4=1, baseline) vs `rag_only`
- prompt-diff between PR4=0 and PR4=1 hybrid
- decision: did the empty card cause the gap?

### Decision rule

| Result | Interpretation | Action for Task 2 |
|---|---|---|
| Hybrid (PR4=0) jumps to ~80% | Empty card caused most of the damage | Suppress empty cards permanently (default-on) |
| Hybrid (PR4=0) stays ~62% | Something else differs | Diff retrieval payloads + validator routing before patching |
| Partial improvement (~70%) | Empty card is one cause, not the only one | Suppress card AND inspect remaining differences |

---

## Task 2 — Suppress Empty Factor Cards

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py` — wrap the `kg_fact_card` insertion so an empty card strips the placeholder section
- Modify: `packages/llm_orchestrator/prompts/prediction_v2.py` — IRAC_USER_PROMPT can keep the `{kg_fact_card}` placeholder; the predictor strips/replaces before format
- Create: `packages/llm_orchestrator/tests/test_empty_factor_card_suppression.py`

**Behaviour:**
- New env flag `STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD` (default `"1"`)
- When set and `kg_fact_card == ""`, the predictor sets `kg_fact_card = ""` (no change) AND additionally strips any orphan blank lines around the placeholder. Cleanest implementation: replace `{kg_fact_card}\n` with empty string in the formatted prompt when the card is empty.
- When the card is non-empty, behaviour is unchanged.

- [ ] **Step 1 — Failing test**

`packages/llm_orchestrator/tests/test_empty_factor_card_suppression.py`:

```python
"""Tests for STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD behaviour."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock

from llm_orchestrator.prompts.prediction_v2 import IRAC_USER_PROMPT


def test_irac_prompt_with_empty_kg_fact_card_has_no_orphan_section(monkeypatch):
    """When STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1 and kg_fact_card is empty,
    the formatted prompt must not contain consecutive blank lines where the
    KG card would have been."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    # Use the helper from issue_predictor that does the suppression.
    from llm_orchestrator.pipeline.issue_predictor import _suppress_empty_factor_card
    raw = IRAC_USER_PROMPT.format(
        issue_type="repairs_disrepair", issue_description="x",
        deposit_amount="0", claimed_amount="0",
        tenancy_duration="6m", tenancy_type="ast", region="london",
        data_completeness=0.5,
        deposit_protection_summary="", tenant_claim="", landlord_claim="",
        evidence_conflicts="", kg_constraints="",
        kg_fact_card="",
        abstention_warning="",
        evidence_summary="", timeline_summary="",
        num_retrieved_cases=0, retrieved_cases="",
    )
    cleaned = _suppress_empty_factor_card(raw)
    # No three consecutive blank lines around where the card was
    assert "\n\n\n" not in cleaned
    # Headers still present
    assert "KEY FACTS FROM CASE ANALYSIS:" in cleaned
    assert "EVIDENCE AVAILABLE:" in cleaned


def test_non_empty_kg_card_passes_through(monkeypatch):
    """When the card has content, the suppressor leaves it alone."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1")
    from llm_orchestrator.pipeline.issue_predictor import _suppress_empty_factor_card
    sample = "...\nKEY KG FACTS (typed):\n- foo\n...\n"
    assert _suppress_empty_factor_card(sample) == sample


def test_suppression_disabled_when_flag_zero(monkeypatch):
    """STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=0 keeps blank lines (legacy)."""
    monkeypatch.setenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "0")
    from llm_orchestrator.pipeline.issue_predictor import _suppress_empty_factor_card
    raw = "KEY FACTS FROM CASE ANALYSIS:\nfoo\n\n\nEVIDENCE AVAILABLE:\n"
    assert _suppress_empty_factor_card(raw) == raw
```

- [ ] **Step 2 — Run, expect failure** — `_suppress_empty_factor_card` doesn't exist yet.

- [ ] **Step 3 — Implement `_suppress_empty_factor_card`** in `issue_predictor.py` as a module-level helper (or static method on IssuePredictor). Logic:

```python
def _suppress_empty_factor_card(prompt: str) -> str:
    """Strip orphan blank lines that appear when {kg_fact_card} or
    {abstention_warning} resolved to empty string.

    Per Stream C recovery plan Task 2: empty KG sections damage the LLM's
    interpretation of the prompt. When the suppression flag is set (default
    on), collapse runs of 3+ newlines to 2.
    """
    if os.getenv("STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD", "1") != "1":
        return prompt
    # Collapse 3+ consecutive newlines down to 2 (paragraph break).
    while "\n\n\n" in prompt:
        prompt = prompt.replace("\n\n\n", "\n\n")
    return prompt
```

- [ ] **Step 4 — Apply at every prompt-format site** in issue_predictor. Find the `IRAC_USER_PROMPT.format(...)` calls (3 sites: lines ~272, ~340, ~628) and `_format_repairs_user_prompt` (line ~1046+) and wrap the resulting string with `_suppress_empty_factor_card(...)` before sending to the LLM.

- [ ] **Step 5 — Run tests, expect pass**

```bash
./venv/bin/pytest packages/llm_orchestrator/tests/test_empty_factor_card_suppression.py -v
./venv/bin/pytest packages/llm_orchestrator/tests/test_kg_in_prompt_golden.py -v  # regression
./venv/bin/pytest packages/llm_orchestrator/tests/test_kg_fact_card.py -v
```

- [ ] **Step 6 — Commit**

```
feat(issue_predictor): suppress empty factor card sections (recovery T2)

Strip 3+ consecutive newlines from the IRAC prompt when {kg_fact_card}
or {abstention_warning} resolved to empty. Default on via
STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1.

Empty KG sections appear to confuse the LLM (33% abstention vs 12.5%
in rag_only on the 2026-05-07 ablation). Collapsing the orphan
whitespace makes the empty-KG case behaviourally closer to rag_only.

Refs Stream C recovery plan Task 2.
```

---

## Task 3 — Validator Audit-Only by Default + Confidence Cap

**Files:**
- Modify: `packages/llm_orchestrator/pipeline/output_assembler.py` — convert validator from veto to audit; cap confidence on rejected chain
- Modify: `packages/llm_orchestrator/models/prediction_v2.py` — add `evidence_support: Optional[str] = None` and `unsupported_claim_count: int = 0` to `PipelineMetadata`
- Modify: `packages/llm_orchestrator/pipeline/evidence_path_validator.py` — emit richer rejection metadata
- Create: `packages/llm_orchestrator/tests/test_validator_audit_only.py`

**Behaviour:**
- `STREAM_C_EVIDENCE_PATH_STRICT` stays default `"0"` (audit only). When `"1"`, the validator marks `unsupported_claims` but DOES NOT force outcome to UNCERTAIN — instead caps `raw_confidence` at 0.60 and sets `evidence_support = "weak"`.
- Audit mode: same metadata emission, no confidence change.

- [ ] **Step 1 — Failing test** in `test_validator_audit_only.py`

```python
@pytest.mark.asyncio
async def test_strict_mode_does_not_force_uncertain_outcome():
    """Even with STREAM_C_EVIDENCE_PATH_STRICT=1 + a failed evidence path,
    the prediction's outcome stays as the LLM produced it. Only
    raw_confidence is capped and evidence_support metadata is set."""
    # Build a PredictionResult with outcome=tenant_wins, raw_confidence=0.85
    # Validator rejects all OutcomeComponents
    # After assemble(): outcome stays tenant_wins, raw_confidence <= 0.60
    # pipeline_metadata.evidence_support == "weak"
    # pipeline_metadata.unsupported_claim_count > 0


def test_audit_mode_does_not_change_confidence():
    # STREAM_C_EVIDENCE_PATH_STRICT=0
    # Validator rejects, but raw_confidence unchanged
    # evidence_support is still "weak" so eval can slice on it
    # outcome unchanged
```

- [ ] **Step 2 — Implement** in `output_assembler.py`:

```python
strict = os.getenv("STREAM_C_EVIDENCE_PATH_STRICT", "0") == "1"
unsupported = [r for r in evidence_path_results if not r.is_supported]

if unsupported:
    # Always record the metadata (audit + strict).
    pipeline_metadata.unsupported_claim_count = len(unsupported)
    pipeline_metadata.evidence_support = "weak"
    if strict:
        # Cap confidence; do NOT change outcome.
        for issue_pred in issue_predictions:
            if issue_pred.raw_confidence > 0.60:
                issue_pred.raw_confidence = 0.60
elif evidence_path_results:
    pipeline_metadata.evidence_support = "strong"
```

- [ ] **Step 3 — Add `evidence_support` + `unsupported_claim_count` to `PipelineMetadata`**

- [ ] **Step 4 — Tests pass + regression**

- [ ] **Step 5 — Commit**

```
feat(output_assembler): validator becomes audit-only; confidence cap on chain failure (recovery T3)

EvidencePathValidator no longer flips outcome=UNCERTAIN under strict mode.
Instead caps raw_confidence at 0.60 and emits evidence_support="weak" +
unsupported_claim_count metadata. Audit mode (default) emits the same
metadata without changing confidence.

Refs Stream C recovery plan Task 3.
```

---

## Task 4 — Forced-Answer Mode

**Files:**
- Modify: `packages/llm_orchestrator/prompts/prediction_v2.py` — IRAC_JSON_SCHEMA when `STREAM_C_FORCE_ANSWER=1` removes `"uncertain"` from allowed outcomes + adds explicit instruction
- Modify: `packages/llm_orchestrator/pipeline/issue_predictor.py` — post-process LLM response to force a non-UNCERTAIN label when the flag is on
- Create: `packages/llm_orchestrator/tests/test_force_answer_mode.py`

**Behaviour:**
- New env flag `STREAM_C_FORCE_ANSWER` (default `"1"`)
- When set, IRAC schema text emitted to the LLM has `"outcome" MUST be exactly one of: "tenant_wins", "landlord_wins", "split"` (no `"uncertain"`)
- Schema text adds: "You must choose exactly one outcome label. Do not answer uncertain. If evidence is weak, choose the most likely outcome and report uncertainty in confidence + evidence_strength fields."
- Post-process: if LLM still returns `outcome="uncertain"`, the predictor maps it to `"split"` (the no-information default) with `raw_confidence` capped at 0.50 and `evidence_strength = "insufficient"`.

- [ ] **Step 1 — Failing test**

```python
@pytest.mark.asyncio
async def test_force_answer_never_returns_uncertain(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    # LLM returns outcome="uncertain"; predictor remaps to split with conf<=0.5
    # Verify final IssuePrediction.outcome != IssueOutcome.UNCERTAIN


def test_force_answer_prompt_excludes_uncertain_from_schema(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "1")
    from llm_orchestrator.prompts.prediction_v2 import build_irac_json_schema
    schema_text = build_irac_json_schema()
    # The "outcome MUST be exactly one of" line must not include uncertain
    assert "uncertain" not in schema_text.lower() or "do not answer uncertain" in schema_text.lower()


def test_force_answer_disabled_keeps_uncertain_allowed(monkeypatch):
    monkeypatch.setenv("STREAM_C_FORCE_ANSWER", "0")
    from llm_orchestrator.prompts.prediction_v2 import build_irac_json_schema
    schema_text = build_irac_json_schema()
    assert "uncertain" in schema_text.lower()
```

- [ ] **Step 2 — Convert IRAC_JSON_SCHEMA into a function** `build_irac_json_schema()` that reads the flag and emits the appropriate schema text.

- [ ] **Step 3 — Add post-process in `issue_predictor.py`** after the LLM call:

```python
if os.getenv("STREAM_C_FORCE_ANSWER", "1") == "1":
    if response.outcome == IssueOutcome.UNCERTAIN:
        response.outcome = IssueOutcome.SPLIT
        response.raw_confidence = min(response.raw_confidence, 0.50)
        response.evidence_strength = EvidenceStrength.INSUFFICIENT
        response.reasoning = (
            "[forced-answer fallback: LLM returned uncertain] "
            + (response.reasoning or "")
        )
```

- [ ] **Step 4 — Tests pass + regression**

- [ ] **Step 5 — Commit**

```
feat(issue_predictor): forced-answer mode (recovery T4)

STREAM_C_FORCE_ANSWER=1 (default) removes "uncertain" from the IRAC
schema's allowed outcomes and post-processes any LLM response that
still returns uncertain into split + confidence cap at 0.50 +
evidence_strength=insufficient.

Eliminates the UNCERTAIN-as-final-label pathology that pushed kg_only
abstention to 67% in the 2026-05-07 ablation. Every case now produces a
gold-comparable label; uncertainty is reported separately via
confidence + evidence_support metadata.

Refs Stream C recovery plan Task 4.
```

---

## Task 5 — Recovery-Sprint Tests Bundle

**File:** `packages/llm_orchestrator/tests/test_pipeline_metadata_serialises.py` (new)

Add tests that lock in the metadata-serialisation fix from commit `6917d32`:

- [ ] `test_predict_all_artifact_includes_pipeline_metadata` — calls the engine end-to-end with mocks, asserts the artifact JSONL row has `pipeline_metadata` as a non-empty dict with all expected keys
- [ ] `test_pipeline_metadata_includes_kg_used_for_prediction` — explicit assertion
- [ ] `test_pipeline_metadata_includes_evidence_support` — gets set to `"strong"` / `"weak"` / `None` per validator outcome
- [ ] `test_force_answer_metadata_records_forced_split` — when forced-answer remaps uncertain to split, metadata records it

This is the safety net so future ablation runs don't silently regress.

---

## Task 6 — Forced-Answer Re-Ablation (48 cases)

**Files:**
- Out: `eval/predictions/stream_c_recovery_2026_05_07/`
- Out: `eval/results/stream_c_recovery_2026_05_07/`
- Out: `docs/eval/stream-c-recovery-ablation-2026-05-07.md`

Run after Tasks 2–5 land.

- [ ] **Step 1 — 8 parallel workers, all 4 modes, all flags on**

```bash
mkdir -p eval/predictions/stream_c_recovery_2026_05_07_chunked
for i in 0 1 2 3 4 5 6 7; do
  mkdir -p "eval/predictions/stream_c_recovery_2026_05_07_chunked/chunk_$i"
  STREAM_C_PR4=1 \
  STREAM_C_FACTOR_RETRIEVAL=1 \
  STREAM_C_EVIDENCE_PATH_STRICT=0 \
  STREAM_C_FORCE_ANSWER=1 \
  STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1 \
    ./venv/bin/python -m scripts.eval.predict_all \
    --gold "/tmp/stream_c_chunks/chunk_$i.jsonl" \
    --out-dir "eval/predictions/stream_c_recovery_2026_05_07_chunked/chunk_$i" \
    --engine live --client claude \
    --modes hybrid,rag_only,kg_only,llm_only --top-k 10 \
    > "/tmp/stream_c_recovery_chunk_$i.log" 2>&1 &
done
```

- [ ] **Step 2 — Merge + run analysis** (same pattern as Task 1)

- [ ] **Step 3 — Recovery report** at `docs/eval/stream-c-recovery-ablation-2026-05-07.md` with:
  - Multi-axis table: accuracy, macro F1, balanced acc, ECE, Brier, citation validity, evidence support rate, unsupported claim rate, kg_used rate
  - Confusion matrices per mode
  - Per-class precision/recall (ground_truth_outcome)
  - **No headline abstention rate** — every mode forced to answer

### Decision rule

| Result | Meaning | Action |
|---|---|---|
| `hybrid` accuracy ≈ `rag_only` (within CI overlap) | Empty-KG fix worked; fallback parity achieved | Proceed to Task 7 (positive control) |
| `hybrid` still much worse | Fallback/prompt/routing still differs | Debug retrieval payload diff before backfill |
| ECE improves under confidence-cap | Evidence-aware calibration is promising | Document as multi-axis win |
| `kg_only` still poor with metadata showing `kg_used_for_prediction=False` | Expected — no factor data | Validates the negative result framing |

---

## Task 7 — One-Case Positive-Control KG Fixture

**Files:**
- Create: `data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/`
  - `case.json` — one CaseFile with synthetic but realistic facts
  - `factor_assertions.json` — manually populated FactorAssertion[]
  - `evidence_spans.json` — backing EvidenceSpan[]
  - `propositions.json` — sample propositions with factor_ids populated
  - `expected_outcome.json` — gold label for the synthetic case
- Create: `packages/llm_orchestrator/tests/test_positive_control_kg_smoke.py`

**Goal:** prove FactorRetriever can return a non-empty ComparatorPack and EvidencePathValidator can close at least one chain when the data is real.

- [ ] **Step 1 — Build the one-case KG by hand**

Pick a clean repairs_social fact pattern (e.g., damp/mould reported, inspection delayed, tenant vulnerable). Populate:
- 5–8 `FactorAssertion`s with `extraction_method=MANUAL_GOLD`, evidence backlinks, polarity
- 3–4 `EvidenceSpan`s
- 5–10 `Proposition`s with `factor_ids` populated, drawn from the existing corpus or synthesised

- [ ] **Step 2 — Smoke test**

```python
@pytest.mark.asyncio
async def test_positive_control_factor_retriever_returns_nonempty_pack():
    """Load the one-case fixture; FactorRetriever must return a
    ComparatorPack with at least one comparator."""
    # Construct FactorRetriever with the manually-built repository
    # Build RetrievalControlInput from the fixture's case_file + factor_assertions
    # pack_result = await retriever.build_comparator_pack(...)
    # assert len(pack_result.comparators) >= 1
    # assert pack_result.comparator_pass_metadata.fallback_reason is None


@pytest.mark.asyncio
async def test_positive_control_evidence_path_closes():
    """Same fixture; EvidencePathValidator returns is_supported=True for
    at least one OutcomeComponent."""
    # Construct OutcomeComponent referencing the fixture's factors
    # validator = EvidencePathValidator(case_graph=fixture.case_graph)
    # result = validator.validate_outcome_component(oc)
    # assert result.is_supported is True
    # assert len(result.chain) == 4  # EvidenceSpan → FA → Prop → OC


@pytest.mark.asyncio
async def test_positive_control_engine_e2e_metadata_shows_kg_used():
    """End-to-end through PredictionEngineV2.predict() with
    STREAM_C_FACTOR_RETRIEVAL=1; final artifact metadata records
    kg_used_for_prediction=True and retrieval_strategy=factor_constrained."""
```

- [ ] **Step 3 — Run; commit fixture + tests**

This is the smoke test that determines whether full backfill is worth doing. If the fixture path lights up the KG correctly, backfill is justified. If even a hand-built fixture can't make the path activate, the architecture has a wiring bug.

---

## Task 8 — Update Supervisor Briefing

**File:** `docs/eval/stream-c-supervisor-briefing-2026-05-07.md` — append a new section "Recovery sprint results" at the bottom.

Sections to add:
- PR4=0 diagnostic finding (Task 1B)
- Patches landed (T2-T5) with feature-flag inventory update
- Forced-answer ablation results (Task 6) — multi-axis table
- Positive-control fixture outcome (Task 7) — does the KG path light up?
- Updated thesis framing per the new evaluation axes
- Decision matrix for whether to proceed with full data backfill

---

## Decision Gates (do not skip)

### Gate 1 — Empty-card diagnosis (after Task 1)
- Q: Does removing PR4/factor card close the hybrid-vs-RAG gap?
- Yes → suppress empty cards permanently (Task 2 default-on) ✓
- No → debug other differences before patching anything else

### Gate 2 — Forced-answer fallback parity (after Task 6)
- Q: With no KG data, does `hybrid` ≈ `rag_only` after the patches?
- Yes → fallback is safe; proceed to positive control
- No → still contaminating; debug retrieval payload diff

### Gate 3 — KG positive-control (after Task 7)
- Q: Can one hand-built KG case produce non-empty factor retrieval and supported evidence paths?
- Yes → backfill is worth pursuing in a follow-up plan
- No → wiring bug — do not spend on backfill yet

### Gate 4 — Multi-axis hybrid signal (after Task 6 with confidence cap + audit metadata)
- Q: Does hybrid match rag_only on accuracy AND improve at least one of: ECE, citation validity, evidence support rate?
- Yes → multi-axis win, defensible thesis claim
- No → frame as "graph-augmentation prerequisites" study

---

## Self-Review (before declaring sprint done)

- All 4 patches landed (Tasks 2–5)
- Pre-existing 1,580 unit tests still pass
- New tests added: forced-answer (3+), empty-card suppression (3), validator audit-only (2+), metadata serialisation (4)
- 2 ablations completed: PR4=0 diagnostic + forced-answer
- 1 positive-control fixture committed with passing smoke test
- Supervisor briefing updated
- Branch pushed to `codex/stream-c-prediction-path-plan`
- No final UNCERTAIN labels in any forced-answer prediction
- Every artifact carries the full §17.6 schema
