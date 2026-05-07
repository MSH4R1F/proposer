# Stream C — Forced-Answer Recovery Ablation (2026-05-07)

## TL;DR

After landing the four recovery patches (T2 empty-card suppression, T3 validator audit-only + confidence cap, T4 forced-answer mode, T5 metadata serialisation regression test), I re-ran the same 48 housing.repairs_social.v1 cases × 4 modes against Claude Sonnet, in a single clean launch with all flags on.

**Headline:** hybrid 0.917 [0.833, 0.979] vs rag_only 0.896 [0.812, 0.979]. The 21pp deficit from the [original 2026-05-07 ablation](stream-c-ablation-2026-05-07.md) flipped to a **+2.1pp surplus**. Abstention rate is **0% across all four modes** — forced-answer worked exactly as intended. `kg_only` and `llm_only` jumped from ~32% accuracy to 0.854/0.875, confirming that **the abstention pathology was the dominant cause of the original low accuracy, not a model deficiency**.

But the result is loaded with caveats and three sit at the centre of any honest interpretation:

1. **The +2.1pp delta is the smallest measurable improvement on this corpus.** With n=48 and 47/48 gold cases being tenant-wins, each correct call is worth 1/48 = 2.08pp. Hybrid beats rag_only by exactly 1 case. CIs overlap heavily.
2. **Hybrid wins on raw and balanced accuracy and macro F1 but loses on ECE and Brier** — by ~1pp. The loss is a "good model, bad confidence" pattern: hybrid is more accurate at the same confidence level, so its calibration gap is larger. All four modes are severely under-confident on this corpus (predicting ~0.5 on cases that are ~95% correct). This is a calibration-layer problem, not an architectural one.
3. **The KG path never lit up.** `kg_used_for_prediction=False` on every hybrid row because the gold corpus has no factor data populated — the FactorRetriever falls back to chunk-RAG on every case. **Hybrid's lead is therefore NOT a graph-augmentation win.** It comes from the FACTOR_CONSTRAINED routing producing a richer retrieval payload than direct `chunk_rag` (mean retrieved: 2.9 vs 2.7; mean cases analysed: 6.8 vs 4.1). That's a real engineering improvement from the routing layer, but it's not the architectural novelty the thesis is about.

**Decision per the recovery plan:**
- **Gate 2 (fallback parity):** ✓ achieved. With no KG data, hybrid ≥ rag_only on accuracy.
- **Gate 3 (KG positive-control wiring):** ✓ achieved in Task 7 — see [`test_positive_control_kg_smoke.py`](../../packages/llm_orchestrator/tests/test_positive_control_kg_smoke.py).
- **Gate 4 (multi-axis hybrid signal):** **partially met** — wins on accuracy / balanced accuracy / macro F1, loses on ECE and Brier, no win on citation validity / evidence support (KG never fired). The defensible claim is fallback parity + routing improvement, not KG-augmentation lift.

The empirical chapter goes from "negative result" to "fallback-parity-plus" rather than from "negative" to "positive". Real architectural lift requires factor-data backfill, which the positive-control fixture in commit `9352517` proves the pipeline activates correctly on.

---

## Side-by-side: original ablation vs recovery ablation

| Mode | Acc (original) | Acc (recovery) | Δ | Abstention (orig) | Abstention (rec) |
|---|---|---|---|---|---|
| **hybrid** | 0.625 [0.479, 0.771] | **0.917** [0.833, 0.979] | **+0.292** | 0.333 | 0.000 |
| rag_only | 0.833 [0.729, 0.938] | 0.896 [0.812, 0.979] | +0.063 | 0.125 | 0.000 |
| kg_only | 0.312 [0.188, 0.458] | 0.854 [0.750, 0.938] | +0.542 | 0.667 | 0.000 |
| llm_only | 0.333 [0.208, 0.479] | 0.875 [0.771, 0.958] | +0.542 | 0.646 | 0.000 |

