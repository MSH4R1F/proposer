# Housing 150 — Tier-1 Rerun Results (Control Plane Active)

**Run date:** 2026-06-09/10 · **Scale:** 149-case housing gold × {hybrid, kg_only} × seed 1
**Engine:** `predict_all.py --engine live --client openai` (prediction model **gpt-5.5**, extraction gpt-5-mini)
**Predictions:** `eval/predictions/housing_150_ablation_20260609/seed1/{hybrid,kg_only}.jsonl`
**Metrics:** `eval/predictions/housing_150_ablation_20260609/seed1/_metrics.json`

All five Tier-1 mechanisms were active simultaneously in this run:
factor-assertion sidecar (control plane), factor-constrained retrieval, the repairs
determination guide, the post-rules classifier (R1/R2/R3), the tariff quantum model,
and the calibration clamp. Flags: `STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_KG_GATE_RELAXED=1
STREAM_C_DETERMINATION_RULES=1 STREAM_C_TARIFF_QUANTUM=1 STREAM_C_PROPOSITION_TAG_FUZZY=1`,
`LLM_PREDICTION_REASONING_EFFORT=medium`.

---

## TL;DR

**One clear win, several regressions, one diagnosable root cause.**

- ✅ **kg_only Brier calibration fixed: 0.354 → 0.168** (−0.186). The degenerate
  miscalibration that the calibration clamp was built to kill is gone. This was the
  primary stated objective of the calibration fix and it worked.
- ✅ **Rare determination classes moved off 0.0 recall.** `reasonable_redress` 0.00 → 0.81,
  `severe_maladministration` 0.00 → 0.24 (hybrid) / 0.53 (kg), `resolved_with_intervention`
  0.00 → 0.42 (hybrid) / 0.33 (kg). The determination machinery *can* surface these classes.
- ❌ **Binary accuracy regressed** in both modes (hybrid 94.6 → 85.9, kg_only 96.0 → 91.3).
- ❌ **Determination accuracy regressed** (hybrid 45.0 → 33.6; kg_only ≈flat 35.6 → 34.9).
- ❌ **Amount MAE got worse than the trivial baseline** (model £802/£753 vs always-£500 MAE £634).

**Root cause of the determination + amount regressions:** rule **R3 over-fires.**
It produced `reasonable_redress` 44× (hybrid) / 35× (kg) against a gold count of 21.
R3's trigger — *prior offer present AND LLM amount is None/0* — conflates "the model
emitted no amount" (common; the tariff then fills it) with "the landlord already
remedied." This (a) steals from the true majority class `maladministration`, collapsing
its recall and dragging determination accuracy down, and (b) forces the £0 tariff band,
systematically under-predicting awards.

---

## 1. Headline metrics: before / after

| Mode | Metric | 05-23 baseline¹ | Tier-1 rerun | Δ |
|------|--------|----------------:|-------------:|----:|
| **hybrid** | Accuracy | 94.6 | **85.9** | −8.7 |
| | Balanced acc | — | 68.7 | — |
| | Brier (landlord) | 0.163 | **0.250** | +0.087 ✗ |
| | Log-loss | — | 0.693 | — |
| | Determination acc | 45.0 | **33.6** | −11.4 |
| | Abstention rate | — | 1.3% | — |
| **kg_only** | Accuracy | 96.0 | **91.3** | −4.7 |
| | Balanced acc | — | 79.5 | — |
| | Brier (landlord) | 0.354 | **0.168** | **−0.186 ✓** |
| | Log-loss | — | 0.523 | — |
| | Determination acc | 35.6 | **34.9** | −0.7 |
| | Abstention rate | — | 0.0% | — |

**Trivial baselines on the 149-case gold:**
- *Always-tenant* accuracy = **96.0%** (143/149 cases are tenant-win). Both modes
  now sit *below* this trivial baseline on raw accuracy — but raw accuracy is
  near-useless on a 96%-tenant prior; balanced accuracy (68.7 / 79.5) and Brier are
  the meaningful signals, and kg_only's Brier improvement is real.
- *Always-maladministration* determination accuracy = **43.0%** (64/149). Both modes
  (33.6 / 34.9) are now *below* this trivial baseline — a direct consequence of R3
  cannibalising the maladministration class (see §2).

¹ 05-23 baseline = `docs/eval/cross_domain_ablation_2026-05-23_FIXED.md`. **Not a clean
A/B** — see §4 confounds. The baseline ran with the control plane *dark* (consumed a
nonexistent sidecar) and without `STREAM_C_PROPOSITION_TAG_FUZZY`. `llm_only`/`rag_only`
rows from that report are unchanged and not re-run here.

