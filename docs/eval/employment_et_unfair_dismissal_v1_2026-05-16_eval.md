# Employment Tribunal eval — `employment.unfair_dismissal.v1`

**Gold:** [`data/gold_standard/employment_unfair_dismissal_v1.jsonl`](../../data/gold_standard/employment_unfair_dismissal_v1.jsonl)
**Run dir:** `data/eval_artifacts/runs/employment_unfair_dismissal_v1/sha149-run-a-1779018524`
**Run ID:** `sha149-run-a-1779018524`
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
| `llm_only` | 49 | 0.8571 | 0.6631 | 0.1211 | 0.0471 | 0.4059 | 0.5918 | 0.0% |
| `rag_only` | 49 | 0.8571 | 0.6631 | 0.1209 | 0.0659 | 0.4029 | 0.5510 | 0.0% |
| `kg_only` | 49 | 0.8571 | 0.6631 | 0.1108 | 0.0922 | 0.3722 | 0.6327 | 0.0% |
| `hybrid` | 49 | 0.8367 | 0.6006 | 0.1295 | 0.0743 | 0.4257 | 0.6122 | 0.0% |

*Brier reading: 0.0 = perfect, 0.25 = coin flip, ≥ 0.25 = worse than chance.*

## Per-class accuracy

| Mode | claimant | respondent |
|---|---|---|
| `llm_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `rag_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `kg_only` | 0.3750 (n=8) | 0.9512 (n=41) |
| `hybrid` | 0.2500 (n=8) | 0.9512 (n=41) |

## Stratified — by gold `determination`

### `llm_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4736 |
| non_merits | 19 | 0.8947 | 0.0897 |
| respondent_success | 22 | 1.0000 | 0.0200 |

### `rag_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.4491 |
| non_merits | 19 | 0.8947 | 0.0979 |
| respondent_success | 22 | 1.0000 | 0.0214 |

### `kg_only`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.3750 | 0.3769 |
| non_merits | 19 | 0.8947 | 0.0981 |
| respondent_success | 22 | 1.0000 | 0.0249 |

### `hybrid`
| Determination | n | Accuracy | Brier (R) |
|---|---|---|---|
| claimant_success | 8 | 0.2500 | 0.5285 |
| non_merits | 19 | 0.8947 | 0.0880 |
| respondent_success | 22 | 1.0000 | 0.0202 |

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
| scotland | 6 | 0.6667 |
| south_west | 4 | 1.0000 |
| south_east | 3 | 0.6667 |
| wales | 3 | 0.6667 |
| yorkshire_and_humber | 3 | 1.0000 |
| east_of_england | 2 | 0.5000 |

## Error analysis — top-5 largest |P_respondent − actual| per mode

### `llm_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8800 | 0.88 | No substantive merits facts were provided and the respondent was legally represe |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8800 | 0.88 | Most persuasive signal is that the dismissal was for redundancy and the responde |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent did not file any response and failed to attend the hearing (default), |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8400 | 0.84 | No substantive merits facts were provided and the respondent was represented by  |
| mr-m-nutt-v-dhl-services-ltd-3310770-slash-2024 | claimant | respondent | 0.8400 | 0.84 | Both parties were legally represented and the file contains no substantive factu |

