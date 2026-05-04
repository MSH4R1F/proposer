# Housing Ombudsman Stratified 50 Eval Manifest

This manifest selects 50 real Housing Ombudsman determinations from the
1,000-case repairs/social corpus scraped on 2026-05-03/2026-05-04.

Outputs:

- `data/eval/housing_ombudsman_stratified_50.jsonl`
- `data/eval/housing_ombudsman_stratified_50_summary.json`

Build command:

```bash
python scripts/eval/build_housing_ombudsman_stratified_eval.py --data-dir "$DATA_DIR"
```

After the outcome metadata change, rebuild the Ombudsman index before relying
on `outcome_normalized` inside Chroma/BM25 retrieval results:

```bash
python scripts/ingest/run_ombudsman_ingest.py --data-dir "$DATA_DIR"
```

The JSONL is an eval selection manifest, not a fully adjudicated GoldCase file.
Each row is source-grounded to a local `parsed.json` and `raw.txt`, carries
`target_source_id` for leakage exclusion, and is marked
`annotation_status="needs_gold_labeling"`.

Sampling:

- Source population: 1,000 kept Ombudsman repairs/social determinations.
- Eligible population: 936 cases with parsed decision dates.
- Excluded before sampling: 64 cases missing decision dates.
- Sample size: 50.
- Seed: 42.
- Primary stratum: `outcome_normalized`.
- Allocation: minimum one case per non-empty outcome, then largest-remainder
  proportional allocation.
- Within each outcome bucket: round-robin over primary matter type to preserve
  damp/mould versus general disrepair coverage.

Selected outcome distribution:

| Outcome | Cases |
| --- | ---: |
| maladministration | 32 |
| service-failure | 7 |
| reasonable-redress | 4 |
| severe-maladministration | 3 |
| resolved-with-intervention | 2 |
| outside-jurisdiction | 1 |
| unknown | 1 |

Selected primary matter distribution:

| Primary matter type | Cases |
| --- | ---: |
| repairs_disrepair | 26 |
| repairs_damp_mould | 24 |

Next step: promote this manifest into a reviewed gold set by extracting
source spans, compensation/order fields, and human-review decisions through
the SHA-28 gold-building path.

Promotion setup command:

```bash
venv/bin/python scripts/eval/prepare_housing_ombudsman_gold_review.py \
  --manifest data/eval/housing_ombudsman_stratified_50.jsonl \
  --run-id housing-ombudsman-stratified-50-review-20260504 \
  --force
```

This writes source bundles, review packets, draft decision templates, and a
dual-provider labeling command sheet under:

- `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/`
- `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/`

The draft decision templates are intentionally not appendable as gold until a
human reviewer verifies the mandatory fields and records
`human_mandatory_review` provenance.

Reviewed-gold promotion status, 2026-05-04:

- Mohamed confirmed the 50 review packets as reviewed and acceptable.
- `scripts/eval/promote_housing_ombudsman_reviewed_gold.py` converted the draft
  decisions to reviewed decisions, ran the real-gold append gate for every row,
  and replaced `data/gold_standard/housing_repairs_social_v1.jsonl`.
- The previous 10-case pilot file was backed up to
  `data/eval_artifacts/gold_build/housing-ombudsman-stratified-50-review-20260504-reviewed/replaced_housing_repairs_social_v1.jsonl`.
- Promotion summary:
  `data/eval_artifacts/gold_build/housing-ombudsman-stratified-50-review-20260504-reviewed/promotion_summary.json`.

Promotion command:

```bash
PYTHONPATH=packages venv/bin/python scripts/eval/promote_housing_ombudsman_reviewed_gold.py \
  --promote-canonical \
  --force
```

The baseline full eval over the reviewed corpus is documented in
`docs/eval/housing-ombudsman-stratified-50-full-eval.md`.