---

## 2. Per-class determination recall — the headline question

> *Did `reasonable_redress` (n=21), `severe_maladministration` (n=17),
> `resolved_with_intervention` (n=12) move off 0.0 recall?* **Yes — but at a cost.**

| Gold class (n) | 05-23 recall | hybrid recall | kg_only recall |
|----------------|-------------:|--------------:|---------------:|
| maladministration (64) | high (majority) | **0.297** (19/64) | **0.203** (13/64) |
| service_failure (29) | — | 0.069 (2/29) | 0.172 (5/29) |
| reasonable_redress (21) | **0.00** | **0.810** (17/21) | **0.810** (17/21) |
| severe_maladministration (17) | **0.00** | 0.235 (4/17) | 0.529 (9/17) |
| resolved_with_intervention (12) | **0.00** | 0.417 (5/12) | 0.333 (4/12) |
| outside_jurisdiction (6) | — | 0.500 (3/6) | 0.667 (4/6) |

**Predicted-vs-gold class counts expose the over-firing:**

| Class | gold | hybrid pred | kg_only pred |
|-------|-----:|------------:|-------------:|
| maladministration | 64 | 32 | 19 |
| reasonable_redress | **21** | **76** | **66** |
| severe_maladministration | 17 | 12 | 22 |
| service_failure | 29 | 10 | 22 |
| resolved_with_intervention | 12 | 5 | 4 |
| no_maladministration | 0 | 6 | 11 |
| outside_jurisdiction | 6 | 6 | 5 |

`reasonable_redress` is predicted **3.6×** (hybrid) / **3.1×** (kg) more often than it
occurs. Its recall is high (0.81) but its **precision is ~22%** (17 correct of 76).
Meanwhile `maladministration` — 43% of the gold — collapses to 0.30/0.20 recall.
This trade is why determination accuracy *fell* despite the rare classes appearing:
the machinery surfaces minority classes but is mis-calibrated toward `reasonable_redress`.

**Source of the over-firing (from run logs):**

| Rule | hybrid firings | kg_only firings |
|------|---------------:|----------------:|
| R1_outside_jurisdiction | 1 | 1 |
| R2_severe_upgrade | 4 | 2 |
| **R3_reasonable_redress** | **44** (all → reasonable_redress) | **35** (all → reasonable_redress) |

Of the 76 hybrid `reasonable_redress` predictions, **44 are R3-forced** (the rest come
from the LLM, nudged by the determination guide). R3's predicate
(`prior_compensation_or_apology_offered` present **and** LLM amount ∈ {None, 0}) treats a
missing model amount as evidence of prior redress. But the model routinely returns no
amount and lets the tariff fill it — so R3 fires on ordinary maladministration cases.

---

## 3. Amount distribution sanity + MAE

**LOO baseline recomputed on this 149-gold:** median award = **£500**, mean = £857
(the £437 figure in older notes was on a different/old set). Always-guess-£500 MAE = **£634**.

| Mode | model MAE | signed mean | within £100 | predicted-amount median | distinct values |
|------|----------:|------------:|------------:|------------------------:|----------------:|
| hybrid | **£802** | **−£631** | 17.7% | £0 | 17 |
| kg_only | **£753** | **−£561** | 19.0% | £0 | 19 |
| *always-£500* | *£634* | — | — | £500 | 1 |

**Both modes are worse than the trivial always-£500 guess.** No new *constant* degenerate
(17–19 distinct values, not a single pinned number), so the tariff model itself produces
spread. The failure is the **large negative bias**: the predicted-amount *median is £0*
because 88 (hybrid) / 81 (kg) cases land in a £0 tariff band — and they land there
*because* R3/guide over-routes them to `reasonable_redress` / `no_maladministration`,
both of which the tariff maps to £0. Predicted-amount histogram (hybrid):
`£0 ×88, £350 ×21, £425 ×9, £75 ×5, £2000 ×5, £82 ×4, …`. The amount regression is
therefore **downstream of the determination over-firing**, not an independent tariff bug.

---

## 4. Confound disclosure — which fix caused which delta

All five mechanisms landed in one run, so deltas are **not cleanly attributable**.
What can be said with confidence:

