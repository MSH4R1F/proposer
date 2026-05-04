# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202413845`
Source slug: `citizen-housing-group-limited-202413845`
Target source ID: `202413845`
Title: Citizen Housing Group Limited (202413845)
URL: https://www.housing-ombudsman.org.uk/decisions/citizen-housing-group-limited-202413845/

## Manifest Strata

- Outcome raw: `service failure; reasonable redress`
- Outcome normalized: `service-failure`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-29`
- Landlord: `Citizen Housing Group Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `250.00`
- Draft region: `london` from `Citizen Housing Group Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident moved into a newly built property in April 2024. During the 12-month defects liability period, included in his lease agreement, he reported a scratch on the kitchen worktop. The landlord declined to address the issue, stating it was not responsible because the defect had not been raised at the time of the property handover. The complaint is about the landlord’s response to: Reports of a damaged kitchen worktop. The complaint.

## Money Candidates

- score=22 amount=250.00 span={'page': 1, 'paragraph': 63, 'text_span': [2156, 2164]} context=other cases within our jurisdiction. Order The l andlord must comply with our order in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our order by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 2 5 0 to recognise the inconvenience caused by its response to reports of a damaged kitchen worktop. This must be paid directly to the resident by the due date. The landlord must
- score=3 amount=50.00 span={'page': 1, 'paragraph': 126, 'text_span': [4230, 4234]} context=referred to the property handover form signed by the resident on 25 April 2024, which did not record any damage to the worktop. It said the worktop had been accepted as undamaged and that it did not consider itself responsible for the repair. The landlord apologised for the delay in responding and offered the resident £50 compensation. Referral to the Ombudsman The resident brought his complaint to the Service . He remained unhappy as the landlord stopped responding to the worktop issue. He also
- score=1 amount=250.00 span={'page': 1, 'paragraph': 147, 'text_span': [5029, 5034]} context=r position that it was not responsible for repairing the worktop. It confirmed that although it had acknowledged the original complaint submitted, it recognised it had not provided a response. It said that this should have been addressed in its stage 2 response. It apologised, identified learning and offered a further £250 compensation in recognition of its poor complaint handling. What we found and why The circumstances of th is complaint are well known by the parties involved, so it is not nec
- score=1 amount=250.00 span={'page': 1, 'paragraph': 181, 'text_span': [9090, 9095]} context=urther response on 22 January 2025. It stated that while gathering evidence for this complaint, it had identified that it had not been handled in line with its process, as a stage 1 response was not issued. It apologised, confirmed that it had spoken to staff about complaint handling to prevent recurrence, and offered £250 compensation. The landlord did not follow its complaints policy, as it failed to issue a stage 1 response after acknowledging the complaint. As a result, the resident had to c
- score=1 amount=50.00 span={'page': 1, 'paragraph': 180, 'text_span': [8677, 8681]} context=that he had not received a stage 1 response. The landlord acknowledged the stage 2 complaint on 6 June 2024 and issued a response on 10 July 2024. In its reply, the landlord acknowledged delays in its complaint handling and attributed these to a system error, which it said had been resolved. It apologised and offered £50 compensation. Following the resident’s referral to the Ombudsman, the landlord issued a further response on 22 January 2025. It stated that while gathering evidence for this com

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202413845.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/citizen-housing-group-limited-202413845/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/44-housing-ombudsman-202413845.draft_decision.json`

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
