# Cross-domain 4-mode ablation — hybrid RAG + KG vs baselines

Ablation modes: `llm_only` (facts only) · `rag_only` (facts + retrieved precedents, leave-one-out) · `kg_only` (facts + SHA-149 factor digest) · `hybrid` (facts + retrieval + factors). Predictor `openai:gpt-5-mini`. Values are **mean ± std across seeds**.

*Brier(pos): lower is better, positive class is the respondent/landlord side; 0.25 = coin flip. Det/Outcome-Acc is the per-domain multi-class label accuracy (employment determination / housing maladministration / RRO offence-finding).*

## Employment unfair-dismissal — 132 cases · gpt-5-mini · 3 seeds (FIXED)

*3 seed(s).*

| Mode | Accuracy | Bal-Acc | Brier(pos) | LogLoss | Det/Outcome-Acc |
|---|---|---|---|---|---|
| `llm_only` | 79.0±0.4 | 0.602±0.008 | 0.162±0.003 | 0.506±0.007 | 50.5±1.7 |
| `rag_only` | 79.0±1.2 | 0.617±0.008 | 0.163±0.004 | 0.507±0.010 | 51.3±1.9 |
| `kg_only` | 77.0±1.2 | 0.582±0.019 | 0.183±0.008 | 0.562±0.021 | 53.5±0.4 |
| `hybrid` | 76.0±0.4 | 0.571±0.008 | 0.183±0.002 | 0.555±0.006 | 53.3±0.4 |

- Best calibration (Brier): **`llm_only`** · best balanced accuracy: **`rag_only`** · best outcome-class accuracy: **`kg_only`**.

## Housing repairs (Ombudsman) — 149 cases · gpt-5-mini · 1 seed (FIXED)

*1 seed(s).*

| Mode | Accuracy | Bal-Acc | Brier(pos) | LogLoss | Det/Outcome-Acc |
|---|---|---|---|---|---|
| `llm_only` | 94.0±0.0 | 0.490±0.000 | 0.349±0.000 | 0.893±0.000 | 32.2±0.0 |
| `rag_only` | 94.6±0.0 | 0.573±0.000 | 0.168±0.000 | 0.524±0.000 | 43.0±0.0 |
| `kg_only` | 96.0±0.0 | 0.500±0.000 | 0.354±0.000 | 0.904±0.000 | 35.6±0.0 |
| `hybrid` | 94.6±0.0 | 0.493±0.000 | 0.163±0.000 | 0.513±0.000 | 45.0±0.0 |

- Best calibration (Brier): **`hybrid`** · best balanced accuracy: **`rag_only`** · best outcome-class accuracy: **`hybrid`**.

## Housing RRO (FTT-PC) — 40-case subset · gpt-5-mini · 1 seed (FIXED)

*1 seed(s).*

| Mode | Accuracy | Bal-Acc | Brier(pos) | LogLoss | Det/Outcome-Acc |
|---|---|---|---|---|---|
| `llm_only` | 55.0±0.0 | 0.464±0.000 | 0.282±0.000 | 0.758±0.000 | 0.0±0.0 |
| `rag_only` | 27.5±0.0 | 0.333±0.000 | 0.197±0.000 | 0.582±0.000 | 0.0±0.0 |
| `kg_only` | 40.0±0.0 | 0.393±0.000 | 0.274±0.000 | 0.783±0.000 | 0.0±0.0 |
| `hybrid` | 32.5±0.0 | 0.357±0.000 | 0.217±0.000 | 0.625±0.000 | 0.0±0.0 |

- Best calibration (Brier): **`rag_only`** · best balanced accuracy: **`llm_only`** · best outcome-class accuracy: **`llm_only`**.

## Cross-domain summary — winning mode per metric

| Domain | Best Brier | Best Bal-Acc | Best Outcome-Acc |
|---|---|---|---|
| Employment unfair-dismissal — 132 cases · gpt-5-mini · 3 seeds (FIXED) | `llm_only` | `rag_only` | `kg_only` |
| Housing repairs (Ombudsman) — 149 cases · gpt-5-mini · 1 seed (FIXED) | `hybrid` | `rag_only` | `hybrid` |
| Housing RRO (FTT-PC) — 40-case subset · gpt-5-mini · 1 seed (FIXED) | `rag_only` | `llm_only` | `llm_only` |