- **kg_only Brier 0.354 → 0.168** is **most likely attributable to the calibration clamp**
  (`adapter._confidence_to_p_landlord` + the citation-cap scope fix). kg_only does not
  retrieve, so factor-constrained retrieval and the citation cap are inert there; the
  clamp is the only *pipeline-logic* change to its probability mapping. **Caveat:** the
  prediction backbone also changed from `gpt-5-mini` (baseline) to `gpt-5.5` (this run) —
  see the fourth confound below — and a different LLM can shift raw confidence
  distributions on its own, so the clamp is the leading but not the sole candidate cause.
- **Determination-accuracy and amount regressions** are attributable to **R3 + the
  determination guide** (the rules/tariff did not exist in the baseline). High confidence
  via the rule-firing logs in §2.
- **Binary-accuracy drop** is **confounded**: `STREAM_C_PROPOSITION_TAG_FUZZY` changed
  the retrieval candidate set vs baseline, *and* the control plane went from dark→active,
  *and* R3 changed determinations (which feed `overall_winner`). Cannot cleanly separate
  retrieval-shift from rule-shift without an ablation.
- **Prediction-model change (uncontrolled covariate):** the baseline cross-domain report
  header says `gpt-5-mini`, while this run used `predict_all.py`'s default **gpt-5.5** for
  prediction (see §5). The backbone model itself differs between baseline and rerun, so
  *every* metric delta here carries an unmodelled model-version component on top of the
  five Tier-1 mechanisms. A clean A/B would hold the prediction model fixed.

**Per-mechanism ablation is now possible** (the flag-coupling bug that previously made
`RULES=0,TARIFF=1` run neither block is fixed — each flag gates only its own block):
- `STREAM_C_DETERMINATION_RULES=0` → isolate the rules' contribution (keeps tariff + guide + calibration).
- `STREAM_C_TARIFF_QUANTUM=0` → isolate the tariff's contribution.
- The recommended next diagnostic is a `RULES=0` rerun: if det-acc and amount MAE recover,
  R3 is confirmed as the sole regression driver and the fix is to tighten (not remove) R3.

---

## 5. Errata

- **2026-05-21 run consumed a nonexistent factor-assertion sidecar** — the control plane
  was dark in that run, so its "hybrid/kg with factors" numbers were actually
  factors-absent. The 05-23 FIXED report inherits this caveat for its factor-bearing modes.
- **Model header mismatch:** the cross-domain report header says `gpt-5-mini`, but the
  housing path uses `predict_all.py`'s default **gpt-5.5** for prediction. This rerun is
  gpt-5.5 for prediction, gpt-5-mini for extraction.
- **`overall_win_probability` is a schema artifact** pinned at 0.5 in the output rows; the
  calibrated signal is `raw_overall_confidence` (hybrid capped at 0.40 by the citation cap
  since hybrid strips all citations at verification, `removal_rate=1.0`; kg_only spans
  0.22–0.78). Scoring uses the adapter's clamped landlord probability, not this field.
- **Sidecar covers 147/149.** Two cases carry no factors and are absent from the
  control plane: `housing-ombudsman-202410423`, `housing-ombudsman-202429736`.
- **Hybrid abstains on 2 cases** (`housing-ombudsman-202511615`,
  `housing-ombudsman-202306436`) — note these are *not* the missing-factor cases above
  (both have factors); their abstention has a different cause (no verified citations
  survived). kg_only abstains on 0.

---

## 6. Mechanism firing counts (from run logs)

| Event | hybrid | kg_only |
|-------|-------:|--------:|
| `determination_rule_applied` (total) | 49 | 38 |
| — R1_outside_jurisdiction | 1 | 1 |
| — R2_severe_upgrade | 4 | 2 |
| — R3_reasonable_redress | 44 | 35 |
| `tariff_quantum_applied` | 144 | 147 |

---

## 7. Recommendation

The calibration fix is a keeper — land it. The determination/tariff machinery is **net
negative as currently tuned** and should not ship to the report's headline numbers until
R3 is corrected. Concretely:

1. **Tighten R3** so it cannot override `maladministration`/`severe_maladministration`.
   R3 should only *confirm* a low-severity LLM determination (no_maladministration /
   service_failure) when a *substantive* prior offer exists — never *promote* a
   maladministration finding to reasonable_redress, and never treat a missing model
   amount as evidence of redress. This alone should restore maladministration recall.
2. **Re-run with `STREAM_C_DETERMINATION_RULES=0`** as a free-of-new-logic diagnostic to
   confirm R3 is the sole regression driver before investing in the R3 rewrite.
3. Keep the calibration clamp and the rare-class guide; both are directionally correct.
