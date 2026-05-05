# Housing Ombudsman 50-Case Failure Taxonomy (2026-05-05, post-patch)

Run: `housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5_full_eval`
Gold: `data/gold_standard/housing_repairs_social_v1.jsonl`
Predictions: `eval/predictions/housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5/{hybrid,rag_only,kg_only,llm_only}.jsonl`

All numbers below were recomputed from the JSONL artifacts; no metric was invented.

---

## A. Setup and counts

- **N total cases:** 50
- **Gold winner distribution:** tenant=49, landlord=1, split=0 (no split-winner cases in gold)
- **Gold amount coverage:** 50/50 cases have a `total_awarded_gbp`. Distribution (£): min=0.00, median=500.00, p75=960.00, p90=1500.00, max=3818.00. Two cases have £0 awarded (one of which is the lone landlord-win); 9 cases sit in £1000+.
- **Gold structure:** every case is *unapportioned* (`per_issue=[]` with `unapportioned_reason` set — Housing Ombudsman issues a global compensation order). Scoring therefore collapses to one comparison per case using `overall_winner` / `overall_win_probability`, per `docs/eval/metrics.md` §"Apportioned vs unapportioned".

| Mode | n preds | winner present | proba present | amount non-null | amount non-zero |
|---|---|---|---|---|---|
| hybrid | 50 | 50 | 50 | 50 | 29 |
| rag_only | 50 | 50 | 50 | 50 | 31 |
| kg_only | 50 | 50 | 50 | 50 | 0 |
| llm_only | 50 | 50 | 50 | 50 | 0 |

**Citations / retrieved-chunk text:** none of the prediction JSONL rows nor the per-case run artifacts under `data/eval_artifacts/runs/housing_ombudsman_stratified_50_live_20260505_post_patch_topk5_sharded5/*.json` carry citation, evidence-id, or chunk-text fields. The schema observed across all 200 per-case files is `{run_id, case_id, mode, context, result_hash, prediction}` only. Section E therefore uses observable proxies (abstained flag, predicted amount = 0) rather than verified-citation counts; this is called out explicitly there and is a real artifact-coverage gap.

---

## B. Mode-level metrics beyond accuracy

### Definitions used

- **Accuracy:** fraction of cases where `prediction.overall_winner == gold.ground_truth_outcome.overall_winner`.
- **Macro-F1 (3-class):** unweighted mean of F1 over labels {tenant, landlord, split}; F1 = 2·P·R/(P+R) with the usual TP/FP/FN counts. The 4-class variant adds {uncertain}, but the prompt collapses uncertain → split before emission, so it differs only in the support of the extra zero term.
- **Balanced accuracy:** macro-average recall over labels present in gold (so {tenant, landlord} here).
- **Abstention rate:** fraction with `abstained=True` (also flagged when `raw_overall_outcome == 'uncertain'`).
- **Abstention-adjusted accuracy:** accuracy on the non-abstained subset only.
- **Reliability bucket b:** cases whose `overall_win_probability` falls in `[b/5, (b+1)/5)`; empirical accuracy = correct/total in bucket.

### Hybrid (n=50)

- accuracy = 34/50 = **0.680**
- macro-F1 (3-class tenant/landlord/split) = **0.273**
- macro-F1 (4-class incl. uncertain) = **0.205** (uncertain has zero gold support, so adds a 0 term)
- balanced accuracy = (recall_tenant + recall_landlord)/2 = (0.694 + 0.000)/2 = **0.347**
- recall: tenant=34/49=0.694, landlord=0/1=0.000
- abstention rate = 15/50 = **0.300** (all 15 emit `overall_winner='split', proba=0.5, raw='uncertain'`)
- abstention-adjusted accuracy = 34/35 = **0.971**
- mean confidence | correct = **0.487** (n=34); mean confidence | incorrect = **0.494** (n=16) — *no resolution*: confidence does not separate right from wrong.
- Confidence histogram (5 bins, equal-width on [0,1]):

| bin | count |
|---|---|
| [0.0, 0.2) | 0 |
| [0.2, 0.4) | 8 |
| [0.4, 0.6) | 28 |
| [0.6, 0.8) | 14 |
| [0.8, 1.0] | 0 |

- Reliability table (predicted-prob bucket → empirical accuracy on tenant/landlord/split label):

