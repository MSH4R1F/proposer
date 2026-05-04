# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202331162`
Source slug: `southern-housing-202331162`
Target source ID: `202331162`
Title: Southern Housing  (202331162)
URL: https://www.housing-ombudsman.org.uk/decisions/southern-housing-202331162/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-25`
- Landlord: `Southern Housing`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `540.00`
- Draft region: `london` from `Southern Housing (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident reported in January 2023 that her kitchen window was cracked. She complained to the landlord on 9 August 2023 because it had not repaired the window during that time. The complaint is about the landlord’s response to the resident’s: Reports of a cracked kitchen window. Complaint.

## Money Candidates

- score=14 amount=540.00 span={'page': 1, 'paragraph': 76, 'text_span': [1995, 2001]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 23 December 2025 2 Compensation Order The landlord must pay the resident £ 540 made up as follows: £ 390 for the landlord’s delay in repairing the resident’s kitchen window. £ 150 for the landlord’s response to the resident’s complaint. This must be pai
- score=14 amount=390.00 span={'page': 1, 'paragraph': 78, 'text_span': [2021, 2027]} context=e failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 23 December 2025 2 Compensation Order The landlord must pay the resident £ 540 made up as follows: £ 390 for the landlord’s delay in repairing the resident’s kitchen window. £ 150 for the landlord’s response to the resident’s complaint. This must be paid directly to the resident
- score=14 amount=150.00 span={'page': 1, 'paragraph': 82, 'text_span': [2096, 2102]} context=is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 23 December 2025 2 Compensation Order The landlord must pay the resident £ 540 made up as follows: £ 390 for the landlord’s delay in repairing the resident’s kitchen window. £ 150 for the landlord’s response to the resident’s complaint. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment
- score=3 amount=390.00 span={'page': 1, 'paragraph': 149, 'text_span': [7356, 7360]} context=reflect the full impact on the resident who likely experienced inconvenience and frustration and had to contact the landlord several times to chase the repair. Therefore we have made a finding of maladministration. We have ordered the landlord to pay additional compensation of £205, bringing the total compensation to £390. Compensation was calculated at £30 per month of delay (allowing one month for the repair). This is in line with our remedies guidance which states such a sum is appropriate wh
- score=3 amount=205.00 span={'page': 1, 'paragraph': 149, 'text_span': [7315, 7321]} context=ience it had caused. This amount does not reflect the full impact on the resident who likely experienced inconvenience and frustration and had to contact the landlord several times to chase the repair. Therefore we have made a finding of maladministration. We have ordered the landlord to pay additional compensation of £205, bringing the total compensation to £390. Compensation was calculated at £30 per month of delay (allowing one month for the repair). This is in line with our remedies guidance
- score=3 amount=185.00 span={'page': 1, 'paragraph': 149, 'text_span': [6961, 6966]} context=. The repair was completed over 14 months after the resident had initially reported the repair. As the landlord acknowledged, these delays were significant and had an adverse impact on the resident. In its final complaint response, the landlord apologised for the delays and acknowledged they were excessive. It awarded £185 compensation for the inconvenience it had caused. This amount does not reflect the full impact on the resident who likely experienced inconvenience and frustration and had to
- score=3 amount=100.00 span={'page': 1, 'paragraph': 157, 'text_span': [9396, 9401]} context=handling failures and awarded the resident £50 compensation. The compensation offered does not reflect the impact these failures had on the resident. Therefore, we have made a finding of maladministration in the landlord’s response to the resident’s complaint. We have ordered the landlord to pay the resident a further £100 compensation. This is in line with our remedies guidance which says such a sum is appropriate where failures adversely affected the resident but did not have a permanent impac
- score=3 amount=30.00 span={'page': 1, 'paragraph': 149, 'text_span': [7393, 7397]} context=ent who likely experienced inconvenience and frustration and had to contact the landlord several times to chase the repair. Therefore we have made a finding of maladministration. We have ordered the landlord to pay additional compensation of £205, bringing the total compensation to £390. Compensation was calculated at £30 per month of delay (allowing one month for the repair). This is in line with our remedies guidance which states such a sum is appropriate where a failure adversely affected the

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202331162.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/southern-housing-202331162/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/09-housing-ombudsman-202331162.draft_decision.json`

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
