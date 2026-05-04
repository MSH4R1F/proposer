# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202442504`
Source slug: `london-borough-of-camden-council-202442504`
Target source ID: `202442504`
Title: London Borough of Camden Council (202442504)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-camden-council-202442504/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-12-19`
- Landlord: `London Borough of Camden Council`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `175.00`
- Draft region: `london` from `London Borough of Camden Council (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The property is a 2 bedroom maisonette. The resident lives with her husband . She has been assisted through the complaints process by a third party support worker , who has represented her with this service. For the purposes of the report, we will refer to both the resident and the representative as ‘the resident’. The complaint is about the landlord ’ s: Handling of reports of no heat ing and hot water Complaint handling.

## Money Candidates

- score=18 amount=175.00 span={'page': 1, 'paragraph': 112, 'text_span': [2594, 2600]} context=ting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 16 January 2026 2 Compensation order The landlord must pay the resident £ 175 made up as follows: £ 75 for its service failure in its handling of the resident’s reports of no heat ing or hot water £ 100 for its maladministration in its handling of the
- score=18 amount=100.00 span={'page': 1, 'paragraph': 121, 'text_span': [2719, 2725]} context=lures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 16 January 2026 2 Compensation order The landlord must pay the resident £ 175 made up as follows: £ 75 for its service failure in its handling of the resident’s reports of no heat ing or hot water £ 100 for its maladministration in its handling of the resident’s complaint. This must be paid directly to the resident by the due date. The landlord must provide documentary evide
- score=18 amount=75.00 span={'page': 1, 'paragraph': 114, 'text_span': [2620, 2625]} context=he failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 16 January 2026 2 Compensation order The landlord must pay the resident £ 175 made up as follows: £ 75 for its service failure in its handling of the resident’s reports of no heat ing or hot water £ 100 for its maladministration in its handling of the resident’s complaint. This
- score=12 amount=100.00 span={'page': 1, 'paragraph': 394, 'text_span': [15968, 15974]} context=caused the resident distress, frustration, and inconvenience. The confusion around the resident’s complaint and the delays in providing responses caused the complaints process to be drawn out and caused the resident time and trouble. In recognition of these failures, the landlord must pay the resident compensation of £ 100 . This amount is in line with our remedies guidance for maladministration. Learning The landlord’s complaints policy sets out 3 stages. Referral to the Ombudsman is set out as
- score=6 amount=75.00 span={'page': 1, 'paragraph': 322, 'text_span': [12262, 12265]} context=laining why it was relevant. We consider these failures to be service failure . The landlord has previously offered the resident a heating rebate for the periods that her heating was not working. In recognition of the service failures identified in this investigation, the landlord must pay the resident compensation of £75. This amount is in line with our remedies guidance for service failure. Complaint The handling of the complaint Finding Maladministration The landlord’s complaints policy says

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202442504.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-camden-council-202442504/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/31-housing-ombudsman-202442504.draft_decision.json`

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
