# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202427949`
Source slug: `sanctuary-housing-association-202427949`
Target source ID: `202427949`
Title: Sanctuary Housing Association (202427949)
URL: https://www.housing-ombudsman.org.uk/decisions/sanctuary-housing-association-202427949/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration; reasonable redress`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-10-29`
- Landlord: `Sanctuary Housing Association`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `400.00`
- Draft region: `london` from `Sanctuary Housing Association (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a 2-bedroom ground floor maisonette. They live with their adult children and several members of the household have long – term physical health conditions. The complaint is about the landlord’s response to the resident’s reports of : D amp and mould. F ault s with the boiler. We have also looked at the landlord’s complaint handling.

## Money Candidates

- score=14 amount=400.00 span={'page': 1, 'paragraph': 124, 'text_span': [2561, 2566]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 26 November 2025 2 Compensation order The landlord must pay the resident £400 for failures in its handling of the ir reports of damp and mould. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of
- score=2 amount=400.00 span={'page': 1, 'paragraph': 272, 'text_span': [9078, 9083]} context=The landlord’s complaint policy has a payment banding where there is high impact on a resident and the responsibility is solely the landlord’s. This banding and the maladministration range of our own remedies guidance have been considered when deciding on an appropriate amount of redress for the resident. A payment of £400 sits within both ranges. Taking the full circumstances into account, the landlord should make a payment of £400 to the resident to reflect the distress and inconvenience cause
- score=2 amount=400.00 span={'page': 1, 'paragraph': 275, 'text_span': [9190, 9195]} context=ility is solely the landlord’s. This banding and the maladministration range of our own remedies guidance have been considered when deciding on an appropriate amount of redress for the resident. A payment of £400 sits within both ranges. Taking the full circumstances into account, the landlord should make a payment of £400 to the resident to reflect the distress and inconvenience caused to the resident by the failings identified above. Complaint Reports of faults with the boiler Finding Reasonab
- score=1 amount=94.00 span={'page': 1, 'paragraph': 168, 'text_span': [4439, 4443]} context=airs had not been completed and they want ed compensation for the issues . 7 May 2024 The landlord issued its stage 2 response. It gave an update on the repairs that had been completed to date and identified that it should have offered compensation at stage 1 for delays to the boiler replacement. It offered a total of £94 compensation for these delays. It said that some damp and mould work was ongoing. Referral to the Ombudsman The resident asked us to investigate as they were unhappy with the d
- score=1 amount=50.00 span={'page': 1, 'paragraph': 328, 'text_span': [10681, 10685]} context=attempts were made to arrange installation of the boiler until the resident chased this. The boiler was installed on 6 March 2024. In its stage 2 response , the landlord offered compensation for the delays to these repairs and for the resident being left without a working boiler. This came to £44 , with an additional £50 as a gesture of goodwill. The £44 was worked out by following the right to repair compensation guidance in the landlord’s compensation policy. The landlord apologised for the de
- score=1 amount=44.00 span={'page': 1, 'paragraph': 326, 'text_span': [10656, 10662]} context=There is no evidence that attempts were made to arrange installation of the boiler until the resident chased this. The boiler was installed on 6 March 2024. In its stage 2 response , the landlord offered compensation for the delays to these repairs and for the resident being left without a working boiler. This came to £44 , with an additional £50 as a gesture of goodwill. The £44 was worked out by following the right to repair compensation guidance in the landlord’s compensation policy. The land
- score=1 amount=44.00 span={'page': 1, 'paragraph': 328, 'text_span': [10715, 10719]} context=tallation of the boiler until the resident chased this. The boiler was installed on 6 March 2024. In its stage 2 response , the landlord offered compensation for the delays to these repairs and for the resident being left without a working boiler. This came to £44 , with an additional £50 as a gesture of goodwill. The £44 was worked out by following the right to repair compensation guidance in the landlord’s compensation policy. The landlord apologised for the delays and provided compensation in
- score=-4 amount=94.00 span={'page': 1, 'paragraph': 137, 'text_span': [3039, 3043]} context=ocumentary evidence of payment by the due date. The landlord may deduct from the total figure any payments it has already made . No later than 26 November 2025 Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations The landlord should pay the resident the £94 it offered for its delays in repairing the boiler, if it has not already done so. Our finding of reasonable redress is made on the basis that this is paid. Our investigation Th

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202427949.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/sanctuary-housing-association-202427949/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/02-housing-ombudsman-202427949.draft_decision.json`

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