| bucket | correct/total | empirical acc |
|---|---|---|
| [0.0, 0.2) | 0/0 | n/a |
| [0.2, 0.4) | 8/8 | 1.00 |
| [0.4, 0.6) | 12/28 | **0.43** |
| [0.6, 0.8) | 14/14 | 1.00 |
| [0.8, 1.0] | 0/0 | n/a |

The 0.4–0.6 bin is the entire problem: 28 cases (15 abstain at p=0.5, plus 13 low-confidence tenant calls). Of these 28, only 12 are scored correct. Both the [0.2, 0.4) and [0.6, 0.8) bins are perfectly correct — when hybrid steps away from p≈0.5 in either direction it is right every time.

### rag_only (n=50)

- accuracy = 35/50 = **0.700**
- macro-F1 (3-class) = **0.278**; (4-class) = 0.208
- balanced accuracy = (0.714 + 0.000)/2 = **0.357**
- recall: tenant=35/49=0.714, landlord=0/1=0.000
- abstention rate = 14/50 = **0.280**
- abstention-adjusted accuracy = 35/36 = **0.972**
- mean confidence | correct = 0.466; mean confidence | incorrect = 0.501. Same null resolution as hybrid.
- Confidence histogram: [0,8,32,10,0]. Reliability:

| bucket | correct/total | empirical acc |
|---|---|---|
| [0.2, 0.4) | 8/8 | 1.00 |
| [0.4, 0.6) | 17/32 | **0.53** |
| [0.6, 0.8) | 10/10 | 1.00 |

### kg_only (n=50)

100% of rows: `overall_winner='split'`, `overall_win_probability=0.5`, `total_predicted_gbp='0'`, `raw_overall_outcome='uncertain'`, `abstained=True`. The mode is essentially a no-op stub: it abstains on every case. Accuracy is 0.00 because no gold case has winner=`split`. Brier=0.25, ECE=0.48 are exactly what (p=0.5, 0/1) gives. This is not a model that "predicts wrong" — it produces no usable signal at all on this dataset.

### llm_only (n=50)

Identical row-by-row to kg_only on this slice: every prediction is `split / 0.5 / £0 / uncertain / abstained=True`. Same conclusion: it abstains universally, so 0 accuracy is mechanical, not adversarial.

This means the headline numbers are produced entirely by the rag and the rag+kg fusion paths — kg_only and llm_only contribute no predictions other than abstain on this slice.

---

## C. Hybrid vs rag_only divergence

- **Agree on overall_winner:** 43/50
- **Agree on total_predicted_gbp:** 26/50 (so they diverge on amount in 24/50 even when winner agrees in 19 of those 24)
- **Hybrid wrong AND rag right (4):** `housing-ombudsman-202413497`, `housing-ombudsman-202442504`, `housing-ombudsman-202508050`, `housing-ombudsman-202404522` — in every one, hybrid emits `split`/abstain while rag_only stays with `tenant`.
- **Hybrid right AND rag wrong (3):** `housing-ombudsman-202513245`, `housing-ombudsman-202421521`, `housing-ombudsman-202427803` — in every one, rag_only emits `split`/abstain while hybrid stays with `tenant`. So abstention-flips run in both directions; the net is rag_only wins by 1 case (4 vs 3).
- Mean confidence delta (hybrid − rag) on agreement: **+0.011** (n=43); on disagreement: **+0.024** (n=7). The two modes are within ~0.02 of each other on every regime — KG fusion is *not* meaningfully changing magnitudes.

### What does KG fusion appear to do?

On this slice, fusion does *not* push toward landlord (only 1 hybrid landlord prediction, same as rag) and does *not* dilute tenant confidences (mean delta is +0.01, not negative). The visible effect is **flipping borderline cases between tenant and split in both directions**, with a slight net loss. Operationally, hybrid abstains on a different 15-case subset than rag_only's 14-case subset, and the symmetric-difference (cases where the two modes disagree on whether to abstain) is the entire 7-case divergence pool. This is consistent with the kg_only signal being "uncertain on every case" — it can only nudge borderline rag tenant calls into abstain or vice versa, and the nudge is essentially noise.

---

## D. Amount errors (hybrid)

### Aggregate (recomputed from JSONLs; matches `summary.json` `modes.hybrid.amount`)

