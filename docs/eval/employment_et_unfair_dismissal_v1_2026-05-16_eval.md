# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/20260516T153132Z-83b8a1ec-emp-et-predict`
**Run ID:** `20260516T153132Z-83b8a1ec-emp-et-predict`
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
| `llm_only` | 49 | 0.8571 | 0.6631 | 0.1207 | 0.0671 | 0.4007 | 0.5306 | 0.0% |
| `rag_only` | 49 | 0.8776 | 0.6753 | 0.1135 | 0.0739 | 0.3895 | 0.5306 | 0.0% |
| `kg_only` | 49 | 0.8571 | 0.6631 | 0.1178 | 0.0590 | 0.3968 | 0.5306 | 0.0% |
| `hybrid` | 49 | 0.8367 | 0.6006 | 0.1330 | 0.0537 | 0.4348 | 0.5306 | 0.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `llm_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `rag_only` | 0.3750 (n=8) | 0.9756 (n=41) |
| `kg_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `hybrid` | 0.2500 (n=8) | 0.9512 (n=41) |

## Stratified — by gold `determination`

### `llm_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4622 |
| non_merits | 19 | 0.8947 | 0.0918 |
| respondent_success | 22 | 1.0000 | 0.0214 |

### `rag_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4608 |
| non_merits | 19 | 0.9474 | 0.0691 |
| respondent_success | 22 | 1.0000 | 0.0255 |

### `kg_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4509 |
| non_merits | 19 | 0.8947 | 0.0841 |
| respondent_success | 22 | 1.0000 | 0.0257 |

### `hybrid`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.2500 | 0.5545 |
| non_merits | 19 | 0.8947 | 0.0810 |
| respondent_success | 22 | 1.0000 | 0.0246 |

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
| london | 16 | 1.0000 |
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
| south_west | 4 | 1.0000 |
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
| south_west | 4 | 0.7500 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

## Error analysis — top-5 largest |P_respondent − actual| per mode

### `llm_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1500 | 0.85 | Respondent's non-attendance and failure to file any response is the strongest si |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive facts or KG/precedent signals showing procedural or substantive u |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | There are no substantive case facts, KG features, or matching precedents supplie |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive facts about the reason or procedure for dismissal and no preceden |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8400 | 0.84 | No substantive dismissal facts or retrieved precedents were provided in the file |

### `rag_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.9000 | 0.9 | Closest retrieved precedent is A Twigg v Chronicle Software Ltd (6021584/2024) w |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Tribunal is likely to find for the claimant because the respondent did not file  |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | There are no substantive facts on the merits and the retrieved precedents provid |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No substantive dismissal facts or KG factors were provided and the retrieved pre |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8400 | 0.84 | No retrieved precedent chunk shares a meaningful fact pattern with this file and |

### `kg_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | The respondent’s failure to file a response or attend the hearing while the clai |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive facts about the dismissal or comparable precedents and the knowle |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No substantive factual or procedural details are provided (knowledge_graph.data_ |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive case facts or matching precedents were provided and the knowledge |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8400 | 0.84 | There are no substantive facts or precedents to assess (knowledge_graph.data_qua |

### `hybrid`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | No retrieved precedent closely matches and the file contains no pleaded procedur |
| r-pyman-v-alitex-ltd-1400384-slash-2025 | claimant | respondent | 0.8800 | 0.88 | The claimant admitted driving an intoxicated colleague who fell and was injured— |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1500 | 0.85 | The respondent did not file an ET3 or attend the hearing (facts), so the Tribuna |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | There are no substantive case facts (knowledge_graph.data_quality_tier = 'minima |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | There are no substantive case facts and the knowledge_graph reports data_quality |

## Findings

- **Prior P(respondent)** in this gold set is **0.84** — a majority-class predictor would already hit ~83% raw accuracy. Use **balanced accuracy** and **Brier** as the non-degenerate signals.
- **`llm_only`** (facts only — no retrieval, no KG) reaches **85.7%** accuracy / Brier **0.1207** / balanced **0.6631**. This is the floor for the ablation.
- **`rag_only`** (facts + retrieved precedents, leave-one-out) at **87.8%** / Brier **0.1135**. Marginal value of retrieval over llm_only: accuracy +2.0 pp, Brier +0.0072.
- **`kg_only`** (facts + structured KG digest) at **85.7%** / Brier **0.1178**. Marginal value of KG over llm_only: accuracy +0.0 pp, Brier +0.0029. The employment KG is data-quality `minimal` today (the SHA-149 factor catalog has not been built so the digest is a 3-node housing-adapter stub for every case). A flat-or-negative result here is the expected null — the LLM treats the empty KG digest as anti-signal and anchors toward the corpus prior.
- **`hybrid`** (facts + retrieved precedents + KG digest) at **83.7%** / Brier **0.1330** / balanced **0.6006**. Lift over llm_only: accuracy -2.0 pp, Brier -0.0123. Determination-accuracy = **53.1%**.
- **Synthesis**: `rag_only` outperforms `hybrid` (+4.1 pp accuracy, Brier Δ +0.0195). The empty employment KG digest (3-node housing-adapter stub on every case) acts as prompt-context noise that dilutes attention away from the precedent chunks. Until SHA-149 lands a real employment factor catalog, `rag_only` is the production-relevant mode for this domain. `hybrid` becomes the right mode once the KG carries case-distinct factor assertions.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- The ``facts`` field on 39/49 rows was the Phase D auto-promote placeholder until 2026-05-16, at which point the gold was re-extracted via ``scripts/eval/extract_employment_et_facts.py``. The re-extractor runs gpt-5-mini against the redacted PDF text with a leakage guard that blocks tribunal-voice, outcome verdicts, remedy-stage references, and statutory-award names. Every row was audited against the formal guard plus an adversarial-phrase sweep before promotion (0 placeholder / 0 formal-leak / 0 adversarial).
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- Retrieval pool: the 50-doc SHA-148 ET corpus (47-49 peers per query under leave-one-out). RAG modes use production `RAGPipeline` (BM25 + embeddings + RRF + reranker); KG modes use production `GraphBuilder`. SHA-149 (employment factor catalog) is not built yet, so the KG digest is structurally minimal (party roles, claim types, no factor assertions). `kg_only` is expected to land close to `llm_only` until SHA-149 lands.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).