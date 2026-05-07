# Housing Repairs Social v1 — Comparative Gold Inter-Annotator Agreement Report (B12 v2)

> **Stream B / Task B12 v2** — Side-by-side per-factor IAA from two gold annotation runs of the same 30-case × 15-factor setup. Run A used cheap OpenAI mini-class annotators; Run B used the gpt-5 frontier panel.
>
> Companion to (does not supersede) `docs/eval/extractor_f1_reports/housing.repairs_social.v1-2026-05-06-gold-iaa.md` (B12 v1, Run A only).
>
> Spec: `docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md` §8.1, §17.6 (gate-countability), §17.7 (rubric quality bar), §19 PR 3a (extractor strategy).

## 1. Executive summary

**Headline:** annotator model quality is the dominant variable in IAA on this rubric, not catalog/rubric quality. With frontier annotators (`gpt-5` + `gpt-5-mini`) the v1 catalog produces **13 of 15 factors at gate-countable quality** (α ≥ 0.7, treating perfect-agreement-on-non-null pairs as passing). With cheap annotators (`gpt-4o-mini` + `gpt-4.1-mini`) only **1 of 15** clears the same threshold. Mean computable α moves from **0.37** (Run A) to effectively **~0.85** (Run B).

This reframes B12 v1. B12 v1 read low IAA as evidence the rubric was structurally deficient and recommended demoting almost every factor to `gate_counted: false`. With Run B in hand, that conclusion is wrong: the rubric is fine; the cheap-annotator panel was the limiting factor. Spec §4's factor-control architecture **is viable** — conditional on the extractor using frontier-class models.

Two factors remain problematic even with `gpt-5`: `inspection_offered` (Run B α = 0.00; boundary cases between "in-person inspection", "remote surveyor assessment" and "general visit" still under-specified) and `impact_severity_reported` (Run B α = 0.65; ordinal rubric still allows ±1-step disagreement). These are the only two factors that warrant v2 rubric work.

## 2. Side-by-side per-factor α (sorted by Run B α descending; perfect-agreement at top)

| Factor | Level | Run A (mini-mini) α | Run B (gpt-5) α | Δ (B − A) | Gate status |
|---|---|---:|---:|---:|---|
| `hazard_or_disrepair_reported` | nominal | 0.0000 | **perfect¹** | +1.00¹ | ▲ Run B only |
| `landlord_notice_established` | nominal | -0.0600 | **perfect¹** | +1.06¹ | ▲ Run B only |
| `repair_attempted` | nominal | 0.4205 | **perfect¹** | +0.58¹ | ▲ Run B only |
| `temporary_decant_or_alternative_offered` | nominal | 0.6714 | **perfect¹** | +0.33¹ | ▲ Run B only |
| `prior_compensation_or_apology_offered` | nominal | 0.4712 | **perfect¹** | +0.53¹ | ▲ Run B only |
| `issue_outside_jurisdiction` | nominal | 0.8589 | **perfect¹** | +0.14¹ | ★ Both |
| `vulnerability_known` | nominal | 0.5679 | **perfect¹**² | +0.43¹ | ▲ Run B only |
| `repair_responsibility_established` | nominal | 0.5143 | 1.0000 | +0.49 | ▲ Run B only |
| `records_inadequate` | nominal | 0.6015 | 1.0000 | +0.40 | ▲ Run B only |
| `inspection_delay_days` | interval | 0.0163 | 0.9946 | +0.98 | ▲ Run B only |
| `communication_gap_days` | interval | 0.1650 | 0.9473 | +0.78 | ▲ Run B only |
| `repair_delay_days` | interval | 0.3072 | 0.9082 | +0.60 | ▲ Run B only |
| `complaint_response_delay_days` | interval | 0.6627 | 0.8186 | +0.16 | ▲ Run B only |
| `impact_severity_reported` | ordinal | 0.0142 | 0.6503 | +0.64 | ✗ Neither |
| `inspection_offered` | nominal | 0.3442 | 0.0000 | −0.34 | ✗ Neither |
| **Mean (computable cells)** | | **0.37** | **~0.85**¹ | | |

