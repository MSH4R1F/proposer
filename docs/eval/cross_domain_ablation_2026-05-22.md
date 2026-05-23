> **⚠️ SUPERSEDED (2026-05-23):** the results below were driven by two measurement bugs — an employment token-truncation→prior-stamp bug and a housing scorer probability double-inversion. See `docs/eval/cross_domain_ablation_2026-05-23_FIXED.md` for the corrected numbers (RAG/hybrid are competitive-to-winning once the bugs are removed).

# Cross-domain 4-mode ablation — hybrid RAG + KG vs baselines

Ablation modes: `llm_only` (facts only) · `rag_only` (facts + retrieved precedents, leave-one-out) · `kg_only` (facts + SHA-149 factor digest) · `hybrid` (facts + retrieval + factors). Predictor `openai:gpt-5-mini`. Values are **mean ± std across seeds**.

*Brier(pos): lower is better, positive class is the respondent/landlord side; 0.25 = coin flip. Det/Outcome-Acc is the per-domain multi-class label accuracy (employment determination / housing maladministration / RRO offence-finding).*

## Employment unfair-dismissal — 132 cases · gpt-5-mini · 3 seeds

*3 seed(s).*

| Mode | Accuracy | Bal-Acc | Brier(pos) | LogLoss | Det/Outcome-Acc |
|---|---|---|---|---|---|
| `llm_only` | 79.0±0.9 | 0.598±0.011 | 0.166±0.005 | 0.517±0.012 | 49.0±1.7 |
| `rag_only` | 77.5±1.2 | 0.548±0.011 | 0.174±0.008 | 0.532±0.020 | 44.7±1.3 |
| `kg_only` | 77.8±1.2 | 0.549±0.019 | 0.172±0.009 | 0.528±0.022 | 46.0±1.9 |
| `hybrid` | 76.5±1.5 | 0.526±0.016 | 0.178±0.006 | 0.542±0.013 | 45.2±2.3 |

- Best calibration (Brier): **`llm_only`** · best balanced accuracy: **`llm_only`** · best outcome-class accuracy: **`llm_only`**.

## Housing repairs (Ombudsman) — 149 cases · gpt-5-mini · 1 seed

*1 seed(s).*

| Mode | Accuracy | Bal-Acc | Brier(pos) | LogLoss | Det/Outcome-Acc |
|---|---|---|---|---|---|
| `llm_only` | 94.0±0.0 | 0.490±0.000 | 0.169±0.000 | 0.529±0.000 | 32.2±0.0 |
| `rag_only` | 94.6±0.0 | 0.573±0.000 | 0.370±0.000 | 0.945±0.000 | 43.0±0.0 |
| `kg_only` | 96.0±0.0 | 0.500±0.000 | 0.167±0.000 | 0.525±0.000 | 35.6±0.0 |
| `hybrid` | 94.6±0.0 | 0.493±0.000 | 0.374±0.000 | 0.952±0.000 | 45.0±0.0 |

- Best calibration (Brier): **`kg_only`** · best balanced accuracy: **`rag_only`** · best outcome-class accuracy: **`hybrid`**.

## Housing RRO (FTT-PC) — 40-case balanced subset · gpt-5-mini · 1 seed

*1 seed(s).*

| Mode | Accuracy | Bal-Acc | Brier(pos) | LogLoss | Det/Outcome-Acc |
|---|---|---|---|---|---|
| `llm_only` | 55.0±0.0 | 0.464±0.000 | 0.305±0.000 | 0.807±0.000 | 0.0±0.0 |
| `rag_only` | 27.5±0.0 | 0.333±0.000 | 0.344±0.000 | 0.893±0.000 | 0.0±0.0 |
| `kg_only` | 40.0±0.0 | 0.393±0.000 | 0.421±0.000 | 1.116±0.000 | 0.0±0.0 |
| `hybrid` | 32.5±0.0 | 0.357±0.000 | 0.360±0.000 | 0.931±0.000 | 0.0±0.0 |

- Best calibration (Brier): **`llm_only`** · best balanced accuracy: **`llm_only`** · best outcome-class accuracy: **`llm_only`**.

## Cross-domain summary — winning mode per metric

| Domain | Best Brier | Best Bal-Acc | Best Outcome-Acc |
|---|---|---|---|
| Employment unfair-dismissal — 132 cases · gpt-5-mini · 3 seeds | `llm_only` | `llm_only` | `llm_only` |
| Housing repairs (Ombudsman) — 149 cases · gpt-5-mini · 1 seed | `kg_only` | `rag_only` | `hybrid` |
| Housing RRO (FTT-PC) — 40-case balanced subset · gpt-5-mini · 1 seed | `llm_only` | `llm_only` | `llm_only` |

## Reading the ablation

