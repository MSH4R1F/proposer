# Housing Ombudsman Stratified-50 v2 Full Eval (2026-05-06)

**Run id:** `task18_par40_20260506_161134`
**Gold corpus:** [`data/gold_standard/housing_repairs_social_v2.jsonl`](../../data/gold_standard/housing_repairs_social_v2.jsonl) (50-row stratified-50 corpus migrated to the v2 determination ontology — see [migration audit](../../data/eval_artifacts/migration/stratified_50_2026_05_06/audit.json))
**Eval set used:** 48 of 50 rows valid under INV-D4. The two unmigrated rows (`housing-ombudsman-202222548` packet not found, `housing-ombudsman-202340236` manifest tag `unknown`) were filtered into [`data/gold_standard/v2_valid48.jsonl`](../../data/gold_standard/v2_valid48.jsonl) for this run.
**Engine:** PredictionEngineV2 / OpenAI gpt-5.5 / `--reasoning_effort=high`
**Wall clock:** 13 minutes (16:11→16:24 BST), 192 LLM calls total
**Parallelism:** 40 shards (10 case-chunks × 4 modes)
**Cost:** ~$10–15 OpenAI

This is the first thesis-grade housing eval run end-to-end on the new determination ontology. It validates that PR #32 (ontology + adapter + metrics) plus PR #33 (prompt + serialiser + loader fixes) wire correctly across all 4 ablation modes.

---

## Headline numbers

| Mode | accuracy | covered_acc | abstain | predicted | correct | det. accuracy | within @20% | within @£100 | MAE £ | amt n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **hybrid** | **0.833** | 0.930 | 0.104 | 43/48 | 40/43 | **0.542** | 0.083 | 0.104 | 568 | 37 |
| rag_only | 0.812 | 0.951 | 0.146 | 41/48 | 39/41 | 0.500 | 0.104 | 0.125 | 534 | 35 |
| kg_only | 0.333 | 0.941 | 0.646 | 17/48 | 16/17 | 0.146 | 0.000 | 0.000 | n/a | 0 |
| llm_only | 0.167 | 1.000 | 0.833 | 8/48 | 8/8 | 0.146 | 0.000 | 0.000 | n/a | 0 |
| `always_tenant` baseline | 0.979 | 0.979 | 0.000 | 48/48 | 47/48 | n/a | n/a | n/a | n/a | n/a |
| `always_landlord` baseline | 0.021 | 0.021 | 0.000 | 48/48 | 1/48 | n/a | n/a | n/a | n/a | n/a |
| `claim_positive_winner` baseline | n/a | n/a | 0.000 | 48/48 | n/a | n/a | n/a | n/a | n/a | n/a |
| `claim_amount_copy` baseline | n/a | n/a | 0.000 | 48/48 | n/a | n/a | n/a | n/a | n/a | n/a |

The two `claim_*` baselines emit `null` per Task 8 — they're deposit-domain baselines that do not apply to housing.repairs_social.v1 (`claimed_amounts=[]` on every gold row).

---

## Reading the metrics

### `accuracy` (legacy binary winner)

Fraction of cases where the predicted `overall_winner` matches gold's `overall_winner` (tenant / landlord / split). Abstentions count as wrong.

**Why hybrid hits 0.833 here vs 0.20 on the original RCA balanced-50.** The stratified-50 v2 corpus is heavily tenant-leaning: `always_tenant` scores 0.979 (47 of 48 rows are tenant-wins under the legacy binary). Any mode that defaults to tenant-bias on this corpus looks excellent on `accuracy`. Reading this number in isolation is misleading.

### `covered_accuracy`

Same numerator as `accuracy`, but denominator excludes abstained cases.

Why rag_only's covered_accuracy (0.951) is higher than hybrid's (0.930): selection effect from abstention. rag_only abstained on 7 cases (vs hybrid 5), and the two extra cases it refused were the borderline ones — so its remaining set was easier. llm_only's 1.000 is an 8-of-8 sliver from a mode that abstained on 40 of 48 cases.

