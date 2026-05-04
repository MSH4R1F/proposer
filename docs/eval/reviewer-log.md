# Reviewer Adjudication Log

Track every double-annotation disagreement and its resolution. Required by [SHA-96](https://linear.app/sharifbuilders/issue/SHA-96): Cohen's κ ≥ 0.8 per `claim_type` and a per-disagreement audit trail.

## How to use

When two reviewers annotate the same case and produce different values for the same field, add a row below. **Don't** peek at the other reviewer's labels before re-reading the source PDF.

## Schema

| Date | Case ID | Field | Reviewer A | Reviewer B | Resolution | Rationale |
|---|---|---|---|---|---|---|

## Entries

(empty — populate during Phase 6 double-annotation pass)

## Skipped cases

If a case cannot be annotated (corrupted PDF, withdrawn decision, structurally ambiguous), record it here rather than producing a low-quality annotation.

| Date | Case ID | Reason | Resolution |
|---|---|---|---|

(empty)

## Cohen's κ targets

Computed at end of Phase 6 by `scripts/eval/agreement.py` (lands in Phase 6, not yet implemented).

| `claim_type` | n double-annotated | κ | Status (≥0.8 = pass) |
|---|---|---|---|
| `cleaning` | – | – | – |
| `damages` | – | – | – |
| `deposit_non_protection` | – | – | – |
| `disrepair` | – | – | – |
| `end_of_tenancy` | – | – | – |

## Append-gate promotion records

The CLI writes one append line per case. Long batch logs may live alongside the
promotion artifacts rather than bloating this page. The reviewed Housing
Ombudsman stratified-50 promotion log is:

- `data/eval_artifacts/gold_build/housing-ombudsman-stratified-50-review-20260504-reviewed/reviewer-log.md`

- 2026-05-03T20:35:30+00:00 case=LON_00BK_HMB_2021_0011 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:32+00:00 case=BIR_00CQ_HMB_2021_0001 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:33+00:00 case=CAM_00KG_HMF_2022_0018 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:34+00:00 case=CAM_33UG_HMC_2022_0002 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:35+00:00 case=BIR_00FY_HMK_2021_0038 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:36+00:00 case=CHI_24UE_HMC_2022_0001 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:37+00:00 case=LON_00AM_HMF_2021_0161 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:38+00:00 case=LON_00BG_HMF_2022_0149 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:39+00:00 case=LON_00BJ_HMF_2022_0153 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-03T20:35:40+00:00 case=LON_00AC_HMG_2022_0016 run=housing-v1-real-pilot-20260503 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]

- 2026-05-04T00:34:58+00:00 case=birmingham-city-council-202332678 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:34:59+00:00 case=bristol-city-council-202340773 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:00+00:00 case=leeds-city-council-202336074 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:00+00:00 case=north-west-leicestershire-district-council-202506976 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:01+00:00 case=chesterfield-borough-council-202434129 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:02+00:00 case=city-of-westminster-council-202437516 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:03+00:00 case=royal-borough-of-greenwich-202419950 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:04+00:00 case=norwich-city-council-202423175 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:04+00:00 case=harlow-district-council-202343281 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
- 2026-05-04T00:35:05+00:00 case=london-borough-of-lambeth-202419912 run=housing-ombudsman-gold-pilot-20260504 adjudicator=Codex pilot adjudicator fields=[facts, disputed_amount_gbp, claim_types, matter_type, ground_truth_outcome.overall_winner, ground_truth_outcome.total_awarded_gbp, ground_truth_outcome.unapportioned_reason]