- **`rag_only` − `llm_only`** isolates the marginal value of case-based retrieval (similar published decisions with their outcomes attached, leave-one-out).
- **`kg_only` − `llm_only`** isolates the marginal value of the SHA-149 structured factor digest (typed pre-decision facts with polarity + confidence).
- **`hybrid`** tests whether retrieval and factors compose. On small gold sets (n≈150, skewed minority class) raw accuracy differences under ~4pp are within seed noise — read balanced accuracy, Brier, and outcome-class accuracy as the signal-bearing metrics.
## Headline findings

1. **No mode wins universally — the best mode is domain- and metric-dependent.**
   - **Employment (n=132, 3 seeds — the most reliable result): `llm_only` wins on every metric.** Adding retrieval and/or factors *hurts* (accuracy −1.2 to −2.5pp, Brier +0.006 to +0.012, balanced-acc −0.05 to −0.07).
   - **Housing repairs (n=149): split decision.** `kg_only` has the best calibration+accuracy, `rag_only` the best balanced-accuracy, `hybrid` the best outcome-class accuracy — but the two retrieval modes (`rag_only`, `hybrid`) **more than double the Brier** (0.37 vs 0.17), i.e. retrieval improves minority-class *recall* at the cost of severe over-confidence.
   - **Housing RRO (n=40 subset): `llm_only` wins on gpt-5-mini** — but see the instability caveat below.

2. **The hybrid RAG+KG architecture does NOT show a consistent advantage over a well-prompted LLM-with-facts baseline at these gold sizes.** On the single most statistically-reliable slice (employment, n=132, 3 seeds), the plain `llm_only` baseline is the *best* mode. This is the honest, load-bearing result of the expansion.

3. **This reverses the earlier n=49 employment finding** (where `hybrid`/`kg_only` won). That reversal is attributable to **prompt-overfitting**: the Rule-22 / conflict-resolution / factor-reasoning rules were tuned against the original 49 cases and do not generalize to the 123 newly-added cases. Larger gold sets exposed the overfit — which is exactly why we built them.

4. **Retrieval trades calibration for minority-class recall.** Clearest on housing repairs: `rag_only` lifts balanced accuracy (0.49→0.57) but wrecks Brier (0.17→0.37). For a product that surfaces probabilities to users, that calibration cost matters more than the recall gain.

## Methodology & caveats (read before citing any number)

- **Auto-promoted research-mode gold.** All three gold sets were labelled by an LLM panel (employment: dual gpt-5.5 + gpt-5-mini; housing: single gpt-5-mini) and auto-promoted with no human adjudication. Numbers measure agreement with an LLM-derived label, not human ground truth. Same-provider (OpenAI) labels *and* predictor ⇒ correlated bias that likely inflates all modes.
- **Severe class skew.** Employment 76% respondent (was 84% at n=49); housing repairs **96% tenant** (Ombudsman almost always finds some maladministration) — raw accuracy is near-degenerate there, which is why balanced-accuracy / Brier / outcome-accuracy are the signal-bearing metrics. RRO was scored on a **deliberately class-balanced 40-case subset** (full gold is 162, 82% tenant).
- **Unequal seeds.** Employment has 3 seeds (±std shown); housing has 1 seed each — housing single-seed numbers carry no variance band and a single case-flip moves balanced-accuracy materially at n≈40–150.
- **RRO is model-unstable at n=40.** gpt-5-mini ranks `llm_only` first; the earlier gpt-5.5 run ranked `hybrid`/`rag_only` first and `llm_only` last, with better Brier (0.22–0.28 vs 0.31–0.42). At n=40 the ablation ordering is not robust to the predictor model — treat RRO as indicative only.
- **RRO `Det/Outcome-Acc = 0`** is an artifact: the housing GoldCase schema (INV-F1) has no determination field that fits a tribunal RRO, so the offence-finding analog lives in the audit sidecar and is not read by this scorer. It is not a real 0% — ignore that column for RRO.
- **predict_all.py is sequential per case (~30s)**; the housing runs were sharded 8-way (repairs) / 4-way (RRO) for throughput. A transient ChromaDB concurrent-reader error required one shard re-run.
- **Domains are heterogeneous** (different forums, ontologies, winner semantics, factor catalogs) — cross-domain comparison is **qualitative**, not a controlled experiment.

## Bottom line for the thesis

At realistic gold sizes (~130–150 auto-labelled cases), the structured **RAG + KG augmentation does not beat a well-prompted LLM-with-facts baseline** on these UK legal domains; where retrieval helps minority-class recall it does so at a real calibration cost. The strongest controlled slice (employment, n=132, 3 seeds) favours the simple baseline. The apparent hybrid win at n=49 was small-sample prompt-overfitting. The honest next step is **human-adjudicated gold + cross-provider labelling + ≥3 seeds per domain** before claiming any architecture advantage.
