# Stream C — PR4=0 Empty-Card Diagnostic (2026-05-07)

## TL;DR

Hypothesis: the 21pp `rag_only` > `hybrid` gap in the [main 2026-05-07 ablation](stream-c-ablation-2026-05-07.md) was caused by the empty `KEY FACTORS (factor-graph derived):` placeholder bleeding into the hybrid prompt and confusing the LLM.

**Test:** re-ran hybrid mode on the same 48 cases with `STREAM_C_PR4=0` (which disables the pack-rendered factor card entirely, falling back to the legacy `_format_kg_fact_card`).

**Result: partial confirmation.** Hybrid accuracy moved from **62.5%** → **66.7%** (+4.2pp). The empty card explains roughly a fifth of the original gap. The other ~16pp gap to `rag_only` (83.3%) is something else — probably a combination of the abstention pathology (33% vs 12.5%) and downstream differences in retrieval payload composition between the `FACTOR_CONSTRAINED` fallback path and the direct `CHUNK_RAG` path that `rag_only` uses.

**Decision per recovery plan Gate 1:** *partial improvement* → suppress empty cards permanently (Task 2 default-on) AND inspect remaining differences. Both are addressed: empty-card suppression landed in commit `25e625f`; the abstention pathology is addressed by forced-answer mode in commit `c8b839e`. The forced-answer 48-case re-ablation (Task 6) is the next test.

---

## Configuration

| Item | Value |
|---|---|
| Date | 2026-05-07 |
| Branch | `codex/stream-c-prediction-path-plan` |
| Gold corpus | `data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl` (48 cases) |
| Modes | `hybrid` only |
| Engine | `live`, Claude 3.7 Sonnet |
| Top-k | 10 |
| Workers | 8 parallel chunks of 6 cases each |
| Wall time | ~25 minutes |
| Env flags | `STREAM_C_PR4=0`, `STREAM_C_FACTOR_RETRIEVAL=1`, `STREAM_C_EVIDENCE_PATH_STRICT=1` |
| Predictions | [`eval/predictions/stream_c_pr4_off_diag_2026_05_07/hybrid.jsonl`](../../eval/predictions/stream_c_pr4_off_diag_2026_05_07/hybrid.jsonl) |
| Eval results | [`eval/results/stream_c_pr4_off_diag_2026_05_07/`](../../eval/results/stream_c_pr4_off_diag_2026_05_07/) |
| Cost | ~£2 |

---

## Side-by-side metrics

| Mode | Accuracy | 95% CI | Macro F1 | Balanced Acc. | ECE | Brier | Covered Acc. | Abstention |
|---|---|---|---|---|---|---|---|---|
| `rag_only` (baseline) | **0.833** | [0.729, 0.938] | 0.307 | 0.426 | 0.455 | 0.230 | 0.952 | 0.125 |
| `hybrid` (PR4=1, baseline) | 0.625 | [0.479, 0.771] | 0.260 | 0.319 | 0.457 | 0.231 | 0.938 | 0.333 |
| **`hybrid` (PR4=0, this run)** | **0.667** | [0.521, 0.812] | 0.270 | 0.340 | 0.456 | 0.231 | 0.970 | 0.312 |

Hybrid PR4=0 is **+4.2pp on raw accuracy** vs hybrid PR4=1 — a real but small move. CIs overlap heavily. Macro F1, balanced accuracy, ECE, Brier are essentially unchanged. Covered accuracy ticks up to 0.970 (when hybrid PR4=0 commits, it's almost always right). Abstention is ~0.31 in both hybrid configurations — way above rag_only's 0.125.

---

## What this rules in / rules out

**Rules in (partially):** the empty `{kg_fact_card}` placeholder did contribute. Suppressing it permanently is the right move — it accounts for ~4pp of the gap and costs nothing.

**Rules out:** "the empty card was the whole problem." The remaining ~16pp gap to rag_only is NOT explained by PR4. It must be in one of:

1. **Abstention behaviour.** Hybrid abstains on 31% of cases vs rag_only's 12.5%. The forced-answer mode (commit `c8b839e`) eliminates final-UNCERTAIN labels by remapping to SPLIT with capped confidence. If abstention was the dominant remaining cause, the next ablation should close most of the residual gap.

2. **Retrieval payload differences.** With `STREAM_C_FACTOR_RETRIEVAL=1`, hybrid's retrieval routes through `RetrievalStrategy.FACTOR_CONSTRAINED` → `_retrieve_via_factor_retriever`. Because `asserted_factors` is empty in every case, the factor-retriever returns `None` and the engine falls back to `_retrieve_chunk_rag`. This *should* be the same path `rag_only` uses, but worth diffing the actual retrieved-cases JSON between the two modes on the same case to confirm.

3. **`{abstention_warning}` placeholder.** Same kind of orphan as the factor card. The recovery patches' empty-card suppressor (commit `25e625f`) collapses runs of 3+ blank lines, which catches both placeholders. But in the diagnostic run, `STREAM_C_SUPPRESS_EMPTY_FACTOR_CARD` was NOT yet on (the patch landed after this ablation started). So the diagnostic still had the orphan whitespace from `{abstention_warning}=""`. The next ablation will have both stripped.

---

## What's next

The recovery sprint patches all landed in commits `25e625f` (T2), `34ccf1e` (T3), `c8b839e` (T4), `6264a93` (T5). Plus the data fixture in `9352517` (T7-data). The next experiment is the **forced-answer 48-case re-ablation** (Task 6) with all the new patches active. Decision rule: hybrid (forced-answer + suppressed-empty-card + audit-only validator) should be ≥ rag_only on accuracy, OR match it while improving ECE / Brier / covered-accuracy / evidence-support metadata.

If the residual gap *still* doesn't close after forced-answer, the abstention hypothesis is wrong and we have to diff retrieval payloads. That's a cheap inspection — no LLM calls needed.

---

## Reproduce

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
wait

cat eval/predictions/stream_c_pr4_off_diag_2026_05_07_chunked/chunk_*/hybrid.jsonl \
  > eval/predictions/stream_c_pr4_off_diag_2026_05_07/hybrid.jsonl

PYTHONPATH=packages ./venv/bin/python scripts/eval/run_full_eval.py \
  --gold data/gold_standard/housing_repairs_social_v2_strict_clean.jsonl \
  --predictions-dir eval/predictions/stream_c_pr4_off_diag_2026_05_07 \
  --out-dir eval/results/stream_c_pr4_off_diag_2026_05_07 \
  --modes hybrid
```