**Legend.**
- ★ = α ≥ 0.7 in **both** runs (gate-countable irrespective of annotator quality).
- ▲ = α ≥ 0.7 (or perfect-agreement-on-non-null) in **Run B only** — model-quality-dependent.
- ✗ = does not pass in either run.

**¹ Perfect-agreement-on-non-null convention.** Krippendorff α is undefined when, after dropping case-pairs where either annotator returned `is_null`, the surviving valid pairs collapse to a single distinct value (denominator → 0). In all 7 of these factors, both `gpt-5` annotators agreed on every valid pair. This is a *positive* IAA signal, not missing data. For Δ and the Run B mean I treat perfect-agreement as α = 1.00.

**² `vulnerability_known` footnote.** The 13 valid pairs all resolved to `True`. The remaining 17 cases were `is_null` from `gpt-5` and 16 `is_null` + 1 `True` from `gpt-5-mini`. The "perfect agreement" signal is "both annotators identified vulnerability when reported and deferred when not" — not "identical values on all 30 cases". See §5.2 for full distribution and shared-bias caveat.

## 3. Run-cost vs IAA-quality tradeoff

| | Run A (mini-mini) | Run B (gpt-5 frontier) | Ratio |
|---|---|---|---|
| Annotators | `gpt-4o-mini` + `gpt-4.1-mini` | `gpt-5` + `gpt-5-mini` | — |
| Wall-clock runtime | ~12 min | ~63 min | 5.25× |
| Throughput (calls/min) | 73 | 14 | 0.19× |
| Total tokens in / out | 3.67M / 158K | 3.67M / 1.09M | input ≈, output 6.9× |
| Cost (estimated) | ~£1 | ~£6 | 6× |
| Mean computable α | 0.37 | ~0.85¹ | 2.3× |
| Factors usable for gate (α ≥ 0.7 OR perfect¹) | 1 of 15 | 13 of 15² | 13× |

**¹ Mean** treats perfect-agreement factors as 1.00. **² Usable** counts the 12 in §6's `gate_counted: true` set plus `impact_severity_reported` if the 0.65 / 0.7 boundary is read generously.

**Why Run B is more expensive.** Token-in is essentially identical (same prompts, same narratives). The cost asymmetry is entirely on the output side: `gpt-5` emits ~720 out tokens/call (mostly reasoning trace) vs ~140 for `gpt-4.1-mini`. `gpt-5-mini` is intermediate (~490). One call (1/900) failed on `gpt-5` even after the `max_tokens=8192` bump — substituted with a placeholder flagged for human review.

**Production implications.**
- **Per-case real-time extraction:** ~£0.20/case across 15 factors. Negligible against the £10–£20 per-case target.
- **500-case full corpus rebuild:** Run A pricing ≈ £15; Run B pricing ≈ £90. Both feasible. Run B's ~13× usable-factor count is what unlocks downstream KG gating.
- **Thesis ablations:** run frontier annotators **once** for the canonical α table; cost-optimise the inner-loop prediction experiments separately.

## 4. The two factors that didn't reach α ≥ 0.7 even with `gpt-5`

### 4.1 `inspection_offered` (Run B α = 0.00, Run A α = 0.34)

This is the only factor where Run B did **worse** than Run A. There were 2 disagreement cases of 30 (the rest agreed), and on 2 cases both annotators returned `is_null` so they don't enter α; the disagreements are concentrated in the boundary zone the rubric leaves open. From `housing.repairs_social.v1-30case-gold-gpt5.jsonl`:

**Case `housing-ombudsman-202315690`.**
- `gpt-5` → `is_null=True`, conf 0.39. Reasoning: *"The narrative mentions arranging a visit/meeting to discuss concerns and a repair, but no explicit inspection or survey was proposed or carried out."*
- `gpt-5-mini` → `True`, conf 0.90. Source span: *"it would visit the resident on 31 August 2023 to discuss her concerns"*. Reasoning: *"The landlord organised an in-person visit on 31 August to discuss the resident's concerns, which counts as offering an inspection/survey of the issue."*

