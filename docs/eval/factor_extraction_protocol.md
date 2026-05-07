# Factor Extraction Protocol — `housing.repairs_social.v1`

**Status:** draft (design-only)
**Spec:** [`docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md`](../superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md) §19 PR 3a
**Catalog under protocol:** [`packages/domain_packs/housing/repairs_social/factors.yaml`](../../packages/domain_packs/housing/repairs_social/factors.yaml)
**Strategy declarations:** [`packages/domain_packs/housing/repairs_social/extractor_strategy.yaml`](../../packages/domain_packs/housing/repairs_social/extractor_strategy.yaml)
**Annotation rubric:** [`packages/domain_packs/housing/repairs_social/annotation_rubric.md`](../../packages/domain_packs/housing/repairs_social/annotation_rubric.md)

Design contract for producing `FactorAssertion` records (spec §4.1) from a `CaseFile`. Implementation-agnostic — concrete extractors and verifiers land in PR 3a / Stream C (`packages/legal_core/extractors/`). The §22.1 panel-review CLI ([`scripts/eval/factor_catalog_review.py`](../../scripts/eval/factor_catalog_review.py)) is a *catalog* tool, distinct from the runtime extractor; nothing here changes it.

---

## 1. Per-Factor Extraction Strategy Table

The table below mirrors `extractor_strategy.yaml`. The `extraction_method` column on `FactorAssertion` (spec §4.1) is set to the value in the `strategy` column at write-time. Per spec §4.1, `llm_extracted` (no verifier) is allowed for prototyping but is excluded from the graph-quality gate by default; this is reflected in the `gate_counted` column.

| factor_id | strategy | calculator_id | gate_counted | min_confidence | rationale (`# why:`) |
|---|---|---|---|---|---|
| `inspection_delay_days` | deterministic | `inspection_delay_calculator` | true | 1.0 | computed as (first_inspection_date − report_date).days; both dates are structured CaseFile fields |
| `repair_delay_days` | deterministic | `repair_delay_calculator` | true | 1.0 | computed as (repair_completion_date − notice_date).days; both dates are structured CaseFile fields |
| `complaint_response_delay_days` | deterministic | `complaint_response_delay_calculator` | true | 1.0 | computed as (landlord_response_date − formal_complaint_date).days; both dates are structured CaseFile fields |
| `communication_gap_days` | deterministic | `communication_gap_calculator` | true | 1.0 | computed as max gap between consecutive communication events in the structured timeline |
| `issue_outside_jurisdiction` | deterministic | `jurisdiction_check` | true | 1.0 | binary rule applied against a closed list of excluded complaint categories; no narrative needed |
| `hazard_or_disrepair_reported` | llm_verified | — | true | 0.5 | boolean presence in free-text report narrative; LLM extraction + verifier pass required for reliability |
| `landlord_notice_established` | llm_verified | — | true | 0.5 | provability of notice requires reading acknowledgement language; verifier guards against over-extraction |
| `inspection_offered` | llm_verified | — | true | 0.5 | offer vs. actual inspection distinction is subtle; verifier reduces conflation errors |
| `repair_attempted` | llm_verified | — | true | 0.5 | "attempted" vs. "completed" requires careful narrative reading; verifier improves precision |
| `temporary_decant_or_alternative_offered` | llm_verified | — | true | 0.5 | offer language is domain-specific and easily confused with completed decant; verifier required |
| `prior_compensation_or_apology_offered` | llm_verified | — | true | 0.5 | distinguishing goodwill gestures from formal compensation offers requires verifier confirmation |
| `vulnerability_known` | llm_verified | — | true | 0.5 | "should have known" inference is judgment-adjacent; verifier provides a second opinion on implicit signals |
| `records_inadequate` | llm_verified | — | true | 0.6 | gap identification in records is inherently interpretive; raised threshold + verifier reduces false positives |
| `repair_responsibility_established` | llm_verified | — | true | 0.6 | statutory vs. contractual basis requires legal-text reading; raised threshold guards against over-attribution |
| `impact_severity_reported` | llm_verified | — | true | 0.5 | resident-reported enum extracted from narrative; verifier reduces hallucinated severity escalation |

Five deterministic factors derive from structured `CaseFile` fields and never require LLM calls. The remaining ten run the full extract-then-verify pipeline. No factor is currently configured as bare `llm_extracted` — that mode exists for prototyping or for factors that fall below the gate threshold per spec §19 PR 3a acceptance ("No factor with F1 < 0.5 promoted to gate-counting").

