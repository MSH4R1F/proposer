# Housing Repairs Social v1 — Gold Inter-Annotator Agreement Report

> ⚠️ **SUPERSEDED by the comparative report — read [`housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md`](housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md) for the canonical analysis.**
>
> This v1 report covers the **mini-mini run only** (gpt-4o-mini + gpt-4.1-mini, ~£1, mean α=0.37) and reaches the pessimistic conclusion that only 1 of 15 factors is gate-countable. A subsequent run with frontier annotators (gpt-5 + gpt-5-mini, ~£6) found 13 of 15 factors gate-countable. The v2 comparative report supersedes this one's recommendations and reframes the architectural defensibility question.
>
> This report is preserved as a historical record because the methodology and disagreement examples are still valid and the model-quality contrast it sets up with v2 is itself a finding.
>
> ---
>
> **Stream B / Task B12 (v1)** — Per-factor IAA report for the 30-case × 15-factor gold annotation run with mini-class annotators.
>
> Spec: `docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md` §17.6 (gate-countability), §17.7 (rubric quality bar), §19 PR 3a (extractor strategy).

## 1. Run metadata

| Field | Value |
|---|---|
| Domain pack | `housing.repairs_social.v1` |
| Date of run | 2026-05-06 |
| Gold-N (cases) | 30 |
| Factor count | 15 |
| Annotator A | `openai:gpt-4o-mini` |
| Annotator B | `openai:gpt-4.1-mini` |
| Annotation seed | 42 |
| Total LLM calls | 900 (30 cases × 15 factors × 2 annotators) |
| Tokens in / out | 3,673,410 / 158,188 |
| Wall-clock runtime | ~12 minutes |
| Throughput | ~73 calls/min |
| Cost (printed) | £0.00 |
| Cost (estimated) | ~£1 (see note below) |

**Cost note.** The OpenAI client's `_PRICING_TABLE` (`packages/llm_orchestrator/clients/labeler_factory.py`) lacks entries for these models, so the report prints £0.00 despite real spend. Hand-estimating: `gpt-4o-mini` ($0.15/M in + $0.60/M out) ≈ $0.32; `gpt-4.1-mini` ($0.40/M in + $1.60/M out) ≈ $0.87. Total ≈ $1.19, ~£0.95 at 0.80 USD/GBP. Follow-up: add the missing pricing rows.

Annotators saw narrative text ONLY — `strip_determination` in `packages/eval/auto_label/runner.py` removed determination paragraphs deterministically.

## 2. Per-factor α table

Sorted descending by α. The gate threshold lines (per spec §17.6) split the table into three bands.

| Factor | Level | α | Band |
|---|---|---:|---|
| `issue_outside_jurisdiction` | nominal | **0.86** | **gate-countable** |
| | | | — α ≥ 0.7 line — |
| `temporary_decant_or_alternative_offered` | nominal | 0.67 | extractable |
| `complaint_response_delay_days` | interval | 0.66 | extractable |
| `records_inadequate` | nominal | 0.60 | extractable |
| `vulnerability_known` | nominal | 0.57 | extractable |
| `repair_responsibility_established` | nominal | 0.51 | extractable |
| | | | — α ≥ 0.5 line — |
| `prior_compensation_or_apology_offered` | nominal | 0.47 | rubric work |
| `repair_attempted` | nominal | 0.42 | rubric work |
| `inspection_offered` | nominal | 0.34 | rubric work |
| `repair_delay_days` | interval | 0.31 | rubric work |
| `communication_gap_days` | interval | 0.17 | rubric work |
| `inspection_delay_days` | interval | 0.02 | rubric work |
| `impact_severity_reported` | ordinal | 0.01 | rubric work |
| `hazard_or_disrepair_reported` | nominal | 0.00 | rubric work |
| `landlord_notice_established` | nominal | -0.06 | rubric work |
| **Mean** | | **0.37** | |

**Bands (per spec §17.6):** **α ≥ 0.7 (gate-countable)** — only `issue_outside_jurisdiction` clears it; notably the only rule-derived `deterministic` factor. **0.5 ≤ α < 0.7 (extractable, not gate-counted)** — 5 factors; populate the KG informationally but do NOT contribute to the spec §8.1 `evidence_backed_factor_count_min: 5` gate. **α < 0.5 (rubric work needed)** — 9 factors, including 3 of 4 numeric durations and the entire "factual foundation" trio (`landlord_notice_established`, `hazard_or_disrepair_reported`, `impact_severity_reported`).

