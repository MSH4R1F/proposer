# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/20260516T143151Z-bc3ed9bb-emp-et-predict`
**Run ID:** `20260516T143151Z-bc3ed9bb-emp-et-predict`
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
| `llm_only` | 49 | 0.8571 | 0.6631 | 0.1183 | 0.0665 | 0.3999 | 0.5510 | 0.0% |
| `rag_only` | 49 | 0.8571 | 0.6631 | 0.1178 | 0.0535 | 0.3966 | 0.5510 | 0.0% |
| `kg_only` | 49 | 0.8367 | 0.5503 | 0.1315 | 0.0241 | 0.4298 | 0.4694 | 0.0% |
| `hybrid` | 49 | 0.8776 | 0.6753 | 0.1047 | 0.0559 | 0.3627 | 0.5306 | 0.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `llm_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `rag_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `kg_only` | 0.1250 (n=8) | 0.9756 (n=41) |
| `hybrid` | 0.3750 (n=8) | 0.9756 (n=41) |

## Stratified — by gold `determination`

### `llm_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4591 |
| non_merits | 19 | 0.8947 | 0.0842 |
| respondent_success | 22 | 1.0000 | 0.0239 |

### `rag_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4671 |
| non_merits | 19 | 0.8947 | 0.0794 |
| respondent_success | 22 | 1.0000 | 0.0238 |

### `kg_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.1250 | 0.6244 |
| non_merits | 19 | 0.9474 | 0.0479 |
| respondent_success | 22 | 1.0000 | 0.0243 |

### `hybrid`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4528 |
| non_merits | 19 | 0.9474 | 0.0512 |
| respondent_success | 22 | 1.0000 | 0.0243 |

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
| london | 16 | 0.8750 |
| north_west | 7 | 0.7143 |
| scotland | 6 | 1.0000 |
| south_west | 4 | 0.7500 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

### `hybrid`
| Region | n | Accuracy |
|---|---|---|
| london | 16 | 1.0000 |
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
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | The respondent did not file a response or attend the hearing, so the Tribunal is |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8500 | 0.85 | The file supplies no substantive facts about the reasonableness or procedural de |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive facts or indicators of procedural or substantive unfairness were  |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | The provided file contains no substantive facts showing unfairness or procedural |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive factual or legal material was provided on the merits; absent evid |

### `rag_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8600 | 0.86 | No substantive factual indicators of a sustainable unfair‑dismissal breach were  |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8600 | 0.86 | The file contains no substantive merits or procedural facts favoring the claiman |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive merits or evidence of unfair procedure or qualifying-service issu |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No case-specific facts or indicia of unfair procedure/substantive fault were pro |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8300 | 0.83 | The provided facts contain no evidence of procedural or substantive unfairness ( |

### `kg_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8500 | 0.85 | The knowledge graph contains no substantive facts or asserted factors to support |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8500 | 0.85 | The knowledge graph is minimal with no asserted adverse factors or procedural fa |
| k-bal-v-the-sofa-and-chair-company-in-voluntary- | claimant | respondent | 0.8400 | 0.84 | The knowledge graph contains minimal factual or factor assertions and no support |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | The knowledge graph contains minimal, non-specific information and no factor ass |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | The knowledge‑graph contains no substantive facts or adverse factor assertions a |

### `hybrid`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8500 | 0.85 | No substantive factual or legal detail was supplied and the knowledge graph is m |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | The case file contains no substantive factual or legal indicators supporting unf |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No substantive factual or legal signals of claimant success are provided and, ab |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive facts or issues were provided and, given the minimal case record  |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8400 | 0.84 | With only a redundancy dismissal pleaded, no detailed allegations of procedural  |

## Findings

- **Prior P(respondent)** in this gold set is **0.84** — a majority-class predictor would already hit ~83% raw accuracy. Use **balanced accuracy** and **Brier** as the non-degenerate signals.
- **`llm_only`** (facts only — no retrieval, no KG) reaches **85.7%** accuracy / Brier **0.1183** / balanced **0.6631**. This is the floor for the ablation.
- **`rag_only`** (facts + retrieved precedents, leave-one-out) at **85.7%** / Brier **0.1178**. Marginal value of retrieval over llm_only: accuracy +0.0 pp, Brier +0.0006.
- **`kg_only`** (facts + structured KG digest) at **83.7%** / Brier **0.1315**. Marginal value of KG over llm_only: accuracy -2.0 pp, Brier -0.0131. The employment KG is data-quality `minimal` today (the SHA-149 factor catalog has not been built so the digest is a 3-node housing-adapter stub for every case). A flat-or-negative result here is the expected null — the LLM treats the empty KG digest as anti-signal and anchors toward the corpus prior.
- **`hybrid`** (facts + retrieved precedents + KG digest) at **87.8%** / Brier **0.1047** / balanced **0.6753**. Lift over llm_only: accuracy +2.0 pp, Brier +0.0137. Determination-accuracy = **53.1%**.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- The ``facts`` field on 39/49 rows was the Phase D auto-promote placeholder until 2026-05-16, at which point the gold was re-extracted via ``scripts/eval/extract_employment_et_facts.py``. The re-extractor runs gpt-5-mini against the redacted PDF text with a leakage guard that blocks tribunal-voice, outcome verdicts, remedy-stage references, and statutory-award names. Every row was audited against the formal guard plus an adversarial-phrase sweep before promotion (0 placeholder / 0 formal-leak / 0 adversarial).
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- Retrieval pool: the 50-doc SHA-148 ET corpus (47-49 peers per query under leave-one-out). RAG modes use production `RAGPipeline` (BM25 + embeddings + RRF + reranker); KG modes use production `GraphBuilder`. SHA-149 (employment factor catalog) is not built yet, so the KG digest is structurally minimal (party roles, claim types, no factor assertions). `kg_only` is expected to land close to `llm_only` until SHA-149 lands.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).