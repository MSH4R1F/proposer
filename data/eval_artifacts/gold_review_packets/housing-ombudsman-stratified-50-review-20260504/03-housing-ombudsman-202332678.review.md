# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202332678`
Source slug: `birmingham-city-council-202332678`
Target source ID: `202332678`
Title: Birmingham City Council (202332678)
URL: https://www.housing-ombudsman.org.uk/decisions/birmingham-city-council-202332678/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-10-30`
- Landlord: `Birmingham City Council`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1000.00`
- Draft region: `west_midlands` from `Birmingham City Council (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in the property, a 2-bedroom house, with her husband and young children. The landlord is aware she has respiratory health conditions. She reported flooring repairs and damp and mould affecting her living room in July 2023. This complaint is about the landlord’s handling of: Flooring repairs. Reports of damp and mould. The complaint.

## Money Candidates

- score=20 amount=1000.00 span={'page': 1, 'paragraph': 80, 'text_span': [2536, 2543]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 28 November 2025 2 Compensation order The landlord must pay the resident £ 1000 made up as follows: £500 for the distress and inconvenience caused by its handling of flooring repairs. £300 for the distress and inconvenience caused by its handling of rep
- score=20 amount=500.00 span={'page': 1, 'paragraph': 82, 'text_span': [2563, 2568]} context=failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 28 November 2025 2 Compensation order The landlord must pay the resident £ 1000 made up as follows: £500 for the distress and inconvenience caused by its handling of flooring repairs. £300 for the distress and inconvenience caused by its handling of reports of damp and mould. £200
- score=20 amount=300.00 span={'page': 1, 'paragraph': 83, 'text_span': [2647, 2652]} context=ic to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 28 November 2025 2 Compensation order The landlord must pay the resident £ 1000 made up as follows: £500 for the distress and inconvenience caused by its handling of flooring repairs. £300 for the distress and inconvenience caused by its handling of reports of damp and mould. £200 for time, trouble, distress and inconvenience caused by its complaint handling fai
- score=20 amount=200.00 span={'page': 1, 'paragraph': 84, 'text_span': [2740, 2745]} context=to our apologies guidance . No later than 28 November 2025 2 Compensation order The landlord must pay the resident £ 1000 made up as follows: £500 for the distress and inconvenience caused by its handling of flooring repairs. £300 for the distress and inconvenience caused by its handling of reports of damp and mould. £200 for time, trouble, distress and inconvenience caused by its complaint handling failures . T his must be paid directly to the resident by the due date. The landlord must provide
- score=3 amount=600.00 span={'page': 1, 'paragraph': 264, 'text_span': [11363, 11368]} context=er. Although it recognised this was the case in its stage 2 response and apologised, it failed to offer any redress in line with its compensation policy in recognition of the distress and inconvenience that its failings had caused to the resident. Our remedies guidance provides for compensation in the range of £100 to £600 for situations like this where there was failure by a landlord that adversely affected the resident causing distress and inconvenience. The landlord’s failure to offer any fin
- score=3 amount=100.00 span={'page': 1, 'paragraph': 264, 'text_span': [11355, 11360]} context=the matter. Although it recognised this was the case in its stage 2 response and apologised, it failed to offer any redress in line with its compensation policy in recognition of the distress and inconvenience that its failings had caused to the resident. Our remedies guidance provides for compensation in the range of £100 to £600 for situations like this where there was failure by a landlord that adversely affected the resident causing distress and inconvenience. The landlord’s failure to offer

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202332678.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/birmingham-city-council-202332678/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/03-housing-ombudsman-202332678.draft_decision.json`

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