The 50–55pp jumps in `kg_only` and `llm_only` are the loudest signal that the original ablation was measuring abstention, not capability. Once forced to answer, those modes reach 0.85–0.88 — comparable to the retrieval-augmented modes — because most cases have a strong textual signal even unaided LLM can lean on.

The hybrid + rag_only direction reversed (rag_only used to be 21pp ahead; hybrid is now 2.1pp ahead), but the delta is small and the multi-axis story below adds context.

`covered_accuracy` tells the more honest story: 0.938 (original hybrid) → 0.917 (recovery hybrid). Forced-answer commits on borderline cases that the prior runs could abstain on, and gets a few of them wrong — so per-decision quality on confident answers is _slightly worse_ under forced-answer than under abstention. The trade-off is intentional: every case now produces a gold-comparable label, which is the prerequisite for the multi-axis evaluation the recovery sprint was designed to enable.

---

## Multi-axis recovery results

| Mode | Accuracy | Macro F1 | Balanced Acc. | ECE | Brier | Covered Acc. | Abstention | Det. Acc. |
|---|---|---|---|---|---|---|---|---|
| **hybrid** | **0.917** | **0.644** | **0.957** | 0.466 | 0.241 | 0.917 | 0.000 | 0.438 |
| rag_only | 0.896 | 0.615 | 0.947 | **0.456** | **0.234** | 0.896 | 0.000 | **0.500** |
| kg_only | 0.854 | 0.571 | 0.926 | 0.545 | 0.335 | 0.854 | 0.000 | 0.271 |
| llm_only | 0.875 | 0.591 | 0.936 | 0.561 | 0.342 | 0.875 | 0.000 | 0.271 |
| _baseline_ `always_tenant` | _0.979_ | _0.495_ | _0.500_ | _0.021_ | _0.021_ | _0.979_ | 0.000 | _0.000_ |

**Bold** = best non-baseline value per column. The `always_tenant` baseline outperforms all four model variants on raw accuracy because the corpus is heavily class-imbalanced (47/48 tenant-wins); balanced accuracy and macro F1 are the meaningful headlines for ranking the modes.

**What hybrid wins on:**
- Accuracy +2.1pp
- Balanced accuracy +1.0pp
- Macro F1 +2.9pp

**What rag_only wins on:**
- ECE −1.0pp (hybrid worse)
- Brier −0.7pp (hybrid worse)
- Determination accuracy +6.2pp (hybrid worse)
- amount@GBP100 +2.1pp (hybrid worse, but n smaller)