- mean abs err = **£520.4**
- median abs err = £350.0
- p90 abs err = £1290.0
- mean signed err = **−£466.4** (under-prediction bias)
- 40/50 predictions are below gold (mean undershoot among those = £616.7); 4/50 are above gold; 6/50 match gold exactly
- **predicted amount = £0 while gold > £0:** **20/50** cases (= 40% of the eval set). Full list: 202427949, 202409223, 202509252, 202413497, 202508313, 202513245, 202410423, 202429736, 202430026, 202316658, "2022225 48", 202401431, 202442504, 202508050, 202404522, 202410679, 202412991, 202413845, 202325309, 202509792.
- **No prediction exceeds £1000.** Predicted amount maxes out at £1000 (1 case). Yet gold has 9 cases ≥£1000 (max £3818). The amount distribution is structurally truncated.

### Bucket comparison (gold vs hybrid pred)

| band | gold | hybrid pred |
|---|---|---|
| £0 | 2 | 21 |
| £1–100 | 4 | 0 |
| £101–250 | 5 | 7 |
| £251–600 | 21 | 21 |
| £601–1000 | 9 | 1 |
| £1000+ | 9 | 0 |

rag_only buckets are very similar (19 / 0 / 6 / 24 / 1 / 0). Hybrid actually has *one more* zero-predicted case than rag (21 vs 19) — that is the entire amount-MAE gap (£520 vs £539 — these are within bootstrap CI of each other).

The dominant pattern: **hybrid almost never predicts in the >£600 range** (only 1 of 50). It pulls everything into either £0 (when uncertain) or £251–600 (a tight modal cluster). This cannot be a retrieval-precision bug alone; it looks like the prompt or extractor is capped or anchored on a "typical small remedy" and never reaches the higher Ombudsman bands.

### |err| > £200 cases (34/50)

```
202451564 gold=575   pred=1000  +425   (rare overshoot)
202427949 gold=400   pred=0     -400
202332678 gold=1000  pred=500   -500
202409223 gold=600   pred=0     -600
202511615 gold=0     pred=300   +300
202445527 gold=1000  pred=500   -500
202509252 gold=700   pred=0     -700
202331162 gold=540   pred=200   -340
202446687 gold=1000  pred=500   -500
202413497 gold=550   pred=0     -550
202508313 gold=350   pred=0     -350
202408056 gold=1440  pred=150   -1290
202513245 gold=550   pred=0     -550
202348669 gold=1010  pred=600   -410
202421521 gold=540   pred=150   -390
202429736 gold=350   pred=0     -350
202441018 gold=500   pred=200   -300
202428538 gold=3818  pred=400   -3418
202430026 gold=441   pred=0     -441
"2022225 48" gold=650 pred=0    -650
202407044 gold=950   pred=600   -350
202432454 gold=650   pred=400   -250
202401431 gold=250   pred=0     -250
202508050 gold=450   pred=0     -450
202506211 gold=1500  pred=600   -900
202334890 gold=2137  pred=400   -1737
202339075 gold=1345  pred=400   -945
202427803 gold=650   pred=250   -400
202410679 gold=350   pred=0     -350
202413845 gold=250   pred=0     -250  (also winner-wrong)
202409957 gold=2431  pred=300   -2131
202509792 gold=1500  pred=0     -1500
202440462 gold=1900  pred=400   -1500
202340236 gold=960   pred=600   -360
```

33/34 are undershoots; only `202451564` overshoots and `202511615` is a £0-gold-but-£300-pred (pure FP).

### Among hybrid-correct-on-winner cases (n=34): how good is amount?

- within £100 of gold: **5/34 (15%)**
- within 20% of gold: **4/34 (12%)**

So even on the cases where hybrid is right about *who wins*, it is essentially never right about *how much*. The amount head is failing independently of the winner head.

### Citation/remedy retrieval (proxy)

We cannot inspect retrieved chunks (they are not in artifacts). The proxy: of the 16 incorrect winner predictions, **16/16 emit predicted amount = £0**. Of the 15 abstain rows, **15/15 emit amount = £0**. These two sets overlap heavily — abstention and zero-amount are the same failure surfacing twice. So in roughly half the eval set the model is producing no usable amount at all, which is consistent with retrieval not surfacing a remedy/order paragraph (or the extractor not finding one).

---

## E. Citation quality (proxies only — no citation field in artifacts)

The prediction JSONLs and per-case run artifacts contain no `citations`, `evidence`, `retrieved_chunks`, or chunk-metadata fields. The keys present in `prediction` are exactly: `case_id, overall_winner, overall_win_probability, total_predicted_gbp, per_issue, raw_overall_outcome, raw_overall_confidence, abstained` (verified across all 50 hybrid case files). I cannot quantify "verified citations per case" or "fraction of chunks that are remedy/order vs issue-summary" from these files. The numbers below are confidence=approximate proxies built only from the abstained flag and the predicted-amount field; they should not be quoted as citation metrics.

