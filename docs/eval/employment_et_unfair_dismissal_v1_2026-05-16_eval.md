# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/20260516T101952Z-10f6bf0d-emp-et-predict`
**Run ID:** `20260516T101952Z-10f6bf0d-emp-et-predict`
**Predictor:** `openai:gpt-5-mini`
**Gold n:** 49

## Gold distribution (priors)

| Winner | Share |
|---|---|
| respondent | 83.7% |
| claimant | 16.3% |

| Determination | Share |
|---|---|
| respondent_success | 44.9% |
| non_merits | 38.8% |
| claimant_success | 16.3% |

## Overall metrics (positive class = `Winner.RESPONDENT`)

| Mode | n | Accuracy | Bal-Accuracy | Brier (R) | ECE | LogLoss | Det-Accuracy | Abstain |
|---|---|---|---|---|---|---|---|---|
| `prior_baseline` | 49 | 0.8367 | 0.5000 | 0.1366 | 0.0000 | 0.4450 | 0.4490 | 0.0% |
| `blind_llm` | 49 | 0.8367 | 0.5000 | 0.1364 | 0.0041 | 0.4441 | 0.4490 | 0.0% |
| `facts_llm` | 49 | 0.8571 | 0.5625 | 0.1232 | 0.0141 | 0.4113 | 0.4286 | 2.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `prior_baseline` | 0.0000 (n=8) | 1.0000 (n=41) |
| `blind_llm` | 0.0000 (n=8) | 1.0000 (n=41) |
| `facts_llm` | 0.1250 (n=8) | 1.0000 (n=41) |

## Stratified — by gold `determination`

### `prior_baseline`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.0000 | 0.7001 |
| non_merits | 19 | 1.0000 | 0.0267 |
| respondent_success | 22 | 1.0000 | 0.0267 |

### `blind_llm`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.0000 | 0.7056 |
| non_merits | 19 | 1.0000 | 0.0254 |
| respondent_success | 22 | 1.0000 | 0.0252 |

### `facts_llm`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.1250 | 0.6329 |
| non_merits | 19 | 1.0000 | 0.0247 |
| respondent_success | 22 | 1.0000 | 0.0230 |

## Stratified — by region (top 8)

### `prior_baseline`
| Region | n | Accuracy |
|---|---|---|
| london | 16 | 0.9375 |
| north_west | 7 | 0.7143 |
| scotland | 6 | 0.8333 |
| south_west | 4 | 0.7500 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

### `blind_llm`
| Region | n | Accuracy |
|---|---|---|
| london | 16 | 0.9375 |
| north_west | 7 | 0.7143 |
| scotland | 6 | 0.8333 |
| south_west | 4 | 0.7500 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

### `facts_llm`
| Region | n | Accuracy |
|---|---|---|
| london | 16 | 0.9375 |
| north_west | 7 | 0.7143 |
| scotland | 6 | 0.8333 |
| south_west | 4 | 1.0000 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

## Error analysis — top-5 largest |P_respondent − actual| per mode

### `prior_baseline`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8367 | 0.8367 | Prior baseline: corpus prior over 2 winner classes is claimant=0.16, respondent= |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8367 | 0.8367 | Prior baseline: corpus prior over 2 winner classes is claimant=0.16, respondent= |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8367 | 0.8367 | Prior baseline: corpus prior over 2 winner classes is claimant=0.16, respondent= |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8367 | 0.8367 | Prior baseline: corpus prior over 2 winner classes is claimant=0.16, respondent= |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8367 | 0.8367 | Prior baseline: corpus prior over 2 winner classes is claimant=0.16, respondent= |

### `blind_llm`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | No factual material was provided; based on historical UK unfair-dismissal statis |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No factual narrative provided; given typical UK unfair-dismissal statistics and  |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | Only metadata provided and no facts to support the claimant; based on typical tr |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | Only metadata provided, so using historical unfair-dismissal corpus priors (resp |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8400 | 0.84 | No factual details were provided; using the historical prior for UK unfair-dismi |

### `facts_llm`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8500 | 0.85 | Insufficient case facts provided; using sector-wide empirical prior that respond |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8500 | 0.85 | No substantive case facts were provided and the historical UK unfair-dismissal c |
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | No substantive case facts were provided and, given the absence of detail plus th |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | The factual narrative is unavailable and, given the empirical prior that most un |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive factual narrative provided and, absent case-specific indicia, his |

## Findings

- **Prior baseline** (always predict majority class respondent at P=0.84) lands at **83.7%** accuracy and Brier **0.1366**. Any meaningful predictor must beat both.
- **Blind LLM** (metadata only — no facts narrative) at **83.7%** accuracy / Brier **0.1364**. Marginal lift over prior: accuracy Δ = **+0.0 pp**, Brier Δ = **+0.0002**.
- **Facts LLM** (metadata + grounded facts) at **85.7%** accuracy / Brier **0.1232**. Marginal lift over blind: accuracy Δ = **+2.0 pp**, Brier Δ = **+0.0131**.
- **Balanced accuracy** (macro-averaged per-class) at facts_llm = **0.5625** — the relevant number when the 84/16 winner skew is suspect of inflating raw accuracy.
- **Determination accuracy** at facts_llm = **42.9%**. This is the 4-class task (claimant_success / respondent_success / partial_success / non_merits), which carries more signal than the binary winner.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- This eval intentionally does NOT use RAG / KG retrieval. SHA-147 deferred vector ingestion; SHA-149 (employment factor catalog) has not been built. The contrast is prior vs blind vs facts only — not the housing four-mode ablation.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).