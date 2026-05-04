# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202338295`
Source slug: `rochdale-boroughwide-housing-limited-202338295`
Target source ID: `202338295`
Title: Rochdale Boroughwide Housing Limited (202338295)
URL: https://www.housing-ombudsman.org.uk/decisions/rochdale-boroughwide-housing-limited-202338295/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-12-19`
- Landlord: `Rochdale Boroughwide Housing Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `380.00`
- Draft region: `london` from `Rochdale Boroughwide Housing Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in the property with her partner and 2 children. She complains the landlord failed to adequately inspect or clean the property after its contractor accidentally put their foot through the ceiling while completing works in the loft. The complaint is about how the landlord responded to: Its contractor causing a partial collapse of the ceiling while completing works in the loft. The resident’s reports of chipped flooring. We have also considered the landlord’s complaint handling.

## Money Candidates

- score=16 amount=380.00 span={'page': 1, 'paragraph': 90, 'text_span': [3414, 3419]} context=y 2026 Compensation order The landlord must pay the resident £ 200 comprised of: £ 200 for distress caused by its failure to complete an asbestos survey or suitably reassure the resident that it had removed all potential hazards following the accident on 7 December 2023. If the landlord has yet to pay the resident the £380 offered at stage 2, it is to do so and evidence this. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by
- score=16 amount=200.00 span={'page': 1, 'paragraph': 82, 'text_span': [3155, 3161]} context=riting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 13 January 2026 Compensation order The landlord must pay the resident £ 200 comprised of: £ 200 for distress caused by its failure to complete an asbestos survey or suitably reassure the resident that it had removed all potential hazards following th
- score=16 amount=200.00 span={'page': 1, 'paragraph': 84, 'text_span': [3175, 3181]} context=nt for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 13 January 2026 Compensation order The landlord must pay the resident £ 200 comprised of: £ 200 for distress caused by its failure to complete an asbestos survey or suitably reassure the resident that it had removed all potential hazards following the accident on 7 Dece
- score=3 amount=600.00 span={'page': 1, 'paragraph': 195, 'text_span': [13472, 13477]} context=dlord has not acknowledged its failure to complete an asbestos inspection nor has it done enough to reassure the resident that there were no hazards present in the home, for these reasons, we do not consider the compensation offered to be sufficient. Our guidance on compensation sets out that payments between £100 and £600 are typically appropriate to put right failings which have adversely, but not permanently, impacted residents. In calculating the correct sum of compensation we have considere
- score=3 amount=200.00 span={'page': 1, 'paragraph': 196, 'text_span': [13900, 13905]} context=idents. In calculating the correct sum of compensation we have considered the distress the resident was likely caused by the landlord’s omissions. We have considered how this distress was likely compounded by the resident’s responsibilities as a mother to her 2 young children. We will order the landlord pays a further £200 to bring the total compensation up to the higher end of our scale. The resident has advised us that she considers the landlord should reimburse her the cost of the 2 new child
- score=3 amount=180.00 span={'page': 1, 'paragraph': 195, 'text_span': [13085, 13090]} context=ccident. However, despite the resident then asking the landlord to commission a new survey after its stage 1 response on 11 December 2023, the landlord failed to organise this or address the request. We note the landlord has already offered the resident £150 for distress and inconvenience. We also note that it offered £180 as a contribution towards any cleaning costs. However, the landlord has not acknowledged its failure to complete an asbestos inspection nor has it done enough to reassure the
- score=3 amount=150.00 span={'page': 1, 'paragraph': 150, 'text_span': [7118, 7123]} context=2023, so it would not offer compensation for this. There was no asbestos containing materials (ACMS) in the loft which was confirmed by a 2015 survey. The resident was welcome to request a more up-to-date report. The insulation used is “stone wool” and “poses no risk to human health.” The landlord offered the resident £150 to have clothes and bedding professionally cleaned. It also offered to clean the 2 beds affected, but would not offer this service for any items which were not in the bedroom.
- score=3 amount=150.00 span={'page': 1, 'paragraph': 167, 'text_span': [8634, 8639]} context=ppy with the standard of cleaning, and offered her a further £30 in compensation to pay for additional cleaning. Explained that it had asked the resident for evidence to show she had replaced her children’s 2 mattresses, which she had not provided. Therefore, it could not reimburse her for these. Offered her a further £150 in compensation for distress and inconvenience, and £50 for a delayed stage 2 response. What we found and why The circumstances of th is complaint are well known by the partie

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202338295.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/rochdale-boroughwide-housing-limited-202338295/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/15-housing-ombudsman-202338295.draft_decision.json`

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