| signal | hybrid | rag_only |
|---|---|---|
| incorrect predictions | 16 | 15 |
| of which `abstained=True` | 15 | 14 |
| of which confidently wrong (pred ≠ gold and not abstained) | 1 | 1 |
| of incorrect, predicted £ = £0 | 16/16 | (similar — see rag amount bucket) |

The one confidently-wrong case is `housing-ombudsman-202413845` for hybrid (predicted `landlord` at p=0.4) and the same case for rag_only (predicted `landlord` at p=0.52) — both modes pick the same wrong winner here, suggesting it is a retrieval/data issue not a fusion issue. This is a *mislabelling-not-modelling* candidate worth a manual gold review.

To quantify true citation quality the run will need to start emitting the chunk IDs / verifier output (the `verifier_hash` in `context.verifier_hash` suggests the verifier ran but its output is not persisted alongside predictions).

---

## F. Representative case table

| case_id | gold_winner | gold_amount | hybrid_pred | hybrid_amount | hybrid_proba | hybrid_citations | rag_pred | rag_amount | rag_citations | failure_type | likely_fix |
|---|---|---|---|---|---|---|---|---|---|---|---|
| housing-ombudsman-202427949 | tenant | 400 | split | 0 | 0.50 | n/a | split | 0 | n/a | winner_abstain | decompose_query |
| housing-ombudsman-202413497 | tenant | 550 | split | 0 | 0.50 | n/a | tenant | 500 | n/a | winner_abstain (hyb only) | kg_ledger_format |
| housing-ombudsman-202442504 | tenant | 175 | split | 0 | 0.50 | n/a | tenant | 500 | n/a | winner_abstain (hyb only) | kg_ledger_format |
| housing-ombudsman-202413845 | tenant | 250 | landlord | 0 | 0.40 | n/a | landlord | 0 | n/a | winner_confident_wrong | rubric_map_to_labels |
| housing-ombudsman-202428538 | tenant | 3818 | tenant | 400 | 0.60 | n/a | tenant | 400 | n/a | amount_band_wrong | award_band_classifier |
| housing-ombudsman-202409957 | tenant | 2431 | tenant | 300 | 0.44 | n/a | tenant | 300 | n/a | amount_band_wrong | award_band_classifier |
| housing-ombudsman-202440462 | tenant | 1900 | tenant | 400 | 0.60 | n/a | tenant | 400 | n/a | amount_band_wrong | award_band_classifier |
| housing-ombudsman-202506211 | tenant | 1500 | tenant | 600 | 0.36 | n/a | tenant | 500 | n/a | amount_undershoot | add_remedy_pass |
| housing-ombudsman-202513245 | tenant | 550 | tenant | 0 | 0.44 | n/a | split | 0 | n/a | amount_null (hyb correct on winner) | add_remedy_pass |
| housing-ombudsman-202421521 | tenant | 540 | tenant | 150 | 0.60 | n/a | split | 0 | n/a | amount_undershoot (hyb beats rag on winner) | liability_remedy_split |
| housing-ombudsman-202509792 | tenant | 1500 | tenant | 0 | 0.42 | n/a | tenant | 600 | n/a | amount_null + citation_empty | add_remedy_pass |
| housing-ombudsman-202325309 | tenant | 50 | split | 0 | 0.50 | n/a | split | 0 | n/a | citation_empty (proxy) | relax_citation_match |
| housing-ombudsman-202306436 | landlord | 0 | split | 0 | 0.50 | n/a | split | 0 | n/a | kg_overconservative (lone landlord case) | rubric_map_to_labels |

`hybrid_citations` / `rag_citations` show `n/a` because the artifacts do not carry per-case citation lists (see Section E).

---

## G. What scoring choice changes the picture?

### Treat `uncertain` (= the `split` emissions where `abstained=True`) as abstention rather than a wrong tenant call

- hybrid: 15 cases removed from the denominator → **34/35 = 0.971** abstention-adjusted accuracy.
- rag_only: 14 removed → **35/36 = 0.972**.

