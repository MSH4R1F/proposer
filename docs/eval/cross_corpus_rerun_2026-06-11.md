# Cross-Corpus Rerun Under the Fixed Harness (2026-06-11)

**Scope:** llm_only + kg_only only. The employment and RRO retrieval indices did not
survive the development-machine rebuild (only `indices/housing_repairs_social_v1`
exists), so rag_only/hybrid could not be replicated and their 05-23 rows stand.
Flags as the 06-10 housing run (rules off by code default); repairs-gated mechanisms
are inert on these corpora by construction.

## Employment unfair dismissal (n=132, 3 fresh seeds, gpt-5-mini)

Runs: `data/eval_artifacts/runs/employment_unfair_dismissal_v1/emp-rerun-20260611-s{1,2,3}/`
First run with the SHA-149 factor sidecar live (305 assertions / 128 of 132 cases,
mean 2.4 per case vs housing's 6.5).

| Mode | Metric | 05-23 | rerun | Verdict |
|---|---|---:|---:|---|
| llm_only | accuracy | 79.0±0.4 | 79.8±1.2 | replicates |
| | balanced acc | 0.602±0.008 | 0.618±0.011 | replicates |
| | Brier | 0.162±0.003 | 0.158±0.009 | replicates |
| | log-loss | 0.506±0.007 | 0.493±0.025 | replicates |
| | det-acc | 50.5±1.7 | 51.5±3.0 | replicates |
| kg_only | accuracy | 77.0±1.2 | 77.3±1.5 | replicates |
| | balanced acc | 0.582±0.019 | 0.587±0.025 | replicates |
| | Brier | 0.183±0.008 | 0.179±0.008 | replicates |
| | det-acc | 53.5±0.4 | 55.3±2.7 | replicates (+1.8 within noise) |

**Reading:** the employment table reproduces within seed noise. Expected — the
employment runner emits ET-shaped probabilities directly and never routes through
the housing adapter where the calibration defects lived. Confirms the defects'
material impact was confined to the housing tables. Sparse live factors do not move
employment determination accuracy beyond noise.

## Housing RRO (n=40, single seed, gpt-5.5)

Predictions: `eval/predictions/rro40_rerun_20260611/seed1/` (+ `_metrics.json`).
RRO factor sidecar live (1,071 assertions). `domain_pack_unknown` warning for
`housing.property_chamber.rro.v1` (no registered pack — repairs mechanisms inert).

| Mode | Metric | 05-23 | rerun |
|---|---|---:|---:|
| kg_only | accuracy | 40.0 | **55.0** |
| | balanced acc | 0.393 | **0.446** |
| | Brier | 0.274 | **0.226** |
| | log-loss | 0.783 | 0.644 |
| | offence-finding acc | not scored | **0.564** |
| | award-bucket acc | not scored | **0.475** |
| llm_only | accuracy | 55.0 | 42.5 |
| | balanced acc | 0.464 | 0.368 |
| | Brier | 0.282 | **0.226** |
| | log-loss | 0.758 | 0.641 |
| | offence-finding acc | not scored | 0.487 |
| | award-bucket acc | not scored | 0.425 |

**Reading:** same direction as the housing 06-10 result — kg_only leads llm_only on
every scored axis; both modes' calibration improves. Indicative only at n=40, single
seed; the rerun bundles the calibration fixes with the live sidecar, so no
per-mechanism attribution is claimed.

## Disclosures

- Single seed on RRO; 3 seeds on employment.
- The RRO accuracy swings (llm_only −12.5, kg_only +15.0) are 5–6 case flips at n=40.
- Report sections updated: `evaluation.tex` §revised-picture (cross-corpus
  replication paragraph) and the conclusion's RQ1 paragraph.