CIs on the winner-level metrics overlap fully. On a 48-case corpus, only ECE and Brier (which have tight CIs because they're per-case scoring rules) read as cleanly separated.

---

## Investigation #1: ceiling on this corpus

Gold-class distribution: tenant=47, landlord=1, split=0, n=48. The smallest measurable accuracy delta on this corpus is `1/48 = 2.08pp`. Hybrid's +2.1pp lead is exactly that — one case.

The constant-predictor baseline `always_tenant` scores 0.979 (47/48). Any non-trivial model has to do better than that to clear the baseline. None of the four modes do — they all over-predict landlord on borderline tenant cases:

| Mode | tenant→landlord errors |
|---|---|
| hybrid | 4 |
| rag_only | 5 |
| llm_only | 6 |
| kg_only | 7 |

What this tells us: **this corpus is too imbalanced to be a reliable benchmark for accuracy comparisons between hybrid and rag_only.** A balanced corpus with ~equal tenant/landlord/split representation, or a much larger corpus, would make the architectural comparison interpretable. With n=48 and 47/48 tenant-wins, the experiment is more a stress-test of "does the new architecture avoid making mistakes" than "does it do something a chunk-RAG baseline can't."

---

## Investigation #2: why ECE / Brier are slightly worse on hybrid

Confidence-bucket histograms (raw_overall_confidence binned into 5 buckets [0–.2, .2–.4, .4–.6, .6–.8, .8–1]):

| Mode | [0–.2] | [.2–.4] | [.4–.6] | [.6–.8] | [.8–1] | mean |
|---|---|---|---|---|---|---|
| hybrid | 0 | 3 | 43 | 2 | 0 | 0.496 |
| rag_only | 0 | 2 | 44 | 2 | 0 | 0.506 |
| kg_only | 0 | 13 | 35 | 0 | 0 | 0.382 |
| llm_only | 0 | 15 | 33 | 0 | 0 | 0.383 |

The dominant bucket for hybrid and rag_only is `[.4–.6]` (43 and 44 cases respectively) — the modes commit at ~0.5 confidence on the vast majority of cases. Bucket-level accuracy in that bucket:

- **hybrid [.4–.6]:** n=43, accuracy = **0.977** (predicted ~0.5 confidence; calibration gap = 0.977 − 0.50 = **0.477**)
- **rag_only [.4–.6]:** n=44, accuracy = 0.932 (predicted ~0.5 confidence; calibration gap = 0.932 − 0.50 = 0.432)

Both modes are massively under-confident — they predict ~50% confidence on cases that are 93–98% correct. **That's why ECE is ~0.46 across the board.** It's a corpus-level under-confidence problem, not a Stream-C-specific defect.

The reason hybrid's ECE is slightly worse than rag_only's: hybrid is **more accurate** at the same average confidence. When a model gets more correct calls into the same low-confidence bucket, the gap between predicted-confidence (0.5) and actual-bucket-accuracy (0.98) widens. So hybrid's "good model, bad confidence" pattern is _more pronounced_ than rag_only's, and ECE penalises it for that.

This is a calibration-layer fix (temperature scaling, isotonic regression, prompt-side confidence-elicitation revision), not an architectural one. A 1pp ECE gap between two modes that are both ~0.46 is within noise; both modes need calibration work irrespective of which is in front.

---

## Investigation #3: what's actually different between hybrid and rag_only when the KG is inert

`pipeline_metadata` audit:

| Mode | `kg_used_for_prediction` | `retrieval_strategy` | `evidence_support` | unsupported_claims | forced-answer fallbacks |
|---|---|---|---|---|---|
| hybrid | `False` × 48 | `factor_constrained` × 48 | `None` × 48 | 0 | 0 |
| rag_only | `False` × 48 | `chunk_rag` × 48 | `None` × 48 | 0 | 0 |
| kg_only | `False` × 48 | `chunk_rag` × 48 | `None` × 48 | 0 | 0 |
| llm_only | `None` × 48 | `chunk_rag` × 48 | `None` × 48 | 0 | 0 |

The KG never fires. `evidence_support=None` everywhere because no `OutcomeComponent`s are constructed (gated on factor data being present). `forced_answer_fallbacks=0` means the LLM always picked a real outcome — the schema-side instruction was sufficient on its own; the post-process safety net never engaged.

So why does hybrid out-perform rag_only by 1 case if both eventually call `_retrieve_chunk_rag`? **Retrieval payload size.** Even though both modes route through chunk-RAG content under the hood, hybrid's FACTOR_CONSTRAINED routing produces a richer downstream payload:

| Mode | Mean retrieved cases | Distribution | Mean total cases analysed |
|---|---|---|---|
| hybrid | 2.9 | `{0:8, 2:3, 3:20, 4:12, 5:4, 6:1}` | **6.8** |
| rag_only | 2.7 | `{0:3, 2:7, 3:37, 4:1}` | 4.1 |
| kg_only | 0.0 | all zeros | 0.0 |
| llm_only | 0.0 | all zeros | 0.0 |

Hybrid analyses **~2× more cases** per prediction (6.8 vs 4.1) and forwards ~2.9 to the IRAC prompt vs rag_only's 2.7. The fatter right-tail (hybrid has 4–6 retrieved cases on 17/48 cases vs rag_only's 1/48) means hybrid hands the LLM more grounding examples on harder cases.

