# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202511313`
Source slug: `london-quadrant-housing-trust-202511313`
Target source ID: `202511313`
Title: London & Quadrant Housing Trust   (202511313)
URL: https://www.housing-ombudsman.org.uk/decisions/london-quadrant-housing-trust-202511313/

## Manifest Strata

- Outcome raw: `service failure`
- Outcome normalized: `service-failure`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-12-10`
- Landlord: `London & Quadrant Housing Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `350.00`
- Draft region: `london` from `London & Quadrant Housing Trust (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives with her child in the ground floor flat of a converted 1-story house. The landlord has vulnerabilities recorded for the resident. In her formal complaint, the resident said there was an ongoing mouse infestation within her flat which the landlord had persistently failed to resolve. The resident said she wanted the landlord to address this issue. She later asked to be re-housed by the landlord after repeated attempts to resolve the issue were unsuccessful. The complaint is about the landlord’s handling of: The resident’s reports of an ongoing mice infestation. The related complaint.

## Money Candidates

- score=18 amount=350.00 span={'page': 1, 'paragraph': 81, 'text_span': [2462, 2468]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 1 5 January 2026 2 Compensation order The landlord must pay the resident £ 350 (including the £190 offered during the complaints process) made up as follows: £ 250 for the distress, inconvenience, time, and trouble caused by the landlord’s handling of r
- score=18 amount=250.00 span={'page': 1, 'paragraph': 83, 'text_span': [2547, 2553]} context=ure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 1 5 January 2026 2 Compensation order The landlord must pay the resident £ 350 (including the £190 offered during the complaints process) made up as follows: £ 250 for the distress, inconvenience, time, and trouble caused by the landlord’s handling of reports of an ongoing mice infestation £ 100 for the distress, inconvenience, time, an
- score=18 amount=190.00 span={'page': 1, 'paragraph': 82, 'text_span': [2483, 2488]} context=or the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 1 5 January 2026 2 Compensation order The landlord must pay the resident £ 350 (including the £190 offered during the complaints process) made up as follows: £ 250 for the distress, inconvenience, time, and trouble caused by the landlord’s handling of reports of an ongoing
- score=14 amount=100.00 span={'page': 1, 'paragraph': 87, 'text_span': [2680, 2686]} context=ies guidance . No later than 1 5 January 2026 2 Compensation order The landlord must pay the resident £ 350 (including the £190 offered during the complaints process) made up as follows: £ 250 for the distress, inconvenience, time, and trouble caused by the landlord’s handling of reports of an ongoing mice infestation £ 100 for the distress, inconvenience, time, and trouble caused by the landlord’s complaint handling failings This must be paid directly to the resident by the due date. The landlo
- score=5 amount=300.00 span={'page': 1, 'paragraph': 246, 'text_span': [14857, 14862]} context=n from outcomes. However, given the lengthy delay (of at least 7 months) in completing all necessary structural repairs, the redress offered is not sufficient to resolve the complaint. This amounts to an overall finding of service failure. In the circumstances, the landlord shall pay the resident total compensation of £300 (including the £150 offered during the complaints process) made up of: £200 for distress and inconvenience. £100 for time and trouble. This amount is in line with the level re
- score=5 amount=200.00 span={'page': 1, 'paragraph': 246, 'text_span': [14933, 14938]} context=completing all necessary structural repairs, the redress offered is not sufficient to resolve the complaint. This amounts to an overall finding of service failure. In the circumstances, the landlord shall pay the resident total compensation of £300 (including the £150 offered during the complaints process) made up of: £200 for distress and inconvenience. £100 for time and trouble. This amount is in line with the level recommended in our remedies guidance where failings have adversely affected th
- score=5 amount=150.00 span={'page': 1, 'paragraph': 246, 'text_span': [14877, 14882]} context=ever, given the lengthy delay (of at least 7 months) in completing all necessary structural repairs, the redress offered is not sufficient to resolve the complaint. This amounts to an overall finding of service failure. In the circumstances, the landlord shall pay the resident total compensation of £300 (including the £150 offered during the complaints process) made up of: £200 for distress and inconvenience. £100 for time and trouble. This amount is in line with the level recommended in our rem
- score=5 amount=100.00 span={'page': 1, 'paragraph': 247, 'text_span': [14970, 14975]} context=epairs, the redress offered is not sufficient to resolve the complaint. This amounts to an overall finding of service failure. In the circumstances, the landlord shall pay the resident total compensation of £300 (including the £150 offered during the complaints process) made up of: £200 for distress and inconvenience. £100 for time and trouble. This amount is in line with the level recommended in our remedies guidance where failings have adversely affected the resident. This amount also takes in

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202511313.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-quadrant-housing-trust-202511313/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/45-housing-ombudsman-202511313.draft_decision.json`

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
