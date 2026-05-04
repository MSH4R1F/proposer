# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202306436`
Source slug: `bournemouth-christchurch-and-poole-council-202306436`
Target source ID: `202306436`
Title: Bournemouth, Christchurch and Poole Council (202306436)
URL: https://www.housing-ombudsman.org.uk/decisions/bournemouth-christchurch-and-poole-council-202306436/

## Manifest Strata

- Outcome raw: `outside jurisdiction`
- Outcome normalized: `outside-jurisdiction`
- Matter types: `repairs_disrepair`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-22`
- Landlord: `Bournemouth, Christchurch and Poole Council`

## Candidate Gold Fields

- Draft winner: `landlord`
- Draft total awarded: `0.00`
- Draft region: `london` from `Bournemouth, Christchurch and Poole Council (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The landlord told the resident it intended to demolish an extension at the rear of her property as it was unsafe and a fire hazard. It said it would charge her for the removal cost as it had never given permission for the extension to be built. The resident complained about this but the landlord would not change its position. She referred her complaint to us. Following this , the landlord initiated court action seeking an injunction for access to demolish the extension. The complaint is about the landlord’s decision to demolish an extension.

## Money Candidates

- No money candidates found.

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202306436.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/bournemouth-christchurch-and-poole-council-202306436/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/33-housing-ombudsman-202306436.draft_decision.json`

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