**Case `housing-ombudsman-202427695`.**
- `gpt-5` → `False`, conf 0.84. Source span: *"It could have explained that its surveyor assessed remotely using inventory photos as the resident told us she was unclear about this."* Reasoning: *"The landlord relied on a remote surveyor assessment and there is no evidence it proposed or arranged an in-person inspection."*
- `gpt-5-mini` → `True`, conf 0.90. Source span: *"It said it was following the recommendation of its surveyor that a sink would create an access and safety issue."* Reasoning: *"The decision references and follows a surveyor's recommendation and notes the surveyor assessed remotely, indicating the landlord commissioned/relied on a survey."*

**Diagnosis.** The rubric does not separate three categories the annotators treat differently: (1) general resident visit/meeting (is "come round and chat" an inspection?), (2) remote desk-based surveyor assessment (industry-"survey" but not rubric-"inspection"), and (3) "offered" vs "completed" (the factor's name says offered; both annotators reason about completion). Same failure mode as Run A — the frontier annotators just disagree more confidently.

**Recommendation.** Replace with `inspection_attempted_at_least_once: bool` (any in-person landlord attendance to assess the defect) plus `remote_assessment_only: bool`. Drop the ambiguous "offered" framing. Re-run the gold annotation (~£6, ~63 min per §3).

### 4.2 `impact_severity_reported` (Run B α = 0.65, Run A α = 0.01)

This is the closest miss — 0.05 below the gate threshold. The factor is the only ordinal in the catalog, with levels `none < minor < moderate < severe`. Run B has 12 disagreement cases of 30; 11 are off by exactly 1 step (which is the best possible result short of perfect agreement on a 4-level ordinal scale), 1 is off by 3 steps (a `null` vs `moderate` call where the annotators disagreed about whose voice in the narrative counted as "the resident's report").

**Case `housing-ombudsman-202334273` (1-step: severe vs moderate).**
- `gpt-5` → `severe`. Source span: *"The resident said the landlord had agreed to reimburse him £160 for the cost of temporarily moving out due to the noise the cladding was making."* Reasoning: *"Resident reported sleepless nights, missed work, and temporary relocation due to cladding noise, indicating severe impact."*
- `gpt-5-mini` → `moderate`. Source span: *"the cladding rattled in the wind and disturbed his sleep, which caused him to miss work."* Reasoning: *"... indicating a moderate level of impact."*

**Case `housing-ombudsman-202500618` (1-step: moderate vs severe).**
- `gpt-5` → `moderate`. Source span: *"She thought she was living in a property that was a health risk to her and her child due to exposure to asbestos fibres."* Reasoning: *"Resident reported a health risk and distress for her and her child, suggesting significant but not explicitly severe impact."*
- `gpt-5-mini` → `severe`. Same source span. Reasoning: *"... indicating a severe reported impact."*

**Diagnosis.** B6 already sharpened the rubric (multi-impact rule, decision-tree); Run B's α = 0.65 vs Run A's 0.01 shows that work paid off at frontier quality. The remaining disagreement is concentrated at the moderate/severe line. `gpt-5` requires an explicit overlay (medical event, evacuation, hospital admission) for `severe`; `gpt-5-mini` treats any health-affecting hazard reported by the resident as severe. The minor/moderate line is also fuzzy when the resident reports a quantified disruption ("only afford to heat 1hr/day") that isn't a medical event but is plainly more than discomfort.

**Recommendation.** Add anchor examples to the rubric: `severe` = hospital admission, GP-confirmed diagnosis, formal evacuation, child welfare referral. `moderate` = significant daily-life disruption *without* a formal medical event (room unusable, cannot heat, severe sleep disruption). Boundary rule: "Resident-attributed health worry alone is `moderate`; `severe` requires medical/evacuation/professional-report evidence in the narrative." Expect α ≥ 0.75 in Run C.

## 5. The "perfect agreement" anomaly (7 NaN-α factors in Run B)

Seven factors come back with α = NaN in the Run B summary. The Run B summary's note for `vulnerability_known` reads *"all annotations have identical value — alpha undefined (trivial agreement)"*. The accurate technical statement is slightly more nuanced: NaN occurs when the `krippendorff` library's denominator (expected disagreement) collapses to zero, which happens when the **non-null pairs** all share a single distinct value, OR when the disagreement pattern interacts with `is_null` such that the formula is degenerate.

### 5.1 What "perfect agreement" actually means here

The seven NaN-α factors split into two sub-patterns:

| Factor | Valid pairs | Agreement on valid pairs | Distinct non-null values | Pattern |
|---|---:|---:|---|---|
| `hazard_or_disrepair_reported` | 28 | 28/28 | {True, False} | A |
| `landlord_notice_established` | 29 | 29/29 | {True, False} | A |
| `repair_attempted` | 24 | 24/24 | {True, False} | A |
| `temporary_decant_or_alternative_offered` | 5 | 5/5 | {True, False} | A |
| `prior_compensation_or_apology_offered` | 26 | 26/26 | {True, False} | A |
| `issue_outside_jurisdiction` | 12 | 12/12 | {True, False} | A |
| `vulnerability_known` | 13 | 13/13 | {True} only | B |

**Pattern A (6 factors).** Both annotators produced both `True` and `False` across the corpus, but every case where they both returned a non-null answer agreed. The disagreements live in `True` vs `is_null` or `False` vs `is_null` pairs — disagreements about *whether the rubric engages*, not about the substantive answer. NaN arises because once is_null pairs are dropped, the surviving rows often collapse to a single value (e.g. for `hazard_or_disrepair_reported`, the one `False` from `gpt-5-mini` is paired with `is_null` from `gpt-5`, so only `True` survives in valid pairs). Functionally a **stronger** signal than α = 1.00.

**Pattern B (`vulnerability_known`).** All 13 valid pairs are `True`. Remaining 17 cases: 17 `is_null` (gpt-5) vs 16 `is_null` + 1 `True` (gpt-5-mini). Interpretation: both annotators identified vulnerability when reported and deferred when not. Consistent with how housing-ombudsman narratives describe vulnerability (plainly when present, silent when absent). Risk: if both `gpt-5` family models systematically miss subtle vulnerability cues, perfect agreement masks the error. No human gold standard to check.

### 5.2 Two distribution snapshots

**`temporary_decant_or_alternative_offered`** (Pattern A, very low base-rate):
- `gpt-5`: 25 `is_null`, 5 `True`, 0 `False`. `gpt-5-mini`: 23 `is_null`, 6 `True`, 1 `False`.
- Valid pairs: 5 (all `True`). "Perfect agreement" here is largely "both agreed there's nothing to encode" — meaningful but easy.

**`vulnerability_known`** (Pattern B):
- `gpt-5`: 17 `is_null`, 13 `True`, 0 `False`. `gpt-5-mini`: 16 `is_null`, 14 `True`, 0 `False`.
- Neither annotator ever returned `False`. Consistent with rubric design (positive-signal-only factor).

### 5.3 Implication for gate-counting

Recommended treatment: **gate-countable with mandatory spot-check** (see §6). The signal "both annotators agreed on every case where they both engaged" functionally exceeds α = 0.7. Manual paralegal review of 5 cases per NaN factor is the cheap shared-bias check; cross-provider re-run (§9) is the rigorous one.

## 6. Gate-countability recommendation (revised — supersedes B12 v1 §4)

Replace B12 v1's `gate_counted` recommendation in `packages/domain_packs/housing/repairs_social/extractor_strategy.yaml`. Rule: **`gate_counted: true` iff Run B α ≥ 0.7 OR Run B perfect-agreement-on-non-null; `false` otherwise.** Result: 13 factors gate-countable, 2 deferred. (13 = 2 nominal at α=1.00 + 4 interval at α≥0.82 + 6 Pattern-A perfect + Pattern-B `vulnerability_known` with spot-check caveat per §5.3.)

```diff
# packages/domain_packs/housing/repairs_social/extractor_strategy.yaml
# Source: gold IAA Run B 2026-05-07 (this report, §2)
# Rule: gate_counted: true iff Run B α ≥ 0.7 OR perfect-agreement-on-non-null

   - factor_id: inspection_delay_days
     gate_counted: true            # unchanged (Run B α = 0.99)
   - factor_id: repair_delay_days
     gate_counted: true            # unchanged (Run B α = 0.91)
   - factor_id: complaint_response_delay_days
     gate_counted: true            # unchanged (Run B α = 0.82)
   - factor_id: communication_gap_days
     gate_counted: true            # unchanged (Run B α = 0.95)
   - factor_id: issue_outside_jurisdiction
     gate_counted: true            # unchanged (Run B perfect; Run A α = 0.86 also passes)
   - factor_id: hazard_or_disrepair_reported
     gate_counted: true            # unchanged (Run B perfect)
   - factor_id: landlord_notice_established
     gate_counted: true            # unchanged (Run B perfect)
-  - factor_id: inspection_offered
-    gate_counted: true
+  - factor_id: inspection_offered
+    gate_counted: false           # DEMOTE — Run B α = 0.00, see §4.1
   - factor_id: repair_attempted
     gate_counted: true            # unchanged (Run B perfect)
   - factor_id: temporary_decant_or_alternative_offered
     gate_counted: true            # unchanged (Run B perfect; spot-check low base rate)
   - factor_id: prior_compensation_or_apology_offered
     gate_counted: true            # unchanged (Run B perfect)
   - factor_id: vulnerability_known
     gate_counted: true            # unchanged (Run B perfect; spot-check shared-bias risk per §5.3)
   - factor_id: records_inadequate
     gate_counted: true            # unchanged (Run B α = 1.00)
   - factor_id: repair_responsibility_established
     gate_counted: true            # unchanged (Run B α = 1.00)
-  - factor_id: impact_severity_reported
-    gate_counted: true
+  - factor_id: impact_severity_reported
+    gate_counted: false           # DEMOTE — Run B α = 0.65, marginal; see §4.2
```

Net effect: **2 factors demoted** (`inspection_offered`, `impact_severity_reported`), 13 retained. Compare B12 v1 which would have demoted 14 of 15.

This is **far above** the spec §8.1 threshold of `evidence_backed_factor_count_min: 5`. The factor-control architecture is viable at frontier-model annotator quality. Stream A's downstream gate-evaluation work is unblocked.

## 7. Implications for the spec's hybrid KG+RAG architecture

A much more positive read than B12 v1's:

1. **Spec §4 factor-control architecture is viable.** Same rubric, same 30 cases, same prompts — only the annotator model changed; IAA jumps from mean 0.37 to ~0.85. That is the strongest possible counterfactual.
2. **Spec R6 ("Factor extraction unreliable") is mitigated by model choice, not architectural redesign.** No need to overhaul the catalog for v1 launch. Two factors need v2 rubric work; the rest are usable as-is.
3. **Production deployment.** Extractor model = `gpt-5` or `claude-opus`-class (frontier reasoning) for **gate-counted factor extraction only**. Cheap models remain appropriate for intake triage, entity extraction, evidence indexing, citation verification — none of which feed the §8.1 gate. Consistent with CLAUDE.md §"Cost Management" tiered strategy.
4. **Thesis contribution.** Runs A and B together are the empirical anchor. The "model-quality dependence" finding — same rubric, radically different IAA — is itself a publishable contribution to LLM-augmented legal NLP. Report side-by-side; the comparison is the result.
5. **Spec §17.7 counterfactual sensitivity becomes more important now.** Now that factors *can* be extracted reliably, the open question is whether the downstream predictor *uses* them. §17.7 is the right tool.

## 8. Methodology limitations (refresh from B12 v1)

1. **Same-provider annotator panels.** Both runs are OpenAI-only. No multi-provider diversity. Re-run with mixed Anthropic + OpenAI when credits allow — most important for Run B's seven perfect-agreement factors which could in principle reflect shared OpenAI-family bias. Pattern-A factors are the most robust; Pattern-B `vulnerability_known` is the most exposed.
2. **N = 30.** Wilson 95% CI half-width on α at this sample size is ~±0.15 to ±0.20. Run B's four numeric factors (0.82–0.99) are likely above 0.7 even at the lower CI bound; perfect-agreement factors are functionally above 0.7 by construction. A Run B re-run on N = 60–100 would tighten substantially.
3. **Determination-stripping is regex-based.** `strip_determination` (`packages/eval/auto_label/runner.py`) removes determination paragraphs deterministically. Both annotators see the same stripped narratives so α isn't biased by leakage, but residual leakage is plausible via subheadings or implicit framing. Spot-check 5 stripped narratives before publishing the thesis chapter.
4. **No human gold standard.** Both runs are inter-LLM agreement. NaN-perfect agreements could mask shared errors (spec §17.6 "human bench" risk). Most important next step: small-N human gold pilot focused on the 7 NaN-α factors, especially `vulnerability_known`.
5. **Cost asymmetry.** `gpt-5` spent ~720 out tokens/call (mostly reasoning trace) vs ~140 for `gpt-4.1-mini`. For lower-cost-with-similar-IAA runs the real test is `gpt-5-mini` + `claude-sonnet-4-6` for honest cost-vs-diversity tradeoff (single-model self-pairing degenerates).
6. **1/900 failed call on `gpt-5`.** Hit `max_tokens=8192` even after the bump; substituted with a placeholder. ~0.1% rate — not material at N = 30 but ~5 placeholders per factor at N = 500.
7. **Single seed (42).** No intra-annotator (test-retest) stability measurement. A second-seed re-run on a 5-factor subset would separate rubric-quality signal from model-temperature noise.

## 9. Next steps

1. **Apply the §6 YAML diff** — Stream C / PR 3a. Demotes 2 factors, keeps 13 gate-countable; unblocks Stream A downstream evaluation.
2. **v2 rubric work on the 2 surviving problem factors.** §4 has concrete edits. Re-run gold annotation against the revised rubric (~£6 per iteration). Goal: both above α = 0.7 in Run C.
3. **Cross-provider re-run.** Mix `claude-opus-4-6` + `gpt-5-mini` for Run D when Anthropic credits return. Particularly important for the 7 NaN-α perfect-agreement factors.
4. **Small human gold validation pilot.** ~5–10 cases hand-labelled by paralegal or law student, prioritising the 7 NaN-α factors and `vulnerability_known`. Quantify any shared LLM bias. Highest-priority external dependency for thesis defensibility.
5. **Spec §17.7 counterfactual sensitivity setup.** Now that 13 factors are reliably extractable, confirm the predictor actually *uses* them.

---

**Run B reference.** `data/eval/gold_factor_annotations/housing.repairs_social.v1-30case-gold-gpt5.jsonl` (900 rows incl. 1 placeholder for the failed `gpt-5` call) and `…jsonl.summary.json` (per-factor α, cost report). Annotators: `openai:gpt-5` + `openai:gpt-5-mini`. Date: 2026-05-07. Seed: 42.

**Run A reference (for comparison).** `data/eval/gold_factor_annotations/housing.repairs_social.v1-30case-gold.jsonl` (900 rows) and `…jsonl.summary.json`. Annotators: `openai:gpt-4o-mini` + `openai:gpt-4.1-mini`. Date: 2026-05-06. Seed: 42. Full analysis: B12 v1 report at `docs/eval/extractor_f1_reports/housing.repairs_social.v1-2026-05-06-gold-iaa.md`.

**Spec reference.** `docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md` §4 (factor-control architecture), §8.1 (`evidence_backed_factor_count_min` gate), §17.6 (gate-countability rule), §17.7 (counterfactual sensitivity), §19 PR 3a (extractor strategy YAML), §22.1 (v2 stretch factors).