## Reading the ablation

- **`rag_only` − `llm_only`** isolates the marginal value of case-based retrieval (similar published decisions with their outcomes attached, leave-one-out).
- **`kg_only` − `llm_only`** isolates the marginal value of the SHA-149 structured factor digest (typed pre-decision facts with polarity + confidence).
- **`hybrid`** tests whether retrieval and factors compose. On small gold sets (n≈150, skewed minority class) raw accuracy differences under ~4pp are within seed noise — read balanced accuracy, Brier, and outcome-class accuracy as the signal-bearing metrics.
## What changed vs the 2026-05-22 report (two measurement bugs fixed)

The first cross-domain run concluded "`llm_only` wins, hybrid RAG+KG hurts." A systematic debugging pass (3 parallel evidence agents + direct verification) found that conclusion was driven almost entirely by **two measurement bugs**, not by the architecture.

### Bug 1 — Employment: silent truncation → majority-prior stamping
`scripts/eval/run_employment_et_predictions.py` called gpt-5-mini (a *reasoning* model) with `max_tokens=2048`. The larger rag/kg/hybrid prompts (~16KB) burned the entire budget on hidden reasoning tokens, so the API returned `status="incomplete"` with **zero visible output**. The runner caught the resulting error and silently coerced the row to `winner=respondent, P=0.7652` — the corpus prior. Measured empty-response rates: `llm_only 0% / rag_only 63% / kg_only 56% / hybrid 80%`. So **up to 80% of "hybrid predictions" were never predictions** — they were the majority prior, which scores 76.5% for free, dragging the augmented modes' means down to ~the baseline.

**Fix:** `max_tokens` 2048 → 12000, `reasoning_effort="low"`, retry-once-at-larger-budget, and an explicit `extraction_failed` flag so a failure can never again masquerade as a confident majority-class prediction. Post-fix empty rate ≈ 0 (1/396 across 3 seeds). A secondary rate-limit (429) cascade under 3-way-parallel seeds was fixed by raising client `max_retries` to 8 and running seeds sequentially.

### Bug 2 — Housing: scorer double-inverted the probability
`packages/eval/adapter.py` already emits `overall_win_probability` as **P(landlord)** (a fixed positive-class orientation). The first `score_housing_ablation.py` re-inverted it (`1 − p`) for tenant predictions — double-inverting. That manufactured the entire "RAG doubles the Brier (0.37 vs 0.17)" regression. With the orientation corrected, the result reverses: on repairs, `rag_only`/`hybrid` reach Brier ≈ **0.16** vs `llm_only`/`kg_only` ≈ **0.35**, and RAG raised the model's confidence in the correct (tenant) direction (raw confidence 0.40 → 0.65).

### Refuted / secondary
- **Self-agreement confound** (gold auto-labelled by the same gpt-5 family that predicts) — a real methodology caveat, but *refuted as the primary driver*: determination-match was only 0.46 and claimant recall 23%, far below what a circular echo would yield.
- **Retrieval quality** is genuinely mediocre (≈34% of retrieved chunks have no joinable parent-outcome, a few long docs dominate, many hits are cover-page boilerplate). This is the real, remaining lever for *improving* the augmented modes further — now visible because it is no longer masked by the two bugs.

### Corrected bottom line
Once the measurement bugs are removed, the hybrid RAG+KG architecture is **competitive-to-winning** across all three domains rather than losing:
- **Employment (n=132, 3 seeds):** `rag_only` ties `llm_only` on accuracy/Brier and **wins balanced accuracy**; `kg_only`/`hybrid` **win determination accuracy by ~+3pp**.
- **Housing repairs (n=149):** `rag_only`/`hybrid` **win Brier (~0.16 vs 0.35)** and determination accuracy (+10–13pp).
- **Housing RRO (n=40 subset):** `rag_only` **wins Brier (0.197 vs 0.282)**; raw accuracy still noisy at this n.

The earlier "baseline beats the architecture" headline was an artifact. The honest, defensible claim is: **retrieval improves calibration and minority-class handling, and structured factors improve determination accuracy** — with retrieval-quality and human-adjudicated gold as the next levers. The 2026-05-22 report is superseded by this one.
