# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202413497`
Source slug: `a2dominion-housing-group-limited-202413497`
Target source ID: `202413497`
Title: A2Dominion Housing Group Limited (202413497)
URL: https://www.housing-ombudsman.org.uk/decisions/a2dominion-housing-group-limited-202413497/

## Manifest Strata

- Outcome raw: `maladministration; reasonable redress`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-28`
- Landlord: `A2Dominion Housing Group Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `550.00`
- Draft region: `london` from `A2Dominion Housing Group Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident has reported damp and mould in the property and has complained about the landlord’s approach to resolve it. The resident has also complained that the landlord has not completed the repairs she has reported. The resident lives in the property with her young children. The complaint is about the landlord’s response to reports of damp and mould, and repairs. We have also considered the landlord’s complaint handling.

## Money Candidates

- score=24 amount=550.00 span={'page': 1, 'paragraph': 103, 'text_span': [3768, 3774]} context=use of the condition of the property or during the works . Where the resident is hesitant to be temporarily rehoused, the landlord must demonstrate that it has taken all reasonable steps to support the resident and provide assurances . No later than 16 January 2026 Compensation order The landlord must pay the resident £ 550 to recognise the likely distress and inconvenience caused to the resident by the failures noted in its response to reports of damp and mould, and repairs. This must be paid d
- score=3 amount=350.00 span={'page': 1, 'paragraph': 158, 'text_span': [6559, 6563]} context=below was now empty so it could attend to inspect. It was sorry for its poor communication. The resident had declined a survey and a mould wash. It had raised a job for a further mould wash and to check the bathroom fan. A structural engineer was going to inspect the flat below. It offered the resident compensation of £350. This was made up of: £150 for its poor communication. £100 for the distress and inconvenience caused. £75 for the delay in progressing works. £25 for its delayed stage 2 resp
- score=3 amount=200.00 span={'page': 1, 'paragraph': 258, 'text_span': [12967, 12974]} context=clear what action the landlord intends to take to resolve the mould or reported repairs to ensure the property is safe for the resident. Taking this into account, we find maladministration in the landlord’s response to damp, mould, and repairs . An order has been made to the pay the resident additional compensation of £ 20 0 for the impact of its failings outlined above. This is in line with our remedies guidance for a finding of maladministration where the landlord has acknowledged failings and
- score=3 amount=150.00 span={'page': 1, 'paragraph': 158, 'text_span': [6586, 6591]} context=ould attend to inspect. It was sorry for its poor communication. The resident had declined a survey and a mould wash. It had raised a job for a further mould wash and to check the bathroom fan. A structural engineer was going to inspect the flat below. It offered the resident compensation of £350. This was made up of: £150 for its poor communication. £100 for the distress and inconvenience caused. £75 for the delay in progressing works. £25 for its delayed stage 2 response. Referral to the Ombud
- score=3 amount=100.00 span={'page': 1, 'paragraph': 159, 'text_span': [6619, 6624]} context=rry for its poor communication. The resident had declined a survey and a mould wash. It had raised a job for a further mould wash and to check the bathroom fan. A structural engineer was going to inspect the flat below. It offered the resident compensation of £350. This was made up of: £150 for its poor communication. £100 for the distress and inconvenience caused. £75 for the delay in progressing works. £25 for its delayed stage 2 response. Referral to the Ombudsman The resident told us she rem
- score=3 amount=75.00 span={'page': 1, 'paragraph': 143, 'text_span': [5332, 5336]} context=said: It understood the resident did not want a surveyor to attend or to be temporarily rehoused because she had a negative experience last time this had happened. It was sorry it had not responded to her email, it said it had reminded its staff of the importance of responding to emails in a timely manner. It offered £75 compensation for this. It needed to carry out further investigations in the resident’s property and the property below. 2 July 2024 The resident stated she was unhappy with the
- score=3 amount=75.00 span={'page': 1, 'paragraph': 160, 'text_span': [6667, 6671]} context=declined a survey and a mould wash. It had raised a job for a further mould wash and to check the bathroom fan. A structural engineer was going to inspect the flat below. It offered the resident compensation of £350. This was made up of: £150 for its poor communication. £100 for the distress and inconvenience caused. £75 for the delay in progressing works. £25 for its delayed stage 2 response. Referral to the Ombudsman The resident told us she remained unhappy with the landlord’s response. She r
- score=3 amount=25.00 span={'page': 1, 'paragraph': 161, 'text_span': [6707, 6711]} context=had raised a job for a further mould wash and to check the bathroom fan. A structural engineer was going to inspect the flat below. It offered the resident compensation of £350. This was made up of: £150 for its poor communication. £100 for the distress and inconvenience caused. £75 for the delay in progressing works. £25 for its delayed stage 2 response. Referral to the Ombudsman The resident told us she remained unhappy with the landlord’s response. She requested that the repairs be completed

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202413497.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/a2dominion-housing-group-limited-202413497/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/12-housing-ombudsman-202413497.draft_decision.json`

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
