# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/20260516T160316Z-4bbe35f2-emp-et-predict`
**Run ID:** `20260516T160316Z-4bbe35f2-emp-et-predict`
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
| `llm_only` | 49 | 0.8571 | 0.6631 | 0.1229 | 0.0696 | 0.4073 | 0.5306 | 0.0% |
| `rag_only` | 49 | 0.8571 | 0.7134 | 0.1238 | 0.0845 | 0.4095 | 0.5918 | 0.0% |
| `kg_only` | 49 | 0.8367 | 0.6006 | 0.1293 | 0.0616 | 0.4224 | 0.5102 | 0.0% |
| `hybrid` | 49 | 0.8163 | 0.6387 | 0.1387 | 0.0896 | 0.4470 | 0.5510 | 0.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `llm_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `rag_only` | 0.5000 (n=8) | 0.9268 (n=41) |
| `kg_only` | 0.2500 (n=8) | 0.9512 (n=41) |
| `hybrid` | 0.3750 (n=8) | 0.9024 (n=41) |

## Stratified — by gold `determination`

### `llm_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4508 |
| non_merits | 19 | 0.8947 | 0.0986 |
| respondent_success | 22 | 1.0000 | 0.0247 |

### `rag_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.5000 | 0.4133 |
| non_merits | 19 | 0.8421 | 0.1173 |
| respondent_success | 22 | 1.0000 | 0.0241 |

### `kg_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.2500 | 0.5128 |
| non_merits | 19 | 0.8947 | 0.0931 |
| respondent_success | 22 | 1.0000 | 0.0212 |

### `hybrid`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4811 |
| non_merits | 19 | 0.8421 | 0.1085 |
| respondent_success | 22 | 0.9545 | 0.0403 |

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
| london | 16 | 0.8750 |
| north_west | 7 | 0.5714 |
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
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | Strongest signal is that the claimant was self-represented while the respondent  |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent filed no response and did not attend the hearing whereas the claimant |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive dismissal facts were provided and the claimant appeared unreprese |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No substantive facts or matching precedents were provided and the respondent was |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive merits or factual detail were supplied and both parties were lega |

### `rag_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | The claimant attended unrepresented (assisted only by an interpreter) while the  |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8800 | 0.88 | Respondent was legally represented (Miss C Nicolaou, solicitor) while no retriev |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent did not file an ET3 and did not attend the merits hearing (strong def |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.8500 | 0.85 | No substantive merits facts were provided and the closest retrieved precedent (m |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No retrieved precedent shares a meaningful fact pattern with this file and, with |

### `kg_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | No substantive facts or matching precedents were provided and the knowledge_grap |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8800 | 0.88 | Prediction driven by KG signal that the claimant was unrepresented while the res |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | Strongest signal: claimant was self‑represented (knowledge_graph parties_by_role |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent's failure to file any response and non-attendance at the hearing (cla |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive case facts or retrieved precedents were provided and both parties |

### `hybrid`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.9000 | 0.9 | Closest precedent ms-jones-v-birmingham-city-council (precedent_outcome_winner:  |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | No substantive merits facts and the knowledge-graph signal that the claimant was |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | No factual material shows an unfair redundancy procedure and the respondent was  |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Strongest signal: the respondent did not file a response and did not attend the  |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No retrieved precedent shares meaningful merits facts and the case file gives no |

## Findings

- **Prior P(respondent)** in this gold set is **0.84** — a majority-class predictor would already hit ~83% raw accuracy. Use **balanced accuracy** and **Brier** as the non-degenerate signals.
- **`llm_only`** (facts only — no retrieval, no KG) reaches **85.7%** accuracy / Brier **0.1229** / balanced **0.6631**. This is the floor for the ablation.
- **`rag_only`** (facts + retrieved precedents, leave-one-out) at **85.7%** / Brier **0.1238**. Marginal value of retrieval over llm_only: accuracy +0.0 pp, Brier -0.0009.
- **`kg_only`** (facts + structured KG digest) at **83.7%** / Brier **0.1293**. Marginal value of KG over llm_only: accuracy -2.0 pp, Brier -0.0064. The employment KG is data-quality `minimal` today (the SHA-149 factor catalog has not been built so the digest is a 3-node housing-adapter stub for every case). A flat-or-negative result here is the expected null — the LLM treats the empty KG digest as anti-signal and anchors toward the corpus prior.
- **`hybrid`** (facts + retrieved precedents + KG digest) at **81.6%** / Brier **0.1387** / balanced **0.6387**. Lift over llm_only: accuracy -4.1 pp, Brier -0.0158. Determination-accuracy = **55.1%**.
- **Single-run noise warning**: with 8 minority-class claimant cases in n=49, one Pyman/Spencer-shaped LLM flip moves headline accuracy ~2pp. Treat single-run accuracy gaps under 4pp as likely-noise and prefer **balanced accuracy**, **Brier**, and **determination accuracy** as the signal-bearing metrics. `scripts/eval/aggregate_employment_et_runs.py` produces mean ± std across multiple runs.
- **Synthesis**: `rag_only` remains the production-relevant mode on this corpus. Empirically (3-run mean): rag_only carries the strongest per-class signal — best balanced accuracy (0.676 vs 0.642 for llm_only/kg_only), best determination accuracy (56.5% vs 53.1-53.7%). `hybrid` ties on raw accuracy within noise but consistently carries 5-8% higher Brier across runs — the LLM appears to hedge more when both retrieval and KG inputs are present. `hybrid` should overtake `rag_only` once SHA-149 lands case-distinct factor assertions; the current enriched-but-thin KG digest (parties_by_role + region) is too weak to add net signal on top of retrieval.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- The ``facts`` field on 39/49 rows was the Phase D auto-promote placeholder until 2026-05-16, at which point the gold was re-extracted via ``scripts/eval/extract_employment_et_facts.py``. The re-extractor runs gpt-5-mini against the redacted PDF text with a leakage guard that blocks tribunal-voice, outcome verdicts, remedy-stage references, and statutory-award names. Every row was audited against the formal guard plus an adversarial-phrase sweep before promotion (0 placeholder / 0 formal-leak / 0 adversarial).
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- Retrieval pool: the 50-doc SHA-148 ET corpus (47-49 peers per query under leave-one-out). RAG modes use production `RAGPipeline` (BM25 + embeddings + RRF + reranker); KG modes use production `GraphBuilder`. Retrieved chunks carry parent-case outcomes (`precedent_outcome_winner`, `precedent_outcome_determination`) joined from the gold itself, so the LLM has case-based-reasoning material per chunk.
- The KG digest contains case-distinct procedural metadata only (`parties_by_role` representation status, `region`) plus the structural KG-build counts. Before 2026-05-16 the digest was byte-identical across all 49 cases (`data_quality_tier=minimal`, `factor_assertions=[]`, etc.); the LLM read those constant flags as 'no signal, fall back to prior' which structurally hurt `hybrid`. The enriched digest produces 22/49 unique digests and no longer acts as anti-signal. SHA-149 (employment factor catalog) is needed for the digest to carry merits signal beyond procedural metadata.
- LLM determinism: gpt-5-mini is a reasoning model and produces 1-2 case flips per run even at temperature=0 (thinking-token drift). Across 3 independent runs on the same gold set, raw accuracy varies by ±1-2pp per mode. The numbers in this report are from one of those runs; see `data/eval_artifacts/runs/employment_unfair_dismissal_v1/_aggregate_3runs_2026-05-16.json` for the multi-run mean ± std.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).