Under this scoring, the two modes are statistically indistinguishable (difference of one case). The *only* meaningful difference between hybrid and rag on this slice is **how often each one decides to abstain** (15 vs 14 cases) and *which* cases each abstains on (4 hybrid abstains where rag answered correctly, vs 3 rag abstains where hybrid answered correctly).

### Macro-F1 / balanced accuracy comparison

| mode | accuracy | macro-F1 (3-class) | balanced acc |
|---|---|---|---|
| hybrid | 0.680 | 0.273 | 0.347 |
| rag_only | 0.700 | 0.278 | 0.357 |
| always_tenant | **0.980** | **0.495** | **0.500** |

`always_tenant` dominates on every metric on this slice — accuracy, macro-F1, and balanced accuracy. This is a direct artifact of the 49/1 class imbalance: there is no minority class to learn from (1 landlord, 0 split), so a constant-tenant predictor is near-optimal. The 50-case Housing Ombudsman slice cannot, by itself, distinguish a working model from a degenerate one. This is consistent with the dataset audit's `is_clean=false` flag and the methodology note (`docs/eval/metrics.md` §"Deterministic Baselines": "If a model only beats weak baselines because the gold set is skewed […] the eval is telling us the dataset/prediction inputs are too easy or leaky").

The Brier/ECE numbers tell the calibration story differently: hybrid Brier=0.247, rag Brier=0.234, always_tenant Brier=0.02. Always-tenant wins Brier too — but only because of the imbalance. The 0.4–0.6 bucket (cases where hybrid hovers around p=0.5) is what drives Brier and ECE up; nothing else does.

---

## H. Top-5 takeaways

1. **Hybrid never confidently mispredicts a winner — it abstains 15 times.** All 15 hybrid winner-incorrect cases are `split / p=0.5 / abstained=True / amount=£0`. The single non-abstain wrong call (`housing-ombudsman-202413845`, predicted `landlord` at p=0.4) is also wrong on rag_only — so it looks like a data/labelling case, not a fusion bug. The "hybrid loses to rag_only" gap (0.68 vs 0.70) is **one extra abstention** (15 vs 14) on a slightly different 7-case symmetric-difference set, not a systematic regression. Treating uncertain as abstention collapses the gap to 0.971 vs 0.972 (≈ noise on n=50).

2. **The amount head is broken independently of the winner head.** Of 34 cases where hybrid is correct on winner, only 5 are within ±£100 and 4 within ±20%. Hybrid never predicts above £1000, but 9/50 gold cases are ≥£1000 and the max gold is £3818. The prediction distribution clusters in £0 (21/50) or £251–600 (21/50) with everything else essentially absent. This is structural — likely the remedy/order extractor not surfacing high-value paragraphs (cases like `202428538` £3818, `202409957` £2431, `202440462` £1900, `202334890` £2137, `202509792` £1500). Fixes that only improve retrieval ranking will not close the band gap; an explicit award-band step or remedy-paragraph pass is needed.

3. **kg_only and llm_only are no-op stubs on this slice.** All 50 rows for both modes are `split / 0.5 / £0 / uncertain / abstained=True`. Their 0% accuracy is mechanical (gold has no `split` label) and they contribute no signal. Reporting them in the headline as "RAG+KG > KG alone" misrepresents the comparison: kg_only does not produce any predictions to compare against on this run. This needs to be called out in any thesis-facing figure.

4. **always_tenant beats hybrid on every classification metric on this slice (0.98 vs 0.68 acc; 0.495 vs 0.273 macro-F1; 0.500 vs 0.347 balanced acc).** This is *the* dataset-quality finding. Until the slice contains real landlord-win and split cases (currently 1 and 0 respectively), this 50-case eval cannot adjudicate whether the model is good. Gold expansion to include landlord-favourable Ombudsman determinations is a hard prerequisite for any honest accuracy claim. Brier/ECE follow the same pattern.

5. **The 4 "hybrid wrong, rag right" cases (`202413497, 202442504, 202508050, 202404522`) are all hybrid-abstain → rag-tenant.** Mean confidence delta on disagreement is +0.024 (essentially zero), so KG fusion is not pulling answers toward landlord — it is pulling tenant calls into abstain at p=0.5 for ~4 out of 50 cases. A targeted fix is the abstention-trigger logic in the KG fusion step (when the KG signal is "uncertain on every case" as it is here, it should not be allowed to flip a confident rag tenant into split). This is **local**: one decision rule. The amount band gap (finding 2) and the dataset balance (finding 4) are **structural** and need new components / new data.
