# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202345261`
Source slug: `babergh-district-council-202345261`
Target source ID: `202345261`
Title: Babergh District Council (202345261)
URL: https://www.housing-ombudsman.org.uk/decisions/babergh-district-council-202345261/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-26`
- Landlord: `Babergh District Council`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `400.00`
- Draft region: `london` from `Babergh District Council (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident had a long-standing issue with infestation s of rats in the property that had been ongoing for over 4 years. The landlord’s handling of rep orts of a pest infestation. We have also considered the landlord’s complaint handling.

## Money Candidates

- score=16 amount=400.00 span={'page': 1, 'paragraph': 86, 'text_span': [2049, 2056]} context=ting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 January 2026 2 Compensation order The landlord must pay the resident £ 4 00 made up of: £300 for the distress and inconvenience caused by its handling of the pest infestation. £100 for the inconvenience caused by its handling of the complaint. The l
- score=16 amount=300.00 span={'page': 1, 'paragraph': 89, 'text_span': [2068, 2073]} context=t for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 January 2026 2 Compensation order The landlord must pay the resident £ 4 00 made up of: £300 for the distress and inconvenience caused by its handling of the pest infestation. £100 for the inconvenience caused by its handling of the complaint. The landlord may deduct
- score=16 amount=100.00 span={'page': 1, 'paragraph': 93, 'text_span': [2156, 2161]} context=pecific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 January 2026 2 Compensation order The landlord must pay the resident £ 4 00 made up of: £300 for the distress and inconvenience caused by its handling of the pest infestation. £100 for the inconvenience caused by its handling of the complaint. The landlord may deduct any payments it has already made from this total figure. This must be paid directly to t
- score=12 amount=100.00 span={'page': 1, 'paragraph': 340, 'text_span': [13324, 13331]} context=n the Code. The delay prolonged the complaints process and prevented the resident from referring the matter to th is Service sooner . It did not acknowledge this delay or offer any redress. As such, there was service failure in the landlord’s handling of the complaint. W e order that the landlord must pay the resident £1 0 0 compensation. This is in line with our remedies guidance for circumstances where service failure by a landlord had an adverse impact on the resident, and it did not appropri
- score=5 amount=300.00 span={'page': 1, 'paragraph': 310, 'text_span': [11580, 11585]} context=rnative arrangements or providing updates, and took more than a year to complete related proofing works . These failures likely caused distress and inconvenience to the resident. For these reasons, we have found maladministration. In light of the inconvenience and distress caused to the resident during 2024 , we award £300 compensation for the failures noted in this report. This is in line with our remedies guidance when the landlord has not acknowledged its failings and there was an adverse imp

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202345261.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/babergh-district-council-202345261/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/26-housing-ombudsman-202345261.draft_decision.json`

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
