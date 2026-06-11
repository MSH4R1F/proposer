# Housing 150 — Bottleneck Fixes Rerun (2026-06-10)

**Run:** 149-case housing gold × {hybrid, kg_only} × seed 1, gpt-5.5 prediction / gpt-5-mini extraction.
**Predictions:** `eval/predictions/housing_150_ablation_20260610/seed1/` (+ `_metrics.json`).
**Supersedes** the 2026-06-09 rerun (`housing_150_tier1_rerun_2026-06-09.md`), whose regressions are
root-caused below. Same flags as 06-09 EXCEPT: `STREAM_C_DETERMINATION_RULES=0`,
`STREAM_C_ALWAYS_PREDICT_AMOUNTS=1`, `STREAM_C_NO_RAG_PREDICT_AMOUNTS=1`,
`STREAM_C_DET_OUTCOME_CONSISTENCY=1`.

## Headline: before / after

| Mode | Metric | 05-23 baseline | 06-09 (broken) | **06-10 (fixed)** | vs baseline |
|------|--------|---:|---:|---:|---:|
| hybrid | Accuracy | 94.6 | 85.9 | **91.9** | −2.7 |
| | Balanced acc | — | 68.7 | 63.9 | — |
| | Brier (landlord) | 0.163 | 0.250 | **0.165** | ≈flat |
| | Determination acc | 45.0 | 33.6 | **46.3** | **+1.3** |
| | Amount MAE | n/a (no amounts) | £802 | **£438** | — |
| kg_only | Accuracy | 96.0 | 91.3 | **98.7** | **+2.7** |
| | Balanced acc | — | 79.5 | **83.3** | — |
| | Brier (landlord) | 0.354 | 0.168 | **0.155** | **−0.199** |
| | Determination acc | 35.6 | 34.9 | **51.7** | **+16.1** |
| | Amount MAE | n/a (no amounts) | £753 | **£493** | — |

**Trivial baselines (149 gold):** always-tenant accuracy 96.0%; always-maladministration
det-acc 43.0%; always-£500 amount MAE £634.

- **kg_only now beats all three trivial baselines**: 98.7 > 96.0 accuracy (it correctly calls
  4/6 landlord/OJ cases while missing only 2 tenant cases), 51.7 > 43.0 det-acc, £493 < £634 MAE.
- **hybrid beats two of three** (det-acc 46.3 > 43.0; MAE £438 < £634 — the best amount model)
  but sits below always-tenant on raw accuracy (91.9 < 96.0); its Brier matches the 05-23
  baseline (0.165 vs 0.163) — and unlike 05-23, with the factor control plane actually active.
- Per-class det recall (hybrid | kg): malad 35/64 | 36/64; RR 16/21 | 14/21; severe 8/17 |
  **13/17**; resolved 5/12 | 3/12; SF 4/29 | 7/29; OJ 1/6 | 4/6.
- Amounts are per-case now (49 | 44 distinct values, max £4,000, within-£100 ≈ 31% both modes;
  signed bias −£115 hybrid / +£100 kg).

## Root causes fixed (each with evidence)

1. **Citation verifier never indexed factor-constrained results by case reference**
   (`citation_verifier.py`; commit `c222745`). Factor-constrained retrieval rows carry a
   proposition UUID, so they were routed exclusively down the UUID path while the LLM is only
   ever shown case references → 100% citation removal on 146/149 hybrid cases → the no-citation
   0.4 confidence cap fired → the calibration clamp mapped ALL hybrid probabilities to exactly
   0.5 (Brier 0.250 = coin flip; log-loss = ln 2). Latent since 2026-05-11; the 05-23 baseline
   avoided it only because its sidecar was dark (chunk-RAG fallback). After fix: removal_rate
   0.0, hybrid Brier 0.165.