## 3. Disagreement analysis (5 lowest-α factors)

Disagreement criteria: boolean value mismatch; numeric null-vs-numeric or |Δ| ≥ 30 days; ordinal enum mismatch. All quotes verbatim from the JSONL.

### 3.1 `landlord_notice_established` (α = -0.06)

5 of 30 cases disagreed. The pattern is striking: in every case below `gpt-4.1-mini` answered **True** while `gpt-4o-mini` answered **False** (or null) on the same narrative.

**Case `housing-ombudsman-202334186`.**
- `gpt-4o-mini` → **False**, conf 0.9. Reasoning: "no evidence of any communication from the resident regarding the leak between February 2018 and 8 November 2022".
- `gpt-4.1-mini` → **True**, conf 0.95. Reasoning: "The landlord inspected the property shortly after the resident reported the leak in 2018, demonstrating that landlord notice was indeed established."

**Case `housing-ombudsman-202444908`.**
- `gpt-4o-mini` → **False**, conf 0.9. Reasoning: "the landlord has told us it has no records of this communication".
- `gpt-4.1-mini` → **True**, conf 0.95. Reasoning: "The landlord apologised in its stage 1 complaint response (November 2021) for its overall delays in responding to the resident."

**Case `housing-ombudsman-202324360`.**
- `gpt-4o-mini` → **null** (is_null=True), conf 0.0. Reasoning: "narrative does not confirm if the landlord acknowledged or logged the report".
- `gpt-4.1-mini` → **True**, conf 0.9. Reasoning: "the landlord acknowledged responsibility and compensated the resident".

