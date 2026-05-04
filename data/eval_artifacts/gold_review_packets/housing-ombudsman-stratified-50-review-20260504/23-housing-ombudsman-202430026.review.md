# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202430026`
Source slug: `islington-and-shoreditch-housing-association-limited-202430026`
Target source ID: `202430026`
Title: Islington and Shoreditch Housing Association Limited (202430026)
URL: https://www.housing-ombudsman.org.uk/decisions/islington-and-shoreditch-housing-association-limited-202430026/

## Manifest Strata

- Outcome raw: `maladministration; outside jurisdiction`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-13`
- Landlord: `Islington and Shoreditch Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `441.81`
- Draft region: `london` from `Islington and Shoreditch Housing Association Limited (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident is a secure tenant of the landlord. The property is a 3-bedroom flat. The complaint is about the landlord’s: response to the resident’s repair requests. response to reports of a data breach. complaint handling.

## Money Candidates

- score=20 amount=441.81 span={'page': 1, 'paragraph': 74, 'text_span': [2311, 2319]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 12 December 2025 2 Compensation order The landlord must pay the resident £ 441.81 made up as follows: £ 300 for distress and inconvenience caused by its response to the resident’s repair requests. £ 1 00 for time, trouble, and inconvenience for the fail
- score=20 amount=300.00 span={'page': 1, 'paragraph': 76, 'text_span': [2340, 2346]} context=ailures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 12 December 2025 2 Compensation order The landlord must pay the resident £ 441.81 made up as follows: £ 300 for distress and inconvenience caused by its response to the resident’s repair requests. £ 1 00 for time, trouble, and inconvenience for the failings identified in its compla
- score=20 amount=100.00 span={'page': 1, 'paragraph': 80, 'text_span': [2435, 2442]} context=lures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 12 December 2025 2 Compensation order The landlord must pay the resident £ 441.81 made up as follows: £ 300 for distress and inconvenience caused by its response to the resident’s repair requests. £ 1 00 for time, trouble, and inconvenience for the failings identified in its complaints handling. £ 41.81 for loss of use of 2 bedroom s for 1 week. The landlord must revisit its
- score=20 amount=41.81 span={'page': 1, 'paragraph': 83, 'text_span': [2535, 2542]} context=idance . No later than 12 December 2025 2 Compensation order The landlord must pay the resident £ 441.81 made up as follows: £ 300 for distress and inconvenience caused by its response to the resident’s repair requests. £ 1 00 for time, trouble, and inconvenience for the failings identified in its complaints handling. £ 41.81 for loss of use of 2 bedroom s for 1 week. The landlord must revisit its offer for flooring replacement to ensure that the offer for actual damaged flooring including fitti
- score=3 amount=500.00 span={'page': 1, 'paragraph': 189, 'text_span': [9074, 9079]} context=er, there was a dispute if the amount offered was sufficient. The resident obtained a quote to supply flooring but said that further flooring was subsequently damaged and, as such, the original quote was not sufficient. The landlord failed to investigate the residents position and maintained that the resident accepted £500 as a resolution to her flooring complaint. This was unreasonable. The landlord should have checked its repair records to confirm the amount of flooring damaged and adjusted it
- score=1 amount=500.00 span={'page': 1, 'paragraph': 129, 'text_span': [4403, 4409]} context=floor repairs. 6 September 2024 The landlord provided its stage 1 complaint response. It upheld the complaint. It said that repairs had been completed and acknowledged the delay in completing the repairs. It apologised for the delay in responding to the complaint and it said that the resident had accepted an offer of £ 500 for damage caused to h er flooring. 9 September 2024 The resident disputed that all of the repairs had been completed. Sh e said that compensation for the damaged flooring was
- score=0 amount=104.54 span={'page': 1, 'paragraph': 193, 'text_span': [10771, 10778]} context=is 20% of the weekly rent for loss of bedrooms. The landlord’s records are not clear, but given the extent of the leak, it is reasonable to conclude that the resident was without use of the 2 bedrooms while the leak was repaired and the floors dried out for over a week. The evidence shows that the resident was paying £104.54 weekly rent. An order for the landlord to pay £41.81 representing 40% of the rent for 1 weeks has been made on this basis. Leaking toilet cistern In her initial complaint th
- score=-2 amount=500.00 span={'page': 1, 'paragraph': 142, 'text_span': [4892, 4897]} context=flooring was not sufficient and asked for the complaint to be escalated to stage 2 14 October 2024 The landlord provided its stage 2 complaint response. It upheld the complaint. It found that its stage 1 complaint response did not meet its standards and that information was not correct. The landlord said it had agreed £500 with the resident for the replacement flooring and it had now processed that payment. It provided an update on each repair issue the resident complained about. It apologised f

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202430026.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/islington-and-shoreditch-housing-association-limited-202430026/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/23-housing-ombudsman-202430026.draft_decision.json`

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