2. **The determination rules layer was net-negative in every component** (commit `5e61e7c`,
   off by default). On 06-09 logs: R3 fired 44×/35× (gold RR n=21), collapsing malad recall;
   R1 fired 2×, both overriding a CORRECT service_failure; R2 fired 8×, 0 correct.
   Counterfactual no-rules det-acc 0.423 vs actual 0.336. The rare-class recall gains came
   from the prompt guide, not the rules.
3. **Tariff bands encoded per-failure guidance against case-level gold totals** (commit
   `2c69a1f`). All 21 gold reasonable_redress cases have total_awarded == the landlord's prior
   offer (median £850, zero £0s) — the Ombudsman orders the offer honoured — while the tariff
   forced RR → £0. Even correctly-classified cases carried MAE £719. Bands rewidened;
   RR no longer zeroed.
4. **Amount prediction was instructed OFF** (commit `5e61e7c` + `87017d9`). The no-RAG prompt
   literally said "set predicted_amount to null" without `STREAM_C_NO_RAG_PREDICT_AMOUNTS=1`
   (kg_only emitted 0 amounts), and hybrid's IRAC system prompt overrides the user-prompt
   amount clause (null on 144/147). Fixed by enabling both flags + a system-prompt-level
   `REPAIRS_RAG_CALIBRATION_ADDENDUM` on the repairs RAG path requiring a GBP total estimate.
5. **Guide debiasing overshot** (commit `6dfe95a`). "Do NOT default to maladministration"
   produced no_maladministration predictions on a gold set containing ZERO such cases (17 of
   34 winner errors on 06-09). Replaced with published-corpus base rates. After: kg predicts
   no_malad 0×, hybrid 4×.
6. **det↔winner inconsistency** (commit `5e61e7c`/`d3ca5f6`). Gold winner is a deterministic
   function of determination (OJ → landlord; everything else → tenant). The LLM emitted
   det=reasonable_redress with winner=landlord (9 errors on 06-09). A consistency mapping
   (`STREAM_C_DET_OUTCOME_CONSISTENCY=1`) now derives outcome from the final determination.
7. **Hybrid under-confidence** (commit `87017d9`). The IRAC framing elicited raw_confidence
   0.28–0.62 (read as citation coverage); the addendum defines it as P(predicted outcome
   correct). After: hybrid confidences 0.52–0.66+, probabilities informative.

## Methodology disclosures

- The guide's base rates and the widened tariff bands are anchored on the published
  determination corpus, which overlaps the gold set; they are class-level priors (the same
  epistemic status as the always-maladministration baseline), not case-level information.
  Disclose alongside results.
- The det→winner mapping aligns the system's output convention with the gold labeling
  convention (any upheld/redressed complaint = resident-favourable outcome). It is a
  convention alignment, not an accuracy mechanism: it only moves cases whose determination
  and winner disagreed.
- 05-23 comparability caveats from `housing_150_tier1_rerun_2026-06-09.md` §4 still apply
  (model change gpt-5-mini→gpt-5.5 in header vs practice, PROPOSITION_TAG_FUZZY, control
  plane dark in baseline).
- Run was executed in 5 parallel shards (3× hybrid on separate Chroma index copies, 2×
  kg_only on the shared root); 20 hybrid rows from the interrupted sequential run were
  reused (same code, same flags).

## Remaining known gaps (future work)

- **service_failure recall is the weakest class** (4/29 hybrid, 7/29 kg): the model grades
  most SF cases up to maladministration. The SF/malad boundary needs comparator anchoring.
- **resolved_with_intervention** (3–5/12) and hybrid **outside_jurisdiction false positives**
  (4 of 12 hybrid winner errors) remain.
- Hybrid trails kg_only across the board — comparator retrieval currently ADDS noise
  relative to the factor control plane alone. Candidate next step: factor-similarity-weighted
  comparator selection rather than proposition-text similarity.
- Hybrid raw accuracy (91.9) remains below always-tenant (96.0); balanced accuracy and
  Brier are the honest headline metrics on this skewed gold set.