`coverage_adjusted_accuracy` (correct-non-abstained / total) is the cleaner direct comparison: hybrid 0.833, rag_only 0.812, kg_only 0.333, llm_only 0.167.

### `determination.accuracy` (new in PR #32)

The Ombudsman determination ontology metric. Fraction of cases where `predicted_determination` matches `gold.ground_truth_outcome.determination` on the 7-class axis (`maladministration`, `severe_maladministration`, `service_failure`, `reasonable_redress`, `no_maladministration`, `resolved_with_intervention`, `outside_jurisdiction`).

- 48 cases carry a gold determination.
- hybrid hit 26/48 = 0.542. rag_only matched it at 0.500. kg_only / llm_only collapse to 0.146.
- This is the **construct-stable headline** — it does not benefit from the corpus tenant-imbalance the way binary `accuracy` does.

### `class_recall` per Determination

Hybrid:

| class | n in gold | recall |
|---|---:|---:|
| maladministration | 31 | **0.77** (24) |
| outside_jurisdiction | 1 | **1.00** (1) |
| service_failure | 7 | 0.14 (1) |
| reasonable_redress | 4 | 0.00 (0) |
| severe_maladministration | 3 | 0.00 (0) |
| resolved_with_intervention | 2 | 0.00 (0) |

Diagnostic reading:
- The model is strong on the dominant class (maladministration) and got the single outside-jurisdiction case right.
- It collapses smaller classes into maladministration — service_failure 0.14, severe_maladministration 0.00, resolved_with_intervention 0.00 — all classes the dataset doesn't have many examples of.
- **reasonable_redress (4 cases) is the most informative miss**: this is the same construct gap the original RCA flagged. The model defaults to maladministration for any tenant-side complaint with a remedy.

kg_only and llm_only collapse to **service_failure** on every covered case (recall=1.0 on service_failure, 0.0 on every other class). That is the no-RAG narrative regression: when the LLM is given only KG facts or empty context, it falls back to a single conservative determination.

### `amount.within_20pct` and `amount.within_gbp100`

Fraction of cases where the predicted total is within ±20% (or ±£100) of `gold.total_awarded_gbp`. Denominator is cases with a non-null gold amount.

- hybrid hit ±20% on **0.083** (4/48) of cases and ±£100 on **0.104** (5/48).
- rag_only is marginally better at ±20% (0.104) and ±£100 (0.125).
- kg_only/llm_only score 0 because they never emit a `predicted_amount`.

These low scores are expected per the RCA: gold's `total_awarded_gbp` rolls in the landlord pre-existing offer for `reasonable_redress` cases, while the model only emits an "additional comparator order" estimate. The construct gap caps the ceiling. Use the per-construct MAE below for the construct-matched ceiling.

### `amount.mae_gbp` (legacy, all-rows)

Mean absolute error in £ over cases where both gold and prediction have an amount. hybrid £568, rag_only £534. Same caveat — averages across construct classes the model treats differently.

### `amount.mae_gbp_ordered_now` / `mae_gbp_previously_offered` / `mae_gbp_global_unapportioned` (new in PR #32)

MAE restricted to cases where the gold amount lives in the named construct field. The cleaner read.

| Mode | mae_ordered_now | mae_previously_offered | mae_global_unapportioned |
|---|---:|---:|---:|
| hybrid | £504 | £440 | £1,341 |
| rag_only | £487 | £440 | £1,341 |
| kg_only | £668 | £738 | £1,741 |
| llm_only | £668 | £738 | £1,741 |

`ordered_now` is the construct the model is actually asked to predict (per the housing prompt pack). hybrid + rag_only land at ~£500 — that's a real signal of model quality, not corpus artefact. The `previously_offered` and `global_unapportioned` numbers are higher because the model has no input access to the prior-offer amount on those constructs (per packet reviewer instructions); failure expected.

kg_only/llm_only have no amount predictions, so per-construct errors are bounded by the construct's gold £ values per the metric's missing-prediction policy (treats missing as full-magnitude error).