### `rag_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | Respondent represented by counsel while the claimant only participated with an i |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent’s complete failure to file an ET3 or attend the hearing (no response  |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8600 | 0.86 | Closest matching precedent Mr L Hounsome v Team Industrial Services UK Ltd (resp |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | There are no substantive merits facts or SHA-149 factor assertions (only hearing |
| d-spencer-v-deckhouse-sevenoaks-ltd-6021339-slas | respondent | claimant | 0.1800 | 0.82 | Strongest signal is that the respondent did not attend the hearing (respondent f |

### `kg_only`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8800 | 0.88 | Respondent was legally represented while the KG shows respondent_failed_to_engag |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent failed to engage (no response filed and did not attend the hearing) — |
| d-spencer-v-deckhouse-sevenoaks-ltd-6021339-slas | respondent | claimant | 0.1800 | 0.82 | The strongest signal is the respondent's failure to engage and non‑attendance at |
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.8200 | 0.82 | The strongest signal is the KG assertion that the dismissal was for redundancy ( |
| mr-r-thomas-v-mid-and-west-wales-fire-and-rescue | claimant | respondent | 0.7200 | 0.72 | The only clear structured signal is claimant_represented_at_hearing=true (knowle |

### `hybrid`
| case_id | gold | predicted | P(resp) | |err| | rationale |
|---|---|---|---|---|---|
| mrs-s-begum-v-design-clinics-ltd-6000457-slash-2 | claimant | respondent | 0.9200 | 0.92 | The KG identifies the fair reason as redundancy (pro_respondent) and the respond |
| m-elnaem-v-serco-ltd-2403227-slash-2024 | claimant | respondent | 0.8800 | 0.88 | Prediction driven by the procedural signals in the knowledge graph — the claiman |
| s-struthers-v-hamilton-academical-football-club- | respondent | claimant | 0.1200 | 0.88 | Respondent did not file an ET3 or attend the merits hearing (knowledge_graph fac |
| s-okan-v-global-edge-consultant-uk-ltd-8002882-s | claimant | respondent | 0.8500 | 0.85 | The SHA-149 sidecar flags is_preliminary_or_strike_out_hearing=true (confidence  |
| mr-a-tomescu-v-metroline-travel-ltd-3302505-slas | claimant | respondent | 0.8400 | 0.84 | No substantive merits facts or matching precedents were retrieved and the KG sho |

## Findings

- **Prior P(respondent)** in this gold set is **0.84** — a majority-class predictor would already hit ~83% raw accuracy. Use **balanced accuracy** and **Brier** as the non-degenerate signals.
- **`llm_only`** (facts only — no retrieval, no KG) reaches **85.7%** accuracy / Brier **0.1211** / balanced **0.6631**. This is the floor for the ablation.
- **`rag_only`** (facts + retrieved precedents, leave-one-out) at **85.7%** / Brier **0.1209**. Marginal value of retrieval over llm_only: accuracy +0.0 pp, Brier +0.0002.
- **`kg_only`** (facts + SHA-149 factor digest) at **85.7%** / Brier **0.1108** / det-acc **63.3%**. Marginal value of structured factors over llm_only: accuracy +0.0 pp, Brier +0.0103, det-acc +4.1 pp. The SHA-149 factor sidecar provides 108 typed factor assertions (12 distinct factor_ids, mean 2.2/case) extracted by gpt-5-mini against the leakage-cleaned facts narrative.
- **`hybrid`** (facts + retrieved precedents + KG digest) at **83.7%** / Brier **0.1295** / balanced **0.6006**. Lift over llm_only: accuracy -2.0 pp, Brier -0.0084. Determination-accuracy = **61.2%**.
- **Single-run noise warning**: with 8 minority-class claimant cases in n=49, one Pyman/Spencer-shaped LLM flip moves headline accuracy ~2pp. Treat single-run accuracy gaps under 4pp as likely-noise and prefer **balanced accuracy**, **Brier**, and **determination accuracy** as the signal-bearing metrics. `scripts/eval/aggregate_employment_et_runs.py` produces mean ± std across multiple runs.
- **Post-SHA-149 synthesis**: with the factor sidecar wired into kg_only and hybrid, the strongest mode by **Brier** is **`kg_only`** (0.1108); strongest by **determination accuracy** is **`kg_only`** (63.3%). The 12-factor SHA-149 catalog provides real merits signal — the digest is no longer the empty 3-node housing-adapter stub it was pre-SHA-149. `hybrid` still pays a Brier overhead over kg_only/rag_only on this n=49 corpus because the LLM hedges more when given both retrieval and factor inputs; a larger gold set is needed to resolve sub-0.02 Brier differences.

## Caveats

- The gold rows themselves were produced by a same-provider dual-LLM panel (gpt-5.5 + gpt-5-mini) with mean IAA 0.55 and auto-promoted per the user's 2026-05-16 decision. Predictions vs gold therefore measure predictor agreement with an LLM-derived label, NOT agreement with human-adjudicated ground truth. Phase D refinement would tighten this.
- The ``facts`` field on 39/49 rows was the Phase D auto-promote placeholder until 2026-05-16, at which point the gold was re-extracted via ``scripts/eval/extract_employment_et_facts.py``. The re-extractor runs gpt-5-mini against the redacted PDF text with a leakage guard that blocks tribunal-voice, outcome verdicts, remedy-stage references, and statutory-award names. Every row was audited against the formal guard plus an adversarial-phrase sweep before promotion (0 placeholder / 0 formal-leak / 0 adversarial).
- Same-provider LLM stack across labelers AND predictor introduces correlated bias — both sides may share the same blind spots (e.g. over-emitting `non_merits` on cases where the s98 framework isn't visible in the chunked PDF text).
- Brier/ECE are computed only over rows where the gold winner is claimant or respondent (binary). `Winner.SPLIT` is excluded from calibration because the actual is neither 0 nor 1; if a future run carries any split rows the calibration n will drop accordingly.
- Retrieval pool: the 50-doc SHA-148 ET corpus (47-49 peers per query under leave-one-out). RAG modes use production `RAGPipeline` (BM25 + embeddings + RRF + reranker); KG modes use production `GraphBuilder`. Retrieved chunks carry parent-case outcomes (`precedent_outcome_winner`, `precedent_outcome_determination`) joined from the gold itself, so the LLM has case-based-reasoning material per chunk.
- The KG digest carries (a) SHA-149 typed factor assertions (12-factor closed catalog at `packages/domain_packs/employment/unfair_dismissal/factors.yaml`; 108 total assertions across 49 cases, mean 2.2/case, extracted by `scripts/eval/extract_employment_et_factors.py` with leakage guard); (b) case-distinct procedural metadata (`parties_by_role` representation status, `region`); and (c) structural KG-build counts. Pre-SHA-149 the digest was byte-identical across 49 cases (1/49 unique hashes); post-SHA-149 the digest is 49/49 unique by factor profile.
- LLM determinism: gpt-5-mini is a reasoning model and produces 1-2 case flips per run even at temperature=0 (thinking-token drift). Across 3 independent runs on the same gold set, raw accuracy varies by ±1-2pp per mode. The numbers in this report are from one of those runs; see `data/eval_artifacts/runs/employment_unfair_dismissal_v1/_aggregate_3runs_2026-05-16.json` for the multi-run mean ± std.
- The corpus is heavily skewed to 2025-2026 decisions (97% of gold). Train/test temporal-split conclusions would need a multi-year corpus which GOV.UK's ET listing does not currently support (the date filter is unhonoured server-side and pagination caps at ~3 years).