The single disagreement case where hybrid was right and rag_only was wrong (`housing-ombudsman-202441018`, gold=tenant) illustrates this:

| | hybrid | rag_only |
|---|---|---|
| predicted winner | tenant ✓ | landlord ✗ |
| confidence | 0.52 | 0.42 |
| retrieved cases | 5 | 2 |
| total analysed | 10 | 6 |
| rag_confidence | 0.82 | 0.93 |

Hybrid had 2.5× more retrieved cases to ground the prediction. With more grounding the LLM held the dominant-class prior; with less, rag_only flipped to landlord with low confidence. **This is a routing-layer effect, not a knowledge-graph effect.**

The architectural-novelty implication is uncomfortable but worth being honest about: the recovery sprint's hybrid-wins-rag_only headline comes from the FACTOR_CONSTRAINED routing producing a richer retrieval payload, not from any KG content reaching the prompt. The KG could be deleted from this run with no measured impact on hybrid's accuracy. _What changed accuracy was the prompt-cleanup work plus the routing pre-call's effect on retrieval payload composition._

---

## What changed under the hood

Four code patches landed between the original and recovery ablations:

1. **Empty factor card suppression** (commit `25e625f`, `STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1`) — collapses orphan blank lines that appeared when `{kg_fact_card}` and `{abstention_warning}` resolved to empty strings.
2. **Validator audit-only + confidence cap** (commit `34ccf1e`, `STREAM_C_EVIDENCE_PATH_STRICT=0` default) — `EvidencePathValidator` no longer flips `outcome=UNCERTAIN` when chains fail. Strict mode caps `raw_confidence` at 0.60 and emits `evidence_support="weak"` + `unsupported_claim_count`. Audit mode (default) records the same metadata without changing confidence.
3. **Forced-answer mode** (commit `c8b839e`, `STREAM_C_FORCE_ANSWER=1`) — IRAC schema removes `"uncertain"` from the allowed-outcome enum and instructs the LLM "you must choose exactly one outcome label." Post-processor remaps any LLM-returned `uncertain` to `split` with `raw_confidence ≤ 0.50`, `evidence_strength=INSUFFICIENT`, `[forced-answer fallback]` reasoning marker. **Empirically the post-process never engaged** — schema instruction alone was enough.
4. **Metadata serialisation regression test** (commit `6264a93`) — locks in the `_serialise_prediction` fix from commit `6917d32` so `pipeline_metadata` can never silently regress out of the artifact JSONL.

Combined effect: the 21pp gap flipped to a 2.1pp surplus. Dominant single contribution was forced-answer mode (kg_only + llm_only abstention dropped from 65% to 0%, so their accuracy could finally be measured at all).

---

## Run configuration

| Item | Value |
|---|---|
| Date | 2026-05-07 (run started 21:36 BST, completed 23:56 BST) |
| Branch | `codex/stream-c-prediction-path-plan` (HEAD `b01de8f` at run start) |
| Gold corpus | `data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl` (48 cases) |
| Modes | `hybrid`, `rag_only`, `kg_only`, `llm_only` |
| Engine | `live`, Claude Sonnet (via `--client claude`) |
| Top-k | 10 |
| Workers | 8 parallel chunks of 6 cases each, 4 modes per chunk |
| Wall time | ~2h 20min (single clean launch, no redos) |
| Bootstrap | seed=42, n_resamples=1000 |
| Env flags | `STREAM_C_PR4=1 STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_EVIDENCE_PATH_STRICT=0 STREAM_C_FORCE_ANSWER=1 STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1` |
| Cost | ~£8 |

**Gold-corpus audit:** `n=48`. 47/48 winners = `tenant`, 1/48 = `landlord`, 0/48 = `split`. 24/24 split between `repairs_damp_mould` and `repairs_disrepair`. 46/48 in London. `complaint_handling_failure` is below the stratification floor (0 cases) — the corpus is `is_clean=False`. No leakage violations.

