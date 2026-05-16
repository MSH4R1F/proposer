# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/20260516T105031Z-18fdcbc9-emp-et-predict`
**Run ID:** `20260516T105031Z-18fdcbc9-emp-et-predict`
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
| `llm_only` | 49 | 0.8571 | 0.5625 | 0.1224 | 0.0151 | 0.4090 | 0.4490 | 0.0% |
| `rag_only` | 49 | 0.8571 | 0.5625 | 0.1231 | 0.0155 | 0.4115 | 0.4490 | 0.0% |
| `kg_only` | 49 | 0.8367 | 0.5000 | 0.1360 | 0.0065 | 0.4428 | 0.4286 | 0.0% |
| `hybrid` | 49 | 0.8571 | 0.5625 | 0.1225 | 0.0127 | 0.4093 | 0.4694 | 0.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `llm_only` | 0.1250 (n=8) | 1.0000 (n=41) |
| `rag_only` | 0.1250 (n=8) | 1.0000 (n=41) |
| `kg_only` | 0.0000 (n=8) | 1.0000 (n=41) |
| `hybrid` | 0.1250 (n=8) | 1.0000 (n=41) |

## Stratified — by gold `determination`

### `llm_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.1250 | 0.6234 |
| non_merits | 19 | 1.0000 | 0.0248 |
| respondent_success | 22 | 1.0000 | 0.0244 |

### `rag_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.1250 | 0.6274 |
| non_merits | 19 | 1.0000 | 0.0253 |
| respondent_success | 22 | 1.0000 | 0.0241 |

### `kg_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.0000 | 0.7077 |
| non_merits | 19 | 1.0000 | 0.0251 |
| respondent_success | 22 | 1.0000 | 0.0240 |

### `hybrid`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.1250 | 0.6277 |
| non_merits | 19 | 1.0000 | 0.0240 |
| respondent_success | 22 | 1.0000 | 0.0238 |

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
| north_west | 7 | 0.7143 |
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
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | The file contains no substantive factual details to support the claimant and, fo |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No case-specific facts were supplied; absent contrary indicators I apply the 202 |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No substantive case facts were provided; absent evidence to the contrary I apply |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No case facts were provided; absent distinguishing evidence, apply the 2026 corp |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8400 | 0.84 | No substantive case facts were provided, so prediction defaults to the corpus pr |

### `rag_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8600 | 0.86 | With no case-specific facts provided and retrieved precedents largely reflecting |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8500 | 0.85 | No grounded case facts were supplied and the retrieved precedents concern seriou |
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | No case-specific facts were supplied and the retrieved precedents emphasize that |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No case-specific facts were supplied and the retrieved precedents concern routin |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8400 | 0.84 | No substantive case facts were provided and the retrieved precedents focus on mi |

### `kg_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| r-pyman-v-alitex-ltd-1400384-slash-2025 | claimant | respondent | 0.8500 | 0.85 | The knowledge-graph is minimal and contains no asserted procedural or substantiv |
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | The knowledge graph contains minimal information (no factual assertions or evide |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive facts or factor assertions are provided and the knowledge graph i |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | The knowledge graph contains minimal factual or evidential detail and no asserte |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | The knowledge graph contains no substantive facts or pleaded factors and is mini |

### `hybrid`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8500 | 0.85 | No substantive case facts or factor assertions were provided and, absent evidenc |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8500 | 0.85 | Given minimal case-specific facts and no presented factor assertions or evidence |
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | There are no substantive case facts or factor assertions in the file and the ret |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | With minimal factual detail provided and no strong indicators of procedural or s |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | Given the absence of detailed claimant facts and the retrieved precedents showin |

## Findings

- **Prior P(respondent)** in this gold set is **0.84** — a majority-class predictor would already hit ~83% raw accuracy. Use **balanced accuracy** and **Brier** as the non-degenerate signals.
- **`llm_only`** (facts only — no retrieval, no KG) reaches **85.7%** accuracy / Brier **0.1224** / balanced **0.5625**. This is the floor for the ablation.
- **`rag_only`** (facts + retrieved precedents, leave-one-out) at **85.7%** / Brier **0.1231**. Marginal value of retrieval over llm_only: accuracy +0.0 pp, Brier -0.0007.
- **`kg_only`** (facts + structured KG digest) at **83.7%** / Brier **0.1360**. Marginal value of KG over llm_only: accuracy -2.0 pp, Brier -0.0137. The employment KG is data-quality `minimal` today (SHA-149 factor catalog deferred), so a flat result here is the expected null.
- **`hybrid`** (facts + retrieved precedents + KG digest) at **85.7%** / Brier **0.1225** / balanced **0.5625**. Lift over llm_only: accuracy +0.0 pp, Brier -0.0001. Determination-accuracy = **46.9%**.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- Retrieval pool: the 50-doc SHA-148 ET corpus (47-49 peers per query under leave-one-out). RAG modes use production `RAGPipeline` (BM25 + embeddings + RRF + reranker); KG modes use production `GraphBuilder`. SHA-149 (employment factor catalog) is not built yet, so the KG digest is structurally minimal (party roles, claim types, no factor assertions). `kg_only` is expected to land close to `llm_only` until SHA-149 lands.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).