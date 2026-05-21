# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/sha149-fixv4-b-1779021144`
**Run ID:** `sha149-fixv4-b-1779021144`
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
| `llm_only` | 49 | 0.8571 | 0.6631 | 0.1228 | 0.0610 | 0.4082 | 0.5510 | 0.0% |
| `rag_only` | 49 | 0.8367 | 0.6509 | 0.1288 | 0.0631 | 0.4199 | 0.5714 | 0.0% |
| `kg_only` | 49 | 0.8367 | 0.6509 | 0.1281 | 0.0837 | 0.4161 | 0.6122 | 0.0% |
| `hybrid` | 49 | 0.8571 | 0.6631 | 0.1172 | 0.1008 | 0.3874 | 0.6327 | 0.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `llm_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `rag_only` | 0.3750 (n=8) | 0.9268 (n=41) |
| `kg_only` | 0.3750 (n=8) | 0.9268 (n=41) |
| `hybrid` | 0.3750 (n=8) | 0.9512 (n=41) |

## Stratified — by gold `determination`

### `llm_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4507 |
| non_merits | 19 | 0.8947 | 0.0974 |
| respondent_success | 22 | 1.0000 | 0.0255 |

### `rag_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4506 |
| non_merits | 19 | 0.8421 | 0.1154 |
| respondent_success | 22 | 1.0000 | 0.0234 |

### `kg_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4464 |
| non_merits | 19 | 0.8421 | 0.1198 |
| respondent_success | 22 | 1.0000 | 0.0196 |

### `hybrid`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4187 |
| non_merits | 19 | 0.8947 | 0.1002 |
| respondent_success | 22 | 1.0000 | 0.0223 |

## Stratified — by region (top 8)

### `llm_only`
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

### `rag_only`
| Region | n | Accuracy |
|---|---|---|
| london | 16 | 0.9375 |
| north_west | 7 | 0.5714 |
| scotland | 6 | 0.8333 |
| south_west | 4 | 1.0000 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

### `kg_only`
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

### `hybrid`
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

### `llm_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| d-spencer-v-deckhouse-sevenoaks-ltd-6021339-slas | respondent | claimant | 0.1500 | 0.85 | Strong procedural signal: the respondent did not attend the hearing (respondent  |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1500 | 0.85 | Respondent failed to engage (no response filed and did not attend the hearing),  |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No case-specific merits or SHA-149 factors were provided and the respondent was  |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No case-specific merits facts, SHA-149 factors, or similar precedents were provi |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No merits facts, factor assertions or matching precedents were provided and both |

### `rag_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8800 | 0.88 | No retrieved precedent shared meaningful matching merits facts and the responden |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | The respondent made an early part redundancy payment (£3,494.04) and was represe |
| d-spencer-v-deckhouse-sevenoaks-ltd-6021339-slas | respondent | claimant | 0.1500 | 0.85 | Respondent did not attend the hearing (respondent_failed_to_engage), indicating  |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1500 | 0.85 | The respondent failed to engage (no ET3 filed and did not attend the hearing), a |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8200 | 0.82 | Both parties were represented by counsel and the case was heard and decided at a |