---

## Confusion matrices (rows = gold winner, cols = predicted winner)

```
hybrid                          rag_only
gold\pred  landlord  tenant     gold\pred  landlord  tenant
landlord   1         0          landlord   1         0
tenant     4         43         tenant     5         42

kg_only                         llm_only
gold\pred  landlord  tenant     gold\pred  landlord  tenant
landlord   1         0          landlord   1         0
tenant     7         40         tenant     6         41
```

All four modes correctly classify the single landlord case (TP=1, FN=0). They differ only in how many tenant cases they incorrectly call landlord. No mode predicts `split` for any case (matches gold).

### Per-class precision / recall (overall_winner)

| Mode | Tenant prec | Tenant rec | Landlord prec | Landlord rec |
|---|---|---|---|---|
| hybrid | 1.000 | 0.915 | 0.200 | 1.000 |
| rag_only | 1.000 | 0.894 | 0.167 | 1.000 |
| kg_only | 1.000 | 0.851 | 0.125 | 1.000 |
| llm_only | 1.000 | 0.872 | 0.143 | 1.000 |

Tenant precision is 1.000 across the board because no model ever calls landlord on a real-tenant case AND lands on landlord — they only over-predict landlord in the wrong direction. Landlord recall is 1.000 across the board because the single landlord case is unanimously detected.

---

## Determination-level results

`predicted_determination` is the per-issue Housing Ombudsman determination label.

| Mode | Det. accuracy | maladministration recall | service_failure recall | outside_jurisdiction recall |
|---|---|---|---|---|
| hybrid | 0.438 | 0.581 | 0.286 | 1.000 |
| rag_only | **0.500** | **0.677** | 0.286 | 1.000 |
| kg_only | 0.271 | 0.258 | 0.571 | 1.000 |
| llm_only | 0.271 | 0.226 | **0.714** | 1.000 |

Two reversals from the winner-level ranking:
1. **rag_only beats hybrid** on determination accuracy (0.500 vs 0.438) and on the largest class (`maladministration`, 0.677 vs 0.581). The chunk-RAG retrieval seems to prime the prompt with stronger maladministration-pattern signal than hybrid's factor-constrained-fallback path does.
2. **kg_only and llm_only are markedly better on `service_failure`** (0.571 / 0.714) than the RAG-using modes (0.286). Without retrieval context, the LLM correctly identifies lower-severity outcomes more often. With retrieval, the model is pulled toward the most-frequent class.

Both point to a coupling between retrieval payload and determination prediction worth investigating — retrieved cases bias toward the modal class, improving headline accuracy but losing recall on under-represented classes.

---

## Caveats

1. **n=48 is small.** CIs are wide. Hybrid's +2.1pp surplus over rag_only is exactly 1 case; both modes' CIs overlap fully. Multi-axis claims need a larger corpus to separate signal from noise.
2. **Class-imbalanced corpus.** 47/48 tenant-wins. `always_tenant` baseline scores 0.979. Balanced accuracy and macro F1 are the meaningful headlines on this corpus, not raw accuracy.
3. **Repairs domain only.** The deposit pack (`housing.deposit.v1`) was untouched in this ablation — its byte-equivalence regression suite still locks in PR 4 = legacy behaviour for deposit cases.
4. **No factor data populated.** `Proposition.factor_ids` and KG `factor_assertions` are still empty across the corpus. The new factor-constrained retrieval path STILL falls back to chunk-RAG (per design decision D5) — so this run is NOT a direct test of the factor-constrained architecture's KG-content contribution. **It IS a test that the recovery patches stop the architecture from harming accuracy when factor data is absent**, AND that the FACTOR_CONSTRAINED routing produces a measurably richer retrieval payload than direct chunk-RAG even when no factor data is present. The next experiment (oracle-factor 20-case subset, deferred) would test whether factor data adds further accuracy on top.
5. **Hybrid's lead is from routing, not graph content.** `kg_used_for_prediction=False` × 48 means the KG never reaches the prompt. The accuracy lead is from retrieval-payload composition (hybrid analyses ~2× more cases than rag_only). Reviewers may push back on this as "hybrid is just chunk-RAG with a better front-door." That would be a fair characterisation of this specific run.
6. **Calibration is poor across all modes.** ECE 0.46 is severe — all modes are massively under-confident. This is independent of architecture and is a calibration-layer concern.

