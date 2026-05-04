# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202511615`
Source slug: `sovereign-network-group-202511615`
Target source ID: `202511615`
Title: Sovereign Network Group (202511615)
URL: https://www.housing-ombudsman.org.uk/decisions/sovereign-network-group-202511615/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-13`
- Landlord: `Sovereign Network Group`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `0.00`
- Draft region: `london` from `Sovereign Network Group (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a 1-bedroom ground floor flat with his wife. He feels the property is not suitable for his medical needs and that the landlord has not dealt with the damp and mould effectively. He has mobility issues. Both occupants have asthma. The landlord is aware of their vulnerabilities. This complaint is about the landlord’s handling of: Damp and mould in the property. Adaptation requests. A rehousing request. The complaint.

## Money Candidates

- No money candidates found.

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202511615.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/sovereign-network-group-202511615/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/06-housing-ombudsman-202511615.draft_decision.json`

## Reviewer Instructions

1. Run dual-provider auto-labeling for this case or for the whole run using
   `commands.sh`.
2. Open this packet and the raw text side by side.
3. Verify the mandatory fields: `facts`, `disputed_amount_gbp`, `claim_types`,
   `matter_type`, `overall_winner`, `total_awarded_gbp`, and
   `unapportioned_reason`.
4. Edit the draft decision template with the reviewed values and convert
   confirmed mandatory `field_provenance[].source` values from
   `deterministic_manifest` to `human_mandatory_review`.
5. Append only after review with `scripts/eval/adjudicate.py append`.