### `kg_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | Strongest signal: the claimant was not represented at the hearing while the resp |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8800 | 0.88 | High likelihood respondent wins because the structured factor shows respondent_f |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | High-confidence KG factor fair_reason_category='redundancy' (confidence 0.98), t |
| d-spencer-v-deckhouse-sevenoaks-ltd-6021339-slas | respondent | claimant | 0.1500 | 0.85 | Respondent did not attend and sha149 factor respondent_failed_to_engage=True (co |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1500 | 0.85 | Respondent failed to file a response and did not attend the hearing—sha149 facto |

### `hybrid`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | High-confidence KG signals that the respondent engaged (respondent_failed_to_eng |
| d-spencer-v-deckhouse-sevenoaks-ltd-6021339-slas | respondent | claimant | 0.1500 | 0.85 | Respondent did not attend (facts) and knowledge_graph flags respondent_failed_to |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1500 | 0.85 | Tribunal record and a high-confidence SHA-149 factor (respondent_failed_to_engag |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8200 | 0.82 | High-confidence SHA-149 factor that the fair reason was redundancy (fair_reason_ |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.7800 | 0.78 | The structured factor that the respondent did engage (respondent_failed_to_engag |

## Findings

- **Prior P(respondent)** in this gold set is **0.84** — a majority-class predictor would already hit ~83% raw accuracy. Use **balanced accuracy** and **Brier** as the non-degenerate signals.
- **`llm_only`** (facts only — no retrieval, no KG) reaches **85.7%** accuracy / Brier **0.1228** / balanced **0.6631**. This is the floor for the ablation.
- **`rag_only`** (facts + retrieved precedents, leave-one-out) at **83.7%** / Brier **0.1288**. Marginal value of retrieval over llm_only: accuracy -2.0 pp, Brier -0.0060.
- **`kg_only`** (facts + SHA-149 factor digest) at **83.7%** / Brier **0.1281** / det-acc **61.2%**. Marginal value of structured factors over llm_only: accuracy -2.0 pp, Brier -0.0053, det-acc +6.1 pp. The SHA-149 factor sidecar provides 108 typed factor assertions (12 distinct factor_ids, mean 2.2/case) extracted by gpt-5-mini against the leakage-cleaned facts narrative.
- **`hybrid`** (facts + retrieved precedents + KG digest) at **85.7%** / Brier **0.1172** / balanced **0.6631**. Lift over llm_only: accuracy +0.0 pp, Brier +0.0056. Determination-accuracy = **63.3%**.
- **Single-run noise warning**: with 8 minority-class claimant cases in n=49, one Pyman/Spencer-shaped LLM flip moves headline accuracy ~2pp. Treat single-run accuracy gaps under 4pp as likely-noise and prefer **balanced accuracy**, **Brier**, and **determination accuracy** as the signal-bearing metrics. `scripts/eval/aggregate_employment_et_runs.py` produces mean ± std across multiple runs.
- **Post-SHA-149 synthesis**: with the factor sidecar wired into kg_only and hybrid, the strongest mode by **Brier** is **`hybrid`** (0.1172); strongest by **determination accuracy** is **`hybrid`** (63.3%). The 12-factor SHA-149 catalog provides real merits signal — the digest is no longer the empty 3-node housing-adapter stub it was pre-SHA-149. `hybrid` still pays a Brier overhead over kg_only/rag_only on this n=49 corpus because the LLM hedges more when given both retrieval and factor inputs; a larger gold set is needed to resolve sub-0.02 Brier differences.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- The ``facts`` field on 39/49 rows was the Phase D auto-promote placeholder until 2026-05-16, at which point the gold was re-extracted via ``scripts/eval/extract_employment_et_facts.py``. The re-extractor runs gpt-5-mini against the redacted PDF text with a leakage guard that blocks tribunal-voice, outcome verdicts, remedy-stage references, and statutory-award names. Every row was audited against the formal guard plus an adversarial-phrase sweep before promotion (0 placeholder / 0 formal-leak / 0 adversarial).
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- Retrieval pool: the 50-doc SHA-148 ET corpus (47-49 peers per query under leave-one-out). RAG modes use production `RAGPipeline` (BM25 + embeddings + RRF + reranker); KG modes use production `GraphBuilder`. Retrieved chunks carry parent-case outcomes (`precedent_outcome_winner`, `precedent_outcome_determination`) joined from the gold itself, so the LLM has case-based-reasoning material per chunk.
- The KG digest carries (a) SHA-149 typed factor assertions (12-factor closed catalog at `packages/domain_packs/employment/unfair_dismissal/factors.yaml`; 108 total assertions across 49 cases, mean 2.2/case, extracted by `scripts/eval/extract_employment_et_factors.py` with leakage guard); (b) case-distinct procedural metadata (`parties_by_role` representation status, `region`); and (c) structural KG-build counts. Pre-SHA-149 the digest was byte-identical across 49 cases (1/49 unique hashes); post-SHA-149 the digest is 49/49 unique by factor profile.
- LLM determinism: gpt-5-mini is a reasoning model and produces 1-2 case flips per run even at temperature=0 (thinking-token drift). Across 3 independent runs on the same gold set, raw accuracy varies by ±1-2pp per mode. The numbers in this report are from one of those runs; see `data/eval_artifacts/runs/employment_unfair_dismissal_v1/_aggregate_3runs_2026-05-16.json` for the multi-run mean ± std.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).