---

## Decision gate verdict (per recovery plan)

- **Gate 1** (empty-card diagnosis): partial — closed via suppression. ✓
- **Gate 2** (forced-answer fallback parity): YES — hybrid is now ≥ rag_only on accuracy. ✓
- **Gate 3** (KG positive-control fixture lights up): YES — confirmed by [`test_positive_control_kg_smoke.py`](../../packages/llm_orchestrator/tests/test_positive_control_kg_smoke.py) at commit `b01de8f`. ✓
- **Gate 4** (multi-axis hybrid signal): **partial.** Hybrid wins on accuracy + balanced accuracy + macro F1; loses on ECE + Brier + determination accuracy + amount@GBP100; ties on abstention; can't be measured on citation validity / evidence support rate (KG inert). The headline win is real but narrow.

---

## What this means for the thesis

The original empirical chapter was setting up to be a negative result ("we built the architecture; it didn't help; here's why"). The recovery ablation **converts the empirical chapter to a fallback-parity-plus result**:

- Hybrid factor-proposition KG-controlled CBR-RAG **does not harm accuracy** under forced-answer evaluation when the KG is empty. It marginally helps (+2.1pp = 1 case on n=48).
- The architecture's **graceful-fallback design (decision D5) is empirically validated** — when factor data is absent, hybrid degrades to "chunk-RAG plus richer routing" rather than to "chunk-RAG minus signal".
- The **forced-answer mechanism is correct and minimally invasive.** Zero post-process fallbacks on 192 prediction sessions; the schema-side change alone was sufficient.
- The **architecture activates correctly when given real data** (Task 7 positive-control smoke test).

The defensible thesis claim, properly tempered:

> "We built and evaluated a factor-proposition KG-controlled CBR-RAG architecture for legal outcome prediction. On 48 housing.repairs_social.v1 cases with no factor data populated, hybrid mode achieved 0.917 accuracy [0.833, 0.979] and 0.957 balanced accuracy, marginally outperforming a chunk-RAG-only baseline (0.896 / 0.947). The architecture's routing layer produced a measurably richer retrieval payload (mean 6.8 vs 4.1 cases analysed per prediction). Pipeline-metadata audit confirms the KG itself never engaged on this corpus due to absent factor data; the architectural innovation's contribution to outcome prediction therefore cannot be quantified from this run alone. A positive-control smoke test on a hand-built fully-populated KG fixture confirms the pipeline activates as designed when factor data is real. Future work: factor-data backfill into the gold corpus, oracle-factor sensitivity, expansion beyond housing.repairs_social.v1, calibration revision."

That's a more conservative claim than "hybrid beats RAG", but it's fully supportable from the data. A reviewer who reads the multi-axis section, the pipeline-metadata audit, and the retrieval-payload investigation will find no over-claim in it.

---

## What's next

In priority order:

