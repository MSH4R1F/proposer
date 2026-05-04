# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202410679`
Source slug: `london-quadrant-housing-trust-202410679`
Target source ID: `202410679`
Title: London & Quadrant Housing Trust   (202410679)
URL: https://www.housing-ombudsman.org.uk/decisions/london-quadrant-housing-trust-202410679/

## Manifest Strata

- Outcome raw: `service failure`
- Outcome normalized: `service-failure`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-12-05`
- Landlord: `London & Quadrant Housing Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `350.00`
- Draft region: `london` from `London & Quadrant Housing Trust (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident reported damp and mould in his property, which he believed was caused by issues with the guttering , for which the landlord was responsible. He later complained about how the landlord handled the repair and the delays that occurred. The complaint is about the landlord’s handling of: Repairs to guttering and the resulting damp and mould. The complaint.

## Money Candidates

- score=18 amount=350.00 span={'page': 1, 'paragraph': 65, 'text_span': [1940, 1946]} context=l other cases within our jurisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 250 for its failures in handling the repair. £ 100 for its poor complaint handling. This must be paid directly to the resident by the due date. The land
- score=18 amount=250.00 span={'page': 1, 'paragraph': 67, 'text_span': [1966, 1972]} context=urisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 250 for its failures in handling the repair. £ 100 for its poor complaint handling. This must be paid directly to the resident by the due date. The landlord must provide document
- score=18 amount=100.00 span={'page': 1, 'paragraph': 73, 'text_span': [2013, 2019]} context=our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 250 for its failures in handling the repair. £ 100 for its poor complaint handling. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by the due date. This i
- score=9 amount=320.00 span={'page': 1, 'paragraph': 84, 'text_span': [2214, 2219]} context=tion order The landlord must pay the resident £ 350 made up as follows: £ 250 for its failures in handling the repair. £ 100 for its poor complaint handling. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by the due date. This is in addition to the £320 the landlord has already offered the resident in its final response. No later than 20 January 2026 2 Inspection order The landlord must contact the resident to arrange an insp
- score=3 amount=320.00 span={'page': 1, 'paragraph': 175, 'text_span': [5595, 5600]} context=needed approval from the S ection 20 referral team. The landlord stated that once approval was confirmed , it would complete the repairs and address the damp and mould. It acknowledged the S ection 20 process was complex but said it would treat the matter as a priority. The landlord apologised and offered the resident £320 compensation . Referral to the Ombudsman The resident brought his complaint to us because he remained dissatisfied with the landlord’s final response. He disagreed with the la
- score=3 amount=320.00 span={'page': 1, 'paragraph': 217, 'text_span': [8311, 8316]} context=he resident once received. In its final response in August 2024, the landlord said it had received the quote but needed approval from the S ection 20 referral team to confirm the necessary permissions to complete the repair. It explained it was treating the matter as a priority, apologised to the resident, and offered £320 compensation. The evidence confirms the landlord took a range of actions to investigate and resolve the guttering prior to and during the complaint, but that it had done so on

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202410679.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-quadrant-housing-trust-202410679/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/42-housing-ombudsman-202410679.draft_decision.json`

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