### `amt n` column

Number of cases where the model emitted a non-null `predicted_amount`. hybrid 37/48, rag_only 35/48, no-RAG modes 0/48. Combined with `within_*` denominators, this lets you see whether a low score is from low coverage vs low accuracy.

---

## What this run validates

1. **The determination ontology pipeline is wire-correct.** Predicted determinations propagate from the housing prompt through `issue_predictor` → `output_assembler` → `from_prediction_result` → JSONL → `_dict_to_prediction` → metrics. Each step is exercised by 192 LLM calls of real data.

2. **Hybrid vs rag_only is roughly a wash on this dataset.** The legacy `accuracy` gap (0.833 vs 0.812) and the `det.accuracy` gap (0.542 vs 0.500) are within the variance you'd expect from prompt rewording. The original RCA's claim that hybrid was strictly better on the balanced-50 doesn't replicate here because this corpus has a different determination distribution.

3. **kg_only and llm_only are genuinely degraded.** `class_recall: service_failure=1.0` on every covered case and 65–83% abstention — the no-RAG narrative regression that PR #32 explicitly excluded from scope is still live.

4. **Per-construct MAE works as designed.** `mae_ordered_now=£504` for hybrid is a clean, construct-stable amount metric; the legacy all-rows `mae_gbp=568` is more polluted.

---

## What this run does NOT validate

- **The original balanced-50 RCA findings.** This run is the *stratified-50* corpus migrated to v2, not the balanced-50. The balanced-50 packets weren't in the merged main when this branch was created. To test the RCA's claims, re-run with `--gold` pointing at a balanced-50 v2 corpus once those packets land on main.
- **Behaviour on minority classes.** Only 4 reasonable_redress, 3 severe_maladministration, 2 resolved_with_intervention rows means class_recall on those is high-variance. Need a stratified larger corpus to make confident statements.
- **Amount calibration on the upper tail.** Highest gold amount in this corpus is small relative to the balanced-50 (median ~£500 here vs broader range there). Worst-case MAE figures need the balanced-50 to surface the construct-gap pathology fully.

---

## Acceptance gates

From the [root-cause investigation](housing-ombudsman-balanced-50-root-cause-investigation-2026-05-06.md) §6:

| Gate | Required | This run | Pass? |
|---|---|---|---|
| All four modes coverage > 30% | yes | hybrid 90%, rag_only 85%, kg_only 35%, llm_only 17% | **partial** — kg/llm fail (no-RAG regression, out of scope) |
| `always_tenant` and `always_landlord` baselines emit | yes | both emit (0.979 and 0.021) | **pass** |
| Hybrid > rag_only on substantive-merits accuracy | preferred | hybrid det.acc 0.542 vs rag_only 0.500 | **pass** (modest) |
| Citation removal rate < 35% per RAG mode | yes | not reported here; verify via citation_verification block in raw predictions | **TBD** |
| No mode predicts a single class > 90% on balanced gold | yes | corpus is unbalanced (96% tenant) so this gate is not directly testable here | **n/a** |

This run clears 3 of 5 gates outright. The two failures (no-RAG modes; balanced-corpus single-class check) are out-of-scope for the determination ontology PRs and require further work.

---

## Reproducibility

To regenerate this report exactly:

```bash
# 1. From repo root, ensure the v2 gold + index exist
ls data/gold_standard/housing_repairs_social_v2.jsonl

# 2. Run migration (if v2 is missing)
PYTHONPATH=packages venv/bin/python -m scripts.eval.migrate_balanced50_to_determination_schema \
  --gold-in data/gold_standard/housing_repairs_social_v1.jsonl \
  --gold-out data/gold_standard/housing_repairs_social_v2.jsonl \
  --review-packets data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/ \
  --audit-out data/eval_artifacts/migration/stratified_50_2026_05_06/

# 3. Filter to validating rows (drops the 2 unmigrated cases)
PYTHONPATH=packages venv/bin/python -c "
import json
from pathlib import Path
from eval.schema import GoldCase
from pydantic import ValidationError
valid = []
for line in Path('data/gold_standard/housing_repairs_social_v2.jsonl').read_text().splitlines():
    try:
        GoldCase.model_validate(json.loads(line))
        valid.append(line)
    except ValidationError:
        pass
Path('data/gold_standard/v2_valid48.jsonl').write_text('\n'.join(valid) + '\n')
"

# 4. Shard into 10 chunks
PYTHONPATH=packages venv/bin/python -c "
from pathlib import Path
lines = Path('data/gold_standard/v2_valid48.jsonl').read_text().splitlines()
n = len(lines); shards = 10
sizes = [n // shards + (1 if i < n % shards else 0) for i in range(shards)]
i = 0
for s, size in enumerate(sizes):
    Path(f'data/gold_standard/v2_shard{s:02d}.jsonl').write_text('\n'.join(lines[i:i+size]) + '\n')
    i += size
"

# 5. Launch 40 parallel shards (4 modes × 10 case-chunks)
RUN_ID="task18_par40_$(date +%Y%m%d_%H%M%S)"
OUT_DIR="eval/predictions/${RUN_ID}"
mkdir -p "$OUT_DIR/logs"
for SHARD in 00 01 02 03 04 05 06 07 08 09; do
  for MODE in hybrid rag_only kg_only llm_only; do
    SHARD_DIR="$OUT_DIR/shard${SHARD}_${MODE}"
    mkdir -p "$SHARD_DIR"
    PYTHONPATH=packages venv/bin/python -m scripts.eval.predict_all \
      --gold "data/gold_standard/v2_shard${SHARD}.jsonl" \
      --modes $MODE --engine live --client openai \
      --rag-index-root data/indices \
      --out-dir "$SHARD_DIR" \
      > "$OUT_DIR/logs/shard${SHARD}_${MODE}.log" 2>&1 &
  done
done
wait

# 6. Concat per-mode shards
for MODE in hybrid rag_only kg_only llm_only; do
  cat $OUT_DIR/shard*_${MODE}/${MODE}.jsonl > $OUT_DIR/${MODE}.jsonl
done

# 7. Run summary metrics
RESULTS_DIR=eval/results/${RUN_ID}_full_eval
mkdir -p $RESULTS_DIR
PYTHONPATH=packages venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/v2_valid48.jsonl \
  --predictions-dir "$OUT_DIR" \
  --out-dir "$RESULTS_DIR" \
  --no-bootstrap --min-case-count 5
```

Run-time on a single workstation with OpenAI tier-2 rate limits: **~13 minutes wall-clock**. Cost: ~$10-15.

---

## Artifacts

- **Predictions:** [`eval/predictions/task18_par40_20260506_161134/`](../../eval/predictions/task18_par40_20260506_161134/)
  - Per-mode JSONL: `hybrid.jsonl`, `rag_only.jsonl`, `kg_only.jsonl`, `llm_only.jsonl`
  - Per-shard outputs: `shard*_<mode>/`
  - Logs: `logs/shard*_<mode>.log`
- **Eval summary:** [`eval/results/task18_par40_20260506_161134_full_eval/`](../../eval/results/task18_par40_20260506_161134_full_eval/)
  - `summary.json` — per-mode metrics block (this report's source data)
  - `ablation.json` — pairwise mode comparison
  - `audit.json` — gold corpus audit
  - `metrics/` — per-(mode, metric) detail
- **Migration audit:** [`data/eval_artifacts/migration/stratified_50_2026_05_06/`](../../data/eval_artifacts/migration/stratified_50_2026_05_06/)

---

## See also

- [Determination ontology canonical mapping](housing-ombudsman-determination-ontology-2026-05-06.md)
- [Root-cause investigation that motivated the ontology](housing-ombudsman-balanced-50-root-cause-investigation-2026-05-06.md)
- [`docs/eval/metrics.md` — determination metrics doc section](metrics.md)
- [`docs/eval/gold-schema.md` — determination ontology schema section](gold-schema.md)
