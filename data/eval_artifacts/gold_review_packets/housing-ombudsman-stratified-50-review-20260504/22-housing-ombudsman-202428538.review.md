# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202428538`
Source slug: `clarion-housing-association-limited-202428538`
Target source ID: `202428538`
Title: Clarion Housing Association Limited (202428538)
URL: https://www.housing-ombudsman.org.uk/decisions/clarion-housing-association-limited-202428538/

## Manifest Strata

- Outcome raw: `maladministration; service failure; reasonable redress`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-07`
- Landlord: `Clarion Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `3818.00`
- Draft region: `london` from `Clarion Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident ’s tenancy of the property, a one-bedroom house, began in August 2022. S he was 19 years old and had been homeless and living in hostels since the age of 16. This was her first tenancy and the first time she would be living alone. In July 2024 she complained to the landlord that it had not completed various repairs, most of which she reported around the time her tenancy began. She said this included a fence which she had since replaced at her own expense. She was unhappy with the landlord’s response to her complaint and asked us to investigate. The complaint is about the landlord’s: Handling of repairs. Response to the resident’s request for reimbursement of fencing costs....

## Money Candidates

- score=20 amount=3818.00 span={'page': 1, 'paragraph': 107, 'text_span': [2964, 2975]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 December 2025 2 Compensation order The landlord must pay the resident £ 3 , 8 18 made up as follows: £ 600 for the distress and inconvenience caused by the maladministration in its handling of repairs. £ 1 00 for the distress and inconvenience caused
- score=20 amount=600.00 span={'page': 1, 'paragraph': 112, 'text_span': [2995, 3001]} context=lures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 December 2025 2 Compensation order The landlord must pay the resident £ 3 , 8 18 made up as follows: £ 600 for the distress and inconvenience caused by the maladministration in its handling of repairs. £ 1 00 for the distress and inconvenience caused by the service failure in its
- score=16 amount=1118.00 span={'page': 1, 'paragraph': 126, 'text_span': [3214, 3221]} context=December 2025 2 Compensation order The landlord must pay the resident £ 3 , 8 18 made up as follows: £ 600 for the distress and inconvenience caused by the maladministration in its handling of repairs. £ 1 00 for the distress and inconvenience caused by the service failure in its response to her reimbursement request. £1,118 as reimbursement for her costs in replacing the fence. £2,000 compensation offered in its complaint responses. The landlord may deduct the £2,000 if it has already paid this
- score=16 amount=100.00 span={'page': 1, 'paragraph': 117, 'text_span': [3096, 3103]} context=entified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 December 2025 2 Compensation order The landlord must pay the resident £ 3 , 8 18 made up as follows: £ 600 for the distress and inconvenience caused by the maladministration in its handling of repairs. £ 1 00 for the distress and inconvenience caused by the service failure in its response to her reimbursement request. £1,118 as reimbursement for her costs in replacing the fence.
- score=5 amount=500.00 span={'page': 1, 'paragraph': 532, 'text_span': [23463, 23469]} context=knowing whether or not the further damage would still have occurred. The reason we do not know this is due to the landlord’s failure to consider its own actions during the enforcement process. Therefore, in our view, it is fair that it should fully compensate the resident for the fencing costs. As it has already paid £500, we have ordered it to pay her the £1,118 remaining balance. We have also ordered it to pay her £100 compensation for the distress and inconvenience caused by this service fail
- score=3 amount=1850.00 span={'page': 1, 'paragraph': 214, 'text_span': [6713, 6722]} context=s required by its repairs policy. Acknowledged it said at the start of the tenancy it would repair 3 fence panels and posts but failed to complete this work. It would compensate the resident for this, but not the full replacement cost. Acknowledged it had delayed in issuing its complaint response. Offered the resident £1, 8 50 compensation for the delays in repairs (£1, 3 50) , its failure to repair the fence (£500) , and the late complaint response (£100) . This was to reflect inconvenience cau
- score=3 amount=1350.00 span={'page': 1, 'paragraph': 220, 'text_span': [6762, 6770]} context=said at the start of the tenancy it would repair 3 fence panels and posts but failed to complete this work. It would compensate the resident for this, but not the full replacement cost. Acknowledged it had delayed in issuing its complaint response. Offered the resident £1, 8 50 compensation for the delays in repairs (£1, 3 50) , its failure to repair the fence (£500) , and the late complaint response (£100) . This was to reflect inconvenience caused, the time she spent chasing it for updates, an
- score=3 amount=1350.00 span={'page': 1, 'paragraph': 303, 'text_span': [11314, 11323]} context=t raised in her complaint and appropriately identified which repairs it was responsible for. It a pologised for its delays in attending to guttering, the bedroom door, drainage and window repairs. It appropriately identified its handling of these issues was not in line with its repairs policy. It o ffered the resident £1, 3 50 compensation for these delays and £500 for its failure to repair the fence. It provided a breakdown of how it had calculated the compensation for each delayed repair , wit

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202428538.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/clarion-housing-association-limited-202428538/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/22-housing-ombudsman-202428538.draft_decision.json`

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