1. **Factor-data backfill into the gold corpus.** Without it, the KG path stays inert on real cases and Stream C's headline architectural claim (graph-augmentation lifts the prediction) cannot be evaluated. The Task 7 fixture shows what "fully populated" looks like for one case; doing 48–150 of those is the rate-limiting input. Estimate: ~2 days of careful manual work per 10 cases for an annotator who knows the factor catalog.
2. **Counterfactual-factor sensitivity harness.** Required by the recovery plan's "Counterfactual factor sensitivity" axis. Build a small harness that, for each gold case, flips one legally-relevant factor and re-runs the pipeline; measure how often the predicted outcome changes appropriately. The positive-control fixture is the seed case for this.
3. **Evaluation-set expansion.** n=48 is too small to separate the 95% CIs we care about. Expand to ≥150 cases as part of the backfill effort, and rebalance class distribution.
4. **Calibration follow-up.** ECE 0.466 across the board is poor. The `overall_win_probability` averages 0.49 even though 47/48 cases are tenant_wins — the model is significantly underconfident. Worth a temperature-scaling pass post-hoc, or reviewing the prompt's confidence-elicitation language.
5. **Determination-label retrieval study.** rag_only beats hybrid on determination accuracy (0.500 vs 0.438) and the no-RAG modes are better on `service_failure` recall — the retrieval payload is biasing the determination prediction. A small ablation flipping the retrieval-payload composition under hybrid would inform whether the chunk-RAG fallback is helping or hurting determination.
6. **Routing-layer attribution study.** Hybrid's lead over rag_only is concentrated in retrieval-payload size (mean 6.8 vs 4.1 cases analysed). Worth understanding why FACTOR_CONSTRAINED routing produces more cases than direct chunk-RAG even when both fall back to the same retriever — it's likely a seed-pass-then-fallback pattern that includes both attempts in the final pack.

---

## Reproduce

```bash
# Predict (8 parallel chunked workers, 4 modes each, ~2.5h wall time)
mkdir -p eval/predictions/stream_c_recovery_2026_05_07_chunked
for i in 0 1 2 3 4 5 6 7; do
  mkdir -p "eval/predictions/stream_c_recovery_2026_05_07_chunked/chunk_$i"
  STREAM_C_PR4=1 STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_EVIDENCE_PATH_STRICT=0 \
  STREAM_C_FORCE_ANSWER=1 STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1 \
    ./venv/bin/python -m scripts.eval.predict_all \
    --gold "/tmp/stream_c_chunks/chunk_$i.jsonl" \
    --out-dir "eval/predictions/stream_c_recovery_2026_05_07_chunked/chunk_$i" \
    --engine live --client claude \
    --modes hybrid,rag_only,kg_only,llm_only --top-k 10 \
    > "/tmp/stream_c_recovery_chunk_$i.log" 2>&1 &
done
wait

# Merge per mode
mkdir -p eval/predictions/stream_c_recovery_2026_05_07
for mode in hybrid rag_only kg_only llm_only; do
  cat eval/predictions/stream_c_recovery_2026_05_07_chunked/chunk_*/${mode}.jsonl \
    > eval/predictions/stream_c_recovery_2026_05_07/${mode}.jsonl
done

# Analyse
PYTHONPATH=packages ./venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --predictions-dir eval/predictions/stream_c_recovery_2026_05_07 \
  --out-dir eval/results/stream_c_recovery_2026_05_07 \
  --modes hybrid,rag_only,kg_only,llm_only
```

---

## Files

- Predictions: [`eval/predictions/stream_c_recovery_2026_05_07/`](../../eval/predictions/stream_c_recovery_2026_05_07/)
- Eval results: [`eval/results/stream_c_recovery_2026_05_07/`](../../eval/results/stream_c_recovery_2026_05_07/)
- Recovery plan: [`docs/superpowers/plans/2026-05-07-stream-c-recovery-sprint.md`](../superpowers/plans/2026-05-07-stream-c-recovery-sprint.md)
- Original ablation: [`docs/eval/stream-c-ablation-2026-05-07.md`](stream-c-ablation-2026-05-07.md)
- PR4=0 diagnostic: [`docs/eval/stream-c-pr4-off-diagnostic-2026-05-07.md`](stream-c-pr4-off-diagnostic-2026-05-07.md)
- Supervisor briefing: [`docs/eval/stream-c-supervisor-briefing-2026-05-07.md`](stream-c-supervisor-briefing-2026-05-07.md) (will be updated with these results in Task 8)