---

## 2. LLM Extractor Architecture

### 2.1 Model and role

Default extractor: Claude Sonnet 4.6 via `LLMRole.PREDICTION` from [`packages/llm_orchestrator/clients/factory.py`](../../packages/llm_orchestrator/clients/factory.py). The existing `PREDICTION` role (rather than `EXTRACTION`) is chosen deliberately: factor extraction is judgment-adjacent and shares the calibration discipline of prediction. The cheaper `LLMRole.EXTRACTION` role remains available as a cost fallback (§7). Full provider/model identifiers are resolved at call time and recorded with the prompt hash (§6).

### 2.2 Prompt structure

One LLM call per factor per case (no multi-factor batching in v1; this is a deliberate cost-vs-isolation trade discussed in §7). Two-message structure:

- **System prompt** sets the extractor role, the catalog SHA, and the rubric for the *single* factor under extraction (id, value_type, polarity, abstention guidance lifted from `annotation_rubric.md`). It also includes the spec §4.1 guard that surface labels are domain-pack rendering concerns and must not appear in the value.
- **User prompt** provides the case narrative excerpt, the structured extraction schema (the Pydantic model in §2.3), and the determination-stripped narrative (using the same regex as [`scripts/eval/factor_catalog_review.py`](../../scripts/eval/factor_catalog_review.py); see §5.3).

### 2.3 Structured output schema

```python
class ExtractedFactor(BaseModel):
    factor_id: str
    value: FactorValue          # spec §4.1 typed carrier
    confidence: float           # 0..1
    source_span: str            # verbatim narrative quote supporting the value
    abstained: bool = False     # true ⇒ value is None and source_span is empty
    notes: str | None = None
```

`value` reuses `FactorValue` from spec §4.1 — exactly one typed field is populated, matching the catalog's `value_type`. `source_span` is a *verbatim* substring of the input narrative; the verifier in §3 enforces this with a string-membership check.

### 2.4 Retry policy

- **Attempt 1:** raw call.
- **Attempt 2:** retry on malformed JSON, missing required fields, or `value_type` mismatch. The retry prompt includes the prior response and the parse error verbatim.
- **Attempt 3+:** none. On second failure, write `requires_human_review = true` with `confidence = 0.0`, persist the raw responses for audit, and continue.

This caps worst-case extractor cost at 2× the nominal call count.

---

## 3. Verifier Architecture (for `llm_verified` factors)

The verifier is a separate LLM pass that re-grounds the extracted value in the source narrative. It exists because spec §4.1 explicitly forbids treating bare `llm_extracted` outputs as gate-counting evidence.

### 3.1 Different model family from the extractor

The verifier uses a *different model role and ideally a different model family* — current default is Claude Opus 4.7 via a dedicated verifier role (a new `LLMRole.VERIFIER` to be added in PR 3a, or `EXTRACTION` re-purposed in the interim). Same-model verification risks the "rubber-stamp" failure mode where the verifier inherits the extractor's blind spots; a different family makes the second opinion meaningful.

### 3.2 Verifier checks

For each `ExtractedFactor` with strategy `llm_verified`, the verifier:

1. **Span membership.** Confirms `source_span` appears as a substring of the original narrative (string match after normalising whitespace). If not found → automatic disagreement.
2. **Value-span consistency.** Independently judges whether the quoted span supports the extracted value (boolean, enum, numeric, etc.). The verifier does not see the extractor's `confidence` so its judgement is not anchored.
3. **Verifier confidence.** Emits `verifier_confidence ∈ [0, 1]`.

### 3.3 Disagreement handling

If the verifier disagrees (different value, quote not found, or `verifier_confidence < min_confidence_threshold`), the `FactorAssertion` is written with `requires_human_review = true` and excluded from `evidence_backed_factor_count` for the §8 gate. Both raw responses and confidences are preserved — abstention without an audit trail is not acceptable. `extraction_method` stays `llm_verified` either way (the audit must show the verifier ran); the `requires_human_review` flag carries the disagreement signal.

---

## 4. Abstention Rule

The abstention rule is the same regardless of strategy:

- If the extractor sets `abstained = true`, **or** `confidence < min_confidence_threshold` (per `extractor_strategy.yaml`), **or** the verifier disagrees (§3.3) → `requires_human_review = true`.
- A `requires_human_review = true` factor is **persisted** in the artifact (so reviewers can audit and override) but is **not counted** in `evidence_backed_factor_count` for graph-quality-gate purposes (spec §8).
- Deterministic factors cannot abstain unless an upstream date or flag is missing; in that case the calculator returns `None` and the factor is omitted from the artifact (rather than being marked human-review).

