# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202412991`
Source slug: `birmingham-city-council-202412991`
Target source ID: `202412991`
Title: Birmingham City Council (202412991)
URL: https://www.housing-ombudsman.org.uk/decisions/birmingham-city-council-202412991/

## Manifest Strata

- Outcome raw: `service failure`
- Outcome normalized: `service-failure`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-24`
- Landlord: `Birmingham City Council`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `150.00`
- Draft region: `west_midlands` from `Birmingham City Council (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives in a 1-bedroom property within a block of flats. She lives there alone. The complaint is about the landlord’s handling of the resident’s : Reports of anti-social behaviour (ASB) including noise nuisance. Complaint.

## Money Candidates

- score=18 amount=150.00 span={'page': 1, 'paragraph': 95, 'text_span': [2218, 2223]} context=es identified in this report. The landlord must ensure: a manager provides t he apology t he apology is specific to the failures identified in this decision , meaningful and empathetic. i t has due regard to our apologies guidance . No later than 21 November 2025 2 Compensation order The landlord must pay the resident £150 made up as follows: £100 for the failures identified in its handling of the resident’s report s of ASB and noise nuisance £50 for the failures identified in its complaint hand
- score=18 amount=100.00 span={'page': 1, 'paragraph': 95, 'text_span': [2243, 2248]} context=ort. The landlord must ensure: a manager provides t he apology t he apology is specific to the failures identified in this decision , meaningful and empathetic. i t has due regard to our apologies guidance . No later than 21 November 2025 2 Compensation order The landlord must pay the resident £150 made up as follows: £100 for the failures identified in its handling of the resident’s report s of ASB and noise nuisance £50 for the failures identified in its complaint handling. This must be paid d
- score=18 amount=50.00 span={'page': 1, 'paragraph': 98, 'text_span': [2345, 2349]} context=s identified in this decision , meaningful and empathetic. i t has due regard to our apologies guidance . No later than 21 November 2025 2 Compensation order The landlord must pay the resident £150 made up as follows: £100 for the failures identified in its handling of the resident’s report s of ASB and noise nuisance £50 for the failures identified in its complaint handling. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by
- score=1 amount=50.00 span={'page': 1, 'paragraph': 516, 'text_span': [14162, 14166]} context=te her complaint again on 3 June 2024. The landlord acknowledged her escalation and responded at stage 2 in line with its complaints policy timescale . Due to the landlord initially preventing the resident escalating her complaint, we found service failure in its complaint handling. We have ordered the landlord to pay £50 compensation which is in keeping with our remedies guidance for service failures that may have caused time and trouble to the resident over a short duration. Learning Knowledge
- score=0 amount=100.00 span={'page': 1, 'paragraph': 456, 'text_span': [12569, 12574]} context=the resident further time and trouble calling to request callbacks again on 3 May and 8 May 2024. This is evidence of poor communication. In view of its poor communication , we find service failure in the landlord’s handling of the resident’s report of ASB including noise nuisance . We have ordered the landlord to pay £ 100. This recognises the distress, time, and trouble its poor communication may have caused the resident. T he resident said as a resolution to the case, she would like to move t

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202412991.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/birmingham-city-council-202412991/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/43-housing-ombudsman-202412991.draft_decision.json`

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
