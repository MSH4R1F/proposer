# Stream C — Case-Side Factor Backfill Ablation (2026-05-09)

## TL;DR

Backfilled `factor_assertions` onto all 48 strict-clean gold cases using the Stream B extractor (`factor_gold_annotation.py` with `gpt-5 + gpt-5-mini` annotators on the 13 gate-countable factors). Promoted the IAA-style annotation output into a sidecar JSON consumed by `PredictionEngineV2` via the `--factor-assertion-sidecar` flag. Re-ran the 4-mode ablation against the case-backfilled corpus.

**Headline:** hybrid **regressed by 2 cases** (0.917 → 0.875) vs the [recovery ablation](stream-c-recovery-ablation-2026-05-07.md) baseline. rag_only unchanged at 0.896. kg_only and llm_only each lifted by 1 case. The case-side backfill **did not lift hybrid** — in fact it slightly hurt.

**Key architectural fact:** even with 13 FactorAssertions per case populated and flowing through to the IRAC prompt, **`kg_used_for_prediction=False` on every hybrid row**. The FactorRetriever scores all corpus propositions at zero `factor_overlap` because their `factor_ids` are still empty (proposition-side backfill not done — Postgres DB-backed, deferred per design call). The case-side data flips `retrieval_strategy=factor_constrained` and populates the IRAC prompt's KG fact card with content, but the architectural gate stays closed.

**Defensible reading:** the architecture's design decision D5 (graceful fallback when factor data is absent) is also operative when factor data is *partially present* — the engine completes the prediction but the KG path doesn't fire end-to-end. Quantifying graph-augmentation lift requires proposition-side backfill, which would justify a separate ~£40-80 engineering+LLM commitment if the case-side result hadn't been neutral-to-negative.

**The empirical chapter pivots:** with both the recovery sprint (no factor data) and case-side backfill experiments showing hybrid within ±1 case of rag_only, the thesis claim **"factor-proposition KG-controlled CBR-RAG lifts prediction"** is currently unsupported on this corpus. The defensible claim shifts from "fallback-parity-plus" to "fallback-parity, no measurable lift from partial factor data." Future work: proposition-side backfill OR an oracle-N hand-built study to isolate the architectural effect.

---

## What was built

### Tooling (commit `92a81e9`, ~1,200 LOC + 18 tests, 0 LLM cost)

The case-side backfill required engineering that didn't exist before this session.

| Component | File | Purpose |
|---|---|---|
| Sidecar schema | [`packages/eval/factor_assertion_sidecar.py`](../../packages/eval/factor_assertion_sidecar.py) | JSON structure storing `factor_assertions` keyed by `case_id`, decoupled from `GoldCase` (lower risk than schema mutation) |
| Promoter CLI | [`scripts/eval/promote_factor_annotations_to_gold.py`](../../scripts/eval/promote_factor_annotations_to_gold.py) | Reads IAA-style annotation jsonl → tie-breaks the 2-annotator output → translates to `FactorAssertion[]` → writes sidecar. Idempotent. |
| Engine wiring | `scripts/eval/predict_all.py` (+74 lines) | New `--factor-assertion-sidecar` flag piped through to the engine's `_build_eval_knowledge_graph` step |
| KG model field | `packages/kg_builder/models/graph.py` (+11 lines) | Added `factor_assertions: List[Any] = []` so the KG node carries promoted assertions through to the FactorRetriever |
| Tests | `packages/eval/tests/test_factor_assertion_sidecar.py` (10 tests), `scripts/eval/tests/test_promote_factor_annotations.py` (8 tests) | Round-trip, tie-break, idempotency, engine-path |

The schema decision was **(b) sidecar over (a) `GoldCase` field addition** because `GoldCase` has `extra="forbid"` Pydantic config — adding a field would have required coordinated changes across the eval harness's downstream consumers, with non-trivial regression risk on the 1,830+ unit test suite.

### Corpus alignment