This is consistent with the spec §1 non-negotiable that the system prefers conservative abstention to overconfident extraction, and it preserves the cite-or-abstain discipline articulated in `CLAUDE.md` for the prediction layer downstream.

---

## 5. Gold Protocol (per spec §19 PR 3a)

### 5.1 Sample

30 cases, double-annotated. The 30 are drawn from the existing housing-ombudsman pool with seed pinned (see §6) and stratified to roughly mirror the determination distribution used elsewhere in the eval harness.

### 5.2 Inter-annotator agreement target

Krippendorff's α ≥ 0.7 *per factor*. Factors that fall below are flagged in the per-factor F1 report; per spec §19 PR 3a acceptance, no factor with F1 < 0.5 is promoted to gate-counting (it remains in the catalog but its `gate_counted` flips to `false` until the rubric and prompt are tightened).

### 5.3 Determination stripping

Annotators (LLM or human) see the **narrative only** — never the determination paragraph. The stripping uses the same regex as [`scripts/eval/factor_catalog_review.py`](../../scripts/eval/factor_catalog_review.py) so that labelled inputs match what the production extractor will see. This enforces the spec §12 / §22.1 leakage rule that every factor must be labelable from narrative alone.

### 5.4 Different model families per annotator

When the two annotators are LLM-based, they MUST use different model families (e.g., Claude Sonnet 4.6 + GPT-4-class). Same-family double annotation produces inflated agreement that does not generalise to the production pipeline. Human gold-standard annotation by a paralegal remains the long-term ideal; LLM panel annotation is the thesis-pace substitute (per spec §22.1).

---

## 6. Reproducibility

Every extraction artifact MUST record:

- **Random seed** for case selection (single integer, pinned per run).
- **Full model identifiers** for the extractor and verifier — provider plus exact version string (e.g., `anthropic/claude-sonnet-4-6-20260301`), not just a family name. This is essential for the temporal-shift discipline in `CLAUDE.md`: a re-run on a new model checkpoint is a different experiment.
- **Prompt hashes:** SHA256 of the system prompt and user prompt template (separately). Hashes change ⇒ the run is not directly comparable to prior runs.
- **Catalog SHA:** SHA256 of the `factors.yaml` and `extractor_strategy.yaml` files at extraction time, so that every `FactorAssertion` can be linked back to the exact catalog version that produced it.
- **Library versions** for the Pydantic models used to parse the structured output (any schema drift invalidates older artifacts).

These fields ride alongside the existing `extractor_version` / `verifier_version` strings on `FactorAssertion` (spec §4.1).

---

## 7. Cost-Budget Note

Per spec §19 cost budget for the housing pack:

```
~500 corpus decisions × ~15 factors per case
  − 5 deterministic (zero LLM cost)
  + 10 llm_verified × (1 extract + 1 verify call)
  ≈ 10,000 LLM calls per full corpus rebuild
```

At Sonnet 4.5/4.6 pricing (~£0.005–0.015 per typical-case call) → **~£60–180 per full housing.repairs_social rebuild** (Sonnet on both passes; Opus on the verifier pushes higher). Reserve **~£250–500 per rebuild × 3–5 rebuilds = ~£1,000–3,500** across PR 3a iteration, separate from prediction-time eval cost.

**Cost fallback** (spec §19): GPT-4o-mini for extraction, Sonnet retained for verification — roughly ⅕ the cost at a modest accuracy hit. This is a knob, not a default; gold-protocol F1 numbers must be re-measured under the fallback before it ships, since changing the extractor model invalidates the agreement statistics from §5.

---

## Cross-References

- Spec §1, §4.1, §8, §12, §17.1, §19 PR 3a, §22.1.
- [`factors.yaml`](../../packages/domain_packs/housing/repairs_social/factors.yaml), [`extractor_strategy.yaml`](../../packages/domain_packs/housing/repairs_social/extractor_strategy.yaml), [`annotation_rubric.md`](../../packages/domain_packs/housing/repairs_social/annotation_rubric.md).
- [`packages/llm_orchestrator/clients/factory.py`](../../packages/llm_orchestrator/clients/factory.py) — `LLMRole` factory used for both passes.