**Diagnosis.** The rubric says notice is established when the landlord "acknowledged it, logged it, responded to it, or did not credibly deny it." `gpt-4.1-mini` treats ANY downstream landlord action (inspection, apology, compensation) as implicit acknowledgement (the lawyerly O'Brien v Robinson inference). `gpt-4o-mini` requires direct first-hop evidence and treats record gaps as disconfirming. Both readings are defensible from the rubric — which is the problem.

**Recommendation.** Rubric tweak: add affirmative phrasing for "downstream landlord conduct that presupposes notice (inspections, repair tickets, complaint responses, apologies)" and an explicit edge case for "landlord later denies records — does contractor activity establish notice?".

### 3.2 `hazard_or_disrepair_reported` (α = 0.00)

3 disagreement cases. The pattern is the inverse of §3.1: this time `gpt-4o-mini` returns **null** when the case is non-disrepair (service-charge-only), while `gpt-4.1-mini` returns **False** for the same case.

**Case `housing-ombudsman-202431015`.**
- `gpt-4o-mini` → **null**, conf 1.0. Reasoning: "no indication in the narrative of any report of disrepair or hazard by the resident".
- `gpt-4.1-mini` → **False**, conf 1.0. Reasoning: "complaint about service charges but contains no indication that the resident or anyone reported a disrepair or hazard".

**Case `housing-ombudsman-202207230`.**
- `gpt-4o-mini` → **null**, conf 1.0.
- `gpt-4.1-mini` → **False**, conf 0.95. (service charges + electricity usage complaint)

**Case `housing-ombudsman-202427695`.**
- `gpt-4o-mini` → **True**, conf 0.9. Reasoning: "resident conveyed a concern regarding hygiene that indicates a report of disrepair or a hazard".
- `gpt-4.1-mini` → **False**, conf 0.95. Reasoning: "request to install a sink not an existing disrepair or hazard."

**Diagnosis.** Two ambiguities: (1) for cases not engaging the factor at all (service-charge complaints), is the right encoding `False` or `null`? The rubric's "Unclear defaults to absent for booleans" rule doesn't tell the annotator whether "not engaged" counts as "unclear absent". (2) Boundary between "request for an improvement" (sink install) and "report of disrepair/hazard" — the rubric includes informal reports but does not draw this line.

**Recommendation.** (a) Add a "factor not engaged" rule for non-repair cases — encode `False` consistently rather than `null`, or introduce an explicit `not_applicable`. (b) List exclusions ("requests for new fixtures, improvements, alterations are not reports of disrepair").

### 3.3 `impact_severity_reported` (α = 0.01)

15 of 30 cases disagreed — half the corpus. This is the worst per-factor result and the only ordinal factor in the catalog.

**Case `housing-ombudsman-202444908`.**
- `gpt-4o-mini` → **severe**, conf 0.9. Reasoning: "resident explicitly reported severe impact on her son's health due to damp and mould" (son hospitalised, asthma diagnosis).
- `gpt-4.1-mini` → **moderate**, conf 0.9. Reasoning: same facts but: "no description of severe disruption like inability to use essential rooms".

**Case `housing-ombudsman-202500618`.**
- `gpt-4o-mini` → **severe**, conf 0.9. Reasoning: asbestos affecting child's health.
- `gpt-4.1-mini` → **moderate**, conf 0.9. Reasoning: distress and "no direct severe health event reported".

**Case `housing-ombudsman-202402569`.**
- `gpt-4o-mini` → **null**, conf 0.9. Reasoning: "narrative does not explicitly mention the resident's reported impact level".
- `gpt-4.1-mini` → **moderate**, conf 0.85. Reasoning: lift outage, distress, time and trouble.

**Diagnosis.** The rubric exemplifies `severe` as "child hospitalised due to damp" — but `gpt-4.1-mini` applies a stricter "essential rooms unusable" overlay the rubric doesn't require. Three boundary calls are being conflated: (a) `null` vs `none` vs `minor`; (b) hospitalisation/diagnosis as `severe` vs `moderate`; (c) distress-only as `minor` vs `moderate`. A 4-level ordinal with imprecise boundaries on N=30 is the worst case for α.

**Recommendation.** Either collapse to 2-level (`reported_impact_substantial: bool`) and accept lost granularity, or replace the free-text severity guidance with a decision tree ("Step 1: hospital admission, medical diagnosis, or evacuation reported? → severe. Step 2: essential room unusable? → moderate. Step 3: disruption or distress reported? → minor. Step 4: otherwise → null.").

### 3.4 `inspection_delay_days` (α = 0.02)

9 disagreement cases. Pattern: `gpt-4o-mini` returns **null** (citing missing/ambiguous dates) while `gpt-4.1-mini` confidently extracts a number from the same narrative.

**Case `housing-ombudsman-202402680`.**
- `gpt-4o-mini` → **null**, conf 1.0. Reasoning: "narrative does not provide specific dates for when inspections were completed".
- `gpt-4.1-mini` → **236d**, conf 0.9. Reasoning: "report on 15 February 2023 and the first inspection actually carried out was on 4 October 2023".

**Case `housing-ombudsman-202444908`.**
- `gpt-4o-mini` → **null**, conf 1.0.
- `gpt-4.1-mini` → **24d**, conf 0.95. Reasoning: "mould wash and applied anti mould paint on 28 April 2024 ... 24 working days after the resident reported".

**Case `housing-ombudsman-202508050`.**
- `gpt-4o-mini` → **12d**, conf 1.0. Reasoning: "12 days after the resident's report on 30 October 2023" (note: arithmetic is wrong if the inspection was on 12 October).
- `gpt-4.1-mini` → **273d**, conf 0.9. Reasoning: "first report was on 3 January 2023, and the first inspection was on 12 October 2023, roughly 273 days later".

**Diagnosis.** Three rubric-driven ambiguities. (a) "Inspection" definition unclear when the landlord's first action is a repair-cum-inspection (mould wash, gutter clean) — `gpt-4.1-mini` treats those as inspection events, `gpt-4o-mini` does not. (b) When multiple report dates exist, the rubric says "use the first inspection date" but is silent on which **report** date anchors the count. (c) Null-or-encode rule defaults to null on partial dates but doesn't define the partiality threshold.

**Recommendation.** Cleanest "rely on the calculator" finding — production already routes this factor to `inspection_delay_calculator`; leave LLM extraction unused. Rubric tweak is low priority since the LLM path is shadow-only.

### 3.5 `communication_gap_days` (α = 0.17)

16 disagreement cases (the worst by absolute count). Two failure modes coexist.

**Case `housing-ombudsman-202334186`.**
- `gpt-4o-mini` → **174d**, conf 0.85. Reasoning: "from February 2018 until ... 8 November 2022" (interpreted as resident-initiated silence that therefore counts as 0 — but encoded ~174d).
- `gpt-4.1-mini` → **1538d**, conf 0.95. Reasoning: same span, encoded as ~1538 days (4y9m).

**Case `housing-ombudsman-202444908`.**
- `gpt-4o-mini` → **null**, conf 0.9. Reasoning: "narrative does not specify measurable gaps".
- `gpt-4.1-mini` → **90d**, conf 0.85. Reasoning: "resident reported a 3-month communication gap".

**Case `housing-ombudsman-202500618`.**
- `gpt-4o-mini` → **null**, conf 0.9.
- `gpt-4.1-mini` → **180d**, conf 0.85. Reasoning: "approximately 180 days gap of no communication".

**Diagnosis.** (a) The "longest gap" rule and "resident-initiated silence ⇒ encode 0" rule interact badly when one annotator infers resident attribution and the other does not. (b) Resident self-reported gaps ("housing officer didn't respond for 3 months") vs. narrative-evidenced gaps — the rubric doesn't say which side counts as "substantive landlord-resident communication gap". (c) Like §3.4, this factor is `deterministic` with `communication_gap_calculator`; LLM IAA confirms the calculator is the right path.

**Recommendation.** Rely on the calculator. Separate task: define what counts as a "communication event" in the structured timeline.

## 4. Gate-countability recommendation

Based on §2 + §3, the recommended `gate_counted` field for each factor in `packages/domain_packs/housing/repairs_social/extractor_strategy.yaml`. **This is a recommendation only — do not apply in this PR.** A Stream C follow-up should make the change.

```yaml
# Recommended diff to packages/domain_packs/housing/repairs_social/extractor_strategy.yaml
# Source: gold IAA run 2026-05-06 (this report, §2)
# Rule applied: gate_counted: true iff α ≥ 0.7 on 30-case gold

# UNCHANGED — α = 0.86, the only factor that clears the gate threshold
- factor_id: issue_outside_jurisdiction
  gate_counted: true            # keep

# DEMOTED — extractable but α < 0.7
- factor_id: temporary_decant_or_alternative_offered  # α = 0.67
  gate_counted: false           # was true
- factor_id: complaint_response_delay_days            # α = 0.66
  gate_counted: false           # was true
- factor_id: records_inadequate                       # α = 0.60
  gate_counted: false           # was true
- factor_id: vulnerability_known                      # α = 0.57
  gate_counted: false           # was true
- factor_id: repair_responsibility_established        # α = 0.51
  gate_counted: false           # was true

# DEMOTED — α < 0.5, rubric work needed
- factor_id: prior_compensation_or_apology_offered    # α = 0.47
  gate_counted: false
- factor_id: repair_attempted                         # α = 0.42
  gate_counted: false
- factor_id: inspection_offered                       # α = 0.34
  gate_counted: false
- factor_id: repair_delay_days                        # α = 0.31
  gate_counted: false
- factor_id: communication_gap_days                   # α = 0.17
  gate_counted: false
- factor_id: inspection_delay_days                    # α = 0.02
  gate_counted: false
- factor_id: impact_severity_reported                 # α = 0.01
  gate_counted: false
- factor_id: hazard_or_disrepair_reported             # α = 0.00
  gate_counted: false
- factor_id: landlord_notice_established              # α = -0.06
  gate_counted: false
```

Net effect: 1 factor `gate_counted: true`, 14 factors `gate_counted: false` — a substantial change from the current "most factors true" state.

**Implication for spec §8.1 gate.** The threshold `evidence_backed_factor_count_min: 5` becomes structurally unreachable. Either lower it (e.g. to 1) or admit factors with α ∈ [0.5, 0.7] as "softly gate-counted" with a discount weight. Stream A architecture decision.

## 5. Methodology limitations

The IAA results should be read as a **lower bound** on inter-annotator reliability. Caveats:

1. **Same-provider, near-same-lineage annotators.** Both `gpt-4o-mini` and `gpt-4.1-mini` are OpenAI mini-class models with shared tokenizer, training-data lineage, and RLHF style. A true panel would mix providers (Claude + GPT). Anthropic credits were exhausted at run-time, forcing the same-provider configuration. Cross-provider would likely reveal **lower** α — the v1 rubric is even less reliable in practice than this report shows.

2. **N = 30 gives wide confidence intervals.** 95% Wilson CI half-width on α at N=30 is ~±0.15 to ±0.20. Factors with α near 0 (`hazard_or_disrepair_reported`, `landlord_notice_established`, `impact_severity_reported`, `inspection_delay_days`) could be statistically zero or weakly positive/negative; the sign of these point estimates is not load-bearing. The qualitative disagreement analysis in §3 is the more reliable signal.

3. **Corpus is the 50-case gold pilot subset.** When the gold corpus expands (spec §22 target: 200 cases), the IAA run should be repeated; per-factor α may stabilise upward (more rubric signal) or downward (more edge cases surface).

4. **Determination-leakage caveat.** `strip_determination` removes determination paragraphs deterministically (verified by `packages/eval/tests/test_auto_label_cli.py`). Residual leakage is still possible through sub-headings ("Jurisdiction", "Outcome") or narrative phrasing that telegraphs the finding. Both annotators see the same leakage so α is not biased — but downstream cross-validation against actual determination labels could be inflated (Stream A concern).

5. **Single seed.** Run was at seed 42 only at temperature > 0. We have not measured intra-annotator stability (test-retest).

## 6. Implications for the spec's hybrid KG+RAG architecture

The honest read: v1's factor catalog + rubric do not, at this corpus size and annotator panel, produce reliably extractable factors. Consequences:

1. **The §8.1 gate is currently unreachable.** With 1 factor at α ≥ 0.7, `evidence_backed_factor_count_min: 5` fails regardless of extractor output; every case falls back to RAG-only routing (§8.4). Consistent with spec R6 ("Factor extraction itself is unreliable") — does not invalidate the architecture but sharpens the question of WHICH factors deserve v2 rubric investment.

2. **`deterministic` outperforms `llm_verified` for IAA.** The only factor that passes (`issue_outside_jurisdiction`) is rule-derived. For boolean factual presence on free-text narrative, two same-family LLMs do not agree well enough to clear §17.6 at N=30. **Rubric quality, not extractor sophistication, is the bottleneck.** A verifier pass cannot raise α — it only filters extractor outputs.

3. **Numeric durations should rely on calculators.** `inspection_delay_days`, `repair_delay_days`, `communication_gap_days` all have α < 0.32 on the LLM path despite being catalogued as `deterministic`; structured CaseFile date fields should be authoritative. `complaint_response_delay_days` at α = 0.66 is the exception, plausibly because Stage 1 dates are unusually well-flagged in narratives.

4. **For thesis defence, this is a rich negative finding.** Both v2 outcomes are publishable: (a) multiple factors move above α ≥ 0.7, proving the factor-control architecture viable; (b) they don't, adding to the "graphs don't help small legal corpora" narrative the spec already cites.

## 7. Next steps

Three concrete next-action options, in increasing order of investment:

1. **v2 rubric sharpening on the 5 lowest-α factors** (`landlord_notice_established`, `hazard_or_disrepair_reported`, `impact_severity_reported`, `inspection_delay_days`, `communication_gap_days`). Apply the per-factor recommendations in §3 (explicit edge cases, decision-tree severity rubric, "factor not engaged" handling for booleans). Re-run the gold annotation at seed 42. **Goal:** ≥3 of 5 above α = 0.5; ≥1 of 5 above α = 0.7. **Cost:** ~£1 + 12 min per re-run. **Owner:** Stream B (B13 candidate).

2. **Drop unreliable factors from gate-counting and rely on the deterministic core.** Apply the §4 recommendation; lower spec §8.1 `evidence_backed_factor_count_min` from 5 to 1 or 2. **Goal:** unblock Stream A's downstream evaluation while v2 rubric work is in flight. **Owner:** Stream C PR.

3. **Cross-provider re-run when Anthropic credits restored.** Mix Claude + `gpt-4.1-mini` as the panel and re-run the same 30-case × 15-factor IAA. α will likely drop further — more representative of true cross-model variance; defensible thesis baseline. **Cost:** ~£3-4. **Owner:** Stream B post-credit-restoration.

Recommended order: **(1) before (2)** because rubric improvements are cheap and high-leverage; **(3)** runs in parallel as soon as credits return.

---

**Run reference:** `data/eval/gold_factor_annotations/housing.repairs_social.v1-30case-gold.jsonl` (900 rows) and `…jsonl.summary.json` (per-factor α, cost report).

**Spec reference:** `docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md` §17.6 (gate-countability), §17.7 (rubric quality bar), §19 PR 3a (extractor strategy), §22.1 (v2 stretch factors).