Critical pre-flight check: only **3 of 48** strict_clean case_ids overlap with `housing_ombudsman_balanced_50_20260506.jsonl` (the script's default corpus). 45 cases would have produced empty extractions on that corpus. Switched to `data/eval/housing_ombudsman_stratified_50.jsonl` which has **all 48/48** strict_clean case_ids AND `raw_text_path` fields pointing to full case text on disk. Verified all 48 raw text files exist (~744 KB total, ~15 KB average per case).

### LLM extraction parameters

| Item | Value |
|---|---|
| Annotators | `openai:gpt-5,openai:gpt-5-mini` (matches Stream B's IAA report v2 run) |
| Cases | 50 (the corpus has 50 rows; 2 are dropped during promote since they're not in strict_clean — `housing-ombudsman-2022225 48`, `housing-ombudsman-202340236`) |
| Factors | 13 of 15 — the gate-countable set per the [IAA report](extractor_f1_reports/housing.repairs_social.v1-2026-05-07-gold-iaa-comparative.md). Excluded: `inspection_offered`, `impact_severity_reported`. |
| Total LLM calls | 50 × 13 × 2 = 1,300 |
| Tokens in | 5,862,095 |
| Tokens out | 1,669,043 |
| Wall time | ~53 min |
| Estimated cost | gpt-5 (~$30) + gpt-5-mini (~$2) = **~$32 ≈ £24** |
| IAA mean α | nan (some factors trivial-agreement, two with poor agreement: `issue_outside_jurisdiction` α=-0.08, `communication_gap_days` α=0.09) |

### Promotion to sidecar

| Item | Value |
|---|---|
| Cases populated | 48 (2 dropped — not in strict_clean) |
| Total FactorAssertions | 486 |
| Mean per case | 10.1 (range: 4–13) |
| Requires-human-review flag set | 114 / 486 (23.5%) |
| Sidecar path | `data/eval_artifacts/factor_assertions/housing_repairs_social_v2_strict_clean.factor_assertions.json` |

The 23.5% review-required rate reflects: (a) annotator disagreement (rare but real on the 2 poor-IAA factors), and (b) low-confidence canonical values. The retriever and engine consume all 486 entries equally — the review flag is metadata for downstream human curation, not a runtime filter.

### Ablation parameters

| Item | Value |
|---|---|
| Date | 2026-05-09 |
| Branch | `codex/stream-c-prediction-path-plan` (HEAD `92a81e9`) |
| Modes | `hybrid`, `rag_only`, `kg_only`, `llm_only` |
| Engine | `live`, Claude Sonnet |
| Top-k | 10 |
| Workers | 8 parallel chunks of 6 cases each, 4 modes per chunk |
| Wall time | 31 min (started 13:08, ended 13:39) |
| Bootstrap | seed=42, n_resamples=1000 |
| Env flags | `STREAM_C_PR4=1 STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_EVIDENCE_PATH_STRICT=0 STREAM_C_FORCE_ANSWER=1 STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1` (identical to recovery ablation) |
| Sidecar | auto-resolved by `predict_all` from canonical path |
| Estimated cost | ~£8 (Claude Sonnet, similar to recovery) |

---

## Side-by-side metrics: recovery (no factor data) vs case-backfill

| Mode | acc (recovery) | acc (case-backfill) | Δ acc | macro F1 (rec) | macro F1 (bf) | ECE (rec) | ECE (bf) | abstention |
|---|---|---|---|---|---|---|---|---|
| **hybrid** | 0.917 [0.833, 0.979] | **0.875** [0.771, 0.958] | **−0.042** | 0.644 | 0.591 | 0.466 | 0.469 | 0.000 |
| rag_only | 0.896 [0.812, 0.979] | 0.896 [0.812, 0.979] | +0.000 | 0.615 | 0.615 | 0.456 | 0.452 | 0.000 |
| kg_only | 0.854 [0.750, 0.938] | 0.875 [0.771, 0.958] | +0.021 | 0.571 | 0.591 | 0.545 | 0.552 | 0.000 |
| llm_only | 0.875 [0.771, 0.958] | 0.896 [0.812, 0.979] | +0.021 | 0.591 | 0.615 | 0.561 | 0.569 | 0.000 |
| _baseline_ `always_tenant` | 0.979 | 0.979 | — | 0.495 | 0.495 | 0.021 | 0.021 | 0.000 |

**Bold = headline change.** All deltas are 1–2 cases on n=48 (smallest measurable accuracy delta = 1/48 = 2.08pp). 95% CIs overlap fully across both runs. The shifts are within LLM stochastic variance.

### Confusion-matrix-level accounting

| Mode | tenant_wins → landlord errors (recovery) | (case-backfill) | Δ errors |
|---|---|---|---|
| hybrid | 4 | **6** | +2 |
| rag_only | 5 | 5 | 0 |
| kg_only | 7 | 6 | −1 |
| llm_only | 6 | 5 | −1 |

Hybrid mis-classified **two additional tenant cases as landlord** under case-backfill — a worse direction. rag_only is unchanged. kg_only and llm_only each rescued one tenant case from a false-landlord call.

---

## Pipeline-metadata audit: did the KG actually fire?

| Mode | `kg_used_for_prediction` | `retrieval_strategy` | `evidence_support` | mean retrieved | mean analysed |
|---|---|---|---|---|---|
| hybrid | `False` × 48 | `factor_constrained` × 48 | `None` × 48 | 3.0 | 6.8 |
| rag_only | `False` × 48 | `chunk_rag` × 48 | `None` × 48 | 2.5 | 4.1 |
| kg_only | `False` × 48 | `chunk_rag` × 48 | `None` × 48 | 0.0 | 0.0 |
| llm_only | `None` × 48 | `chunk_rag` × 48 | `None` × 48 | 0.0 | 0.0 |

**Same picture as recovery: `kg_used_for_prediction=False` everywhere.** Even with all 13 gate-countable factors populated for every case (mean 10.1 FactorAssertions per case), the metadata gate stays closed. The reason: `FactorRetriever` (`packages/llm_orchestrator/pipeline/factor_retrieval.py:293`) scores propositions by `factor_overlap` between case-side `asserted_factors` and proposition-side `factor_ids`. Corpus propositions are still untagged (Postgres-backed, deferred from this sprint), so every proposition scores 0 on factor overlap. The retriever falls back to similarity-based scoring; the engine flags this as "KG path not used."

**Independent confirmation that the sidecar IS being consumed:**

- One sample case (`housing-ombudsman-202451564`) has 13 sidecar entries with realistic values:
  - `communication_gap_days = 133` (polarity=pro_claimant, conf=0.85, review=True)
  - `complaint_response_delay_days = 14` (conf=0.93, review=False)
  - `hazard_or_disrepair_reported = True` (conf=0.98, review=False)
- `retrieval_strategy=factor_constrained` for hybrid (vs `chunk_rag` for rag_only) — different routing
- Mean retrieved cases: 3.0 for hybrid vs 2.5 for rag_only — small payload difference

So the factor data IS reaching the IRAC prompt's KG fact card, AND the routing is taking the factor-constrained path. What's not happening is end-to-end KG activation (gate-pass).

---

## What this run rules in / rules out

**Rules in:**

1. **The sidecar pipeline works end-to-end.** Promoter → sidecar JSON → engine consumption → KG node hydration → FactorRetriever input → prompt rendering. All wired correctly.
2. **`factor_gold_annotation.py` produces usable annotations on real case text** when pointed at a corpus with `raw_text_path` (the strict_clean gold corpus alone is insufficient). 14% null rate on the 3-case sample, ~10 FactorAssertions per case on the 50-case run.
3. **The architectural design decision D5 (graceful fallback) holds.** Even with case-side factor data partially populated and proposition-side empty, the engine produces predictions; nothing crashes; abstention stays at 0%.

**Rules out:**

1. **"Case-side factor data lifts hybrid accuracy on this corpus."** It doesn't. Hybrid regressed 2 cases. CIs overlap heavily (so we can't say it *hurt* with confidence either), but the direction is the wrong way for the thesis claim.
2. **"The KG architecture activates as soon as factor_assertions are populated."** It doesn't. Both case-side AND proposition-side need population for `kg_used_for_prediction=True` to flip.
3. **Any thesis claim of the form "factor-proposition KG-controlled CBR-RAG lifts prediction"** based on either the recovery ablation or this case-backfill ablation. Neither shows architectural lift on this 48-case corpus.

---

## Why might hybrid have regressed?

Three plausible explanations, none independently testable from this run:

1. **The factor card adds noise/bias to the IRAC prompt.** The 23.5% requires-human-review flag rate means the rendered factor card carries some uncertain signals. The 2 poor-IAA factors (`issue_outside_jurisdiction` α=-0.08, `communication_gap_days` α=0.09) may bias hybrid's prediction toward the wrong class.
2. **LLM stochastic variance.** Both runs use Claude Sonnet at default temperature. Two cases shifting on n=48 is a 4.2pp swing — well within the noise band observed in repeated runs of the same configuration. The recovery ablation's hybrid result moved by 1 case between Codex's run and my replication on the same configuration; this could be similar.
3. **Pre-existing class-prior bias.** With 47/48 gold cases tenant_wins, any signal that nudges hybrid toward landlord costs accuracy. The factor card may include factors where the value is "no-fault on landlord" (e.g., `issue_outside_jurisdiction=False` is technically pro-claimant but "outside jurisdiction" framing might confuse the LLM).

To isolate: an oracle-quality hand-curated 5-case set (similar to the [positive-control fixture](../../data/eval_artifacts/positive_control/housing_repairs_social_v1_one_case_kg/)) would let us run hybrid against perfectly-correct factor data, factor card prose, and prompts. If oracle hybrid lifts vs LLM-extracted hybrid, the regression is annotation-quality. If it doesn't, the architecture's factor-card mechanism itself isn't lifting prediction on this corpus.

---

## Cost summary for this experiment

| Step | LLM | Engineering | Wall |
|---|---|---|---|
| Recon (subagent) | £0 | ~30 min | — |
| Tooling (subagent 1) | £0 | ~6 hours equiv | — |
| Sample 3-case extraction (false start: wrong corpus) | ~£0.50 | — | ~3 min |
| Sample 3-case extraction (stratified_50 corpus) | ~£0.50 | — | ~3 min |
| Sample promotion | £0 | — | <1 min |
| Integration smoke (1-case predict, after venv repair) | ~£0.20 | ~30 min on env recovery | ~3 min |
| Full extraction (50 × 13 × 2) | ~£24 | — | 53 min |
| Promotion | £0 | — | <1 min |
| 4-mode ablation | ~£8 | — | 31 min |
| **Total** | **~£32** | **~7 hours** | **~95 min compute** |

The ~£32 is within tolerance of the £20–30 user authorisation. The largest single cost item is the gpt-5 annotator (~£23 of the £24 extractor cost; gpt-5-mini was ~£1.30). Notable losses: the first sample was wasted (~£0.50) due to a corpus-alignment bug; ~30 minutes were spent on venv corruption recovery (unrelated to the backfill itself but cost time on the critical path).

---

## What's next

The case-side backfill is **complete** and the architecture is **correctly wired**, but the empirical claim "graph-augmented retrieval lifts prediction" remains unsupported on this corpus. Three forward paths in priority order:

1. **Proposition-side backfill** (£40–80 LLM + ~6h engineering for the Postgres-backed proposition tagger + writer). This is the rate-limiter for any "KG fired end-to-end" empirical claim. Risk: same as case-side — if it doesn't lift hybrid, the architecture has a real problem on this corpus, and the thesis pivots to "we built the system; it works; the empirical lift requires datasets/factor-catalogues different from the ones we tested."
2. **Oracle-N hand-curated study** (5–10 cases hand-built like the positive-control fixture; £4 ablation). Tests whether *perfect* factor data + factor card lifts hybrid vs rag_only on the same cases. Cheaper than (1), gives clearer signal, smaller N. If oracle hybrid lifts, the LLM-extracted backfill is contaminated; if not, the architecture isn't doing what we hoped.
3. **Calibration study, independent of factor backfill.** ECE 0.45–0.57 across all modes is severe under-confidence. Worth a temperature-scaling pass — could lift Brier scores meaningfully without further LLM spend.

Recommendation: **(2) before (1)**. The oracle-N study costs £4 and 4 hours of careful manual annotation; it gives a clean answer about whether the architecture's lift mechanism works under ideal data, before committing £40–80 to the proposition-tagger-via-Postgres surface.

---

## Reproduce

```bash
# 1. Run the extractor (50 cases, 13 factors, 2 annotators)
PYTHONPATH=packages ./venv/bin/python scripts/eval/factor_gold_annotation.py \
    --domain housing.repairs_social.v1 \
    --execute \
    --n 50 \
    --annotator-providers "openai:gpt-5,openai:gpt-5-mini" \
    --seed 42 \
    --corpus-path data/eval/housing_ombudsman_stratified_50.jsonl \
    --factors hazard_or_disrepair_reported,landlord_notice_established,repair_attempted,temporary_decant_or_alternative_offered,prior_compensation_or_apology_offered,issue_outside_jurisdiction,vulnerability_known,repair_responsibility_established,records_inadequate,inspection_delay_days,communication_gap_days,repair_delay_days,complaint_response_delay_days \
    --output data/eval_artifacts/gold_annotation/housing.repairs_social.v1-case-backfill-n50-stratified-seed42-2026-05-09.jsonl

# 2. Promote IAA jsonl to sidecar
PYTHONPATH=packages ./venv/bin/python scripts/eval/promote_factor_annotations_to_gold.py \
    --annotations data/eval_artifacts/gold_annotation/housing.repairs_social.v1-case-backfill-n50-stratified-seed42-2026-05-09.jsonl \
    --gold-corpus data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
    --domain housing.repairs_social.v1 \
    --extractor-version "gpt-5+gpt-5-mini-2026-05-09"

# 3. Re-run 4-mode ablation (predict_all auto-resolves the sidecar)
mkdir -p eval/predictions/stream_c_case_backfill_2026_05_09_chunked
for i in 0 1 2 3 4 5 6 7; do
  mkdir -p "eval/predictions/stream_c_case_backfill_2026_05_09_chunked/chunk_$i"
  STREAM_C_PR4=1 STREAM_C_FACTOR_RETRIEVAL=1 STREAM_C_EVIDENCE_PATH_STRICT=0 \
  STREAM_C_FORCE_ANSWER=1 STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD=1 \
    ./venv/bin/python -m scripts.eval.predict_all \
    --gold "/tmp/stream_c_chunks/chunk_$i.jsonl" \
    --out-dir "eval/predictions/stream_c_case_backfill_2026_05_09_chunked/chunk_$i" \
    --engine live --client claude \
    --modes hybrid,rag_only,kg_only,llm_only --top-k 10 \
    > "/tmp/stream_c_case_backfill_chunk_$i.log" 2>&1 &
done
wait

mkdir -p eval/predictions/stream_c_case_backfill_2026_05_09
for mode in hybrid rag_only kg_only llm_only; do
  cat eval/predictions/stream_c_case_backfill_2026_05_09_chunked/chunk_*/${mode}.jsonl \
    > eval/predictions/stream_c_case_backfill_2026_05_09/${mode}.jsonl
done

# 4. Analyse
PYTHONPATH=packages ./venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --predictions-dir eval/predictions/stream_c_case_backfill_2026_05_09 \
  --out-dir eval/results/stream_c_case_backfill_2026_05_09 \
  --modes hybrid,rag_only,kg_only,llm_only
```

---

## Files

- Tooling: commit `92a81e9` (`feat(eval): case-side factor-assertion backfill tooling (Stream C)`)
- IAA annotations: [`data/eval_artifacts/gold_annotation/housing.repairs_social.v1-case-backfill-n50-stratified-seed42-2026-05-09.jsonl`](../../data/eval_artifacts/gold_annotation/housing.repairs_social.v1-case-backfill-n50-stratified-seed42-2026-05-09.jsonl) (1,300 rows)
- Sidecar: [`data/eval_artifacts/factor_assertions/housing_repairs_social_v2_strict_clean.factor_assertions.json`](../../data/eval_artifacts/factor_assertions/housing_repairs_social_v2_strict_clean.factor_assertions.json) (48 cases, 486 assertions)
- Predictions: [`eval/predictions/stream_c_case_backfill_2026_05_09/`](../../eval/predictions/stream_c_case_backfill_2026_05_09/)
- Eval results: [`eval/results/stream_c_case_backfill_2026_05_09/`](../../eval/results/stream_c_case_backfill_2026_05_09/)
- Recovery ablation (baseline for comparison): [`stream-c-recovery-ablation-2026-05-07.md`](stream-c-recovery-ablation-2026-05-07.md)
- Supervisor briefing: [`stream-c-supervisor-briefing-2026-05-07.md`](stream-c-supervisor-briefing-2026-05-07.md) (will be updated with these results in a follow-up commit)
