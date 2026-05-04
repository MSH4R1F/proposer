# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202409223`
Source slug: `london-borough-of-croydon-202409223`
Target source ID: `202409223`
Title: London Borough of Croydon (202409223)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-croydon-202409223/

## Manifest Strata

- Outcome raw: `maladministration; reasonable redress`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-05`
- Landlord: `London Borough of Croydon`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `600.00`
- Draft region: `london` from `London Borough of Croydon (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in the property, a house with a shed in the garden. She is unhappy with delays to repairs which caused a bedroom in the property to be damp and cold and the time taken by the landlord to replace external doors in the house and shed. The landlord’s handling of: Repairs to the external structure of the property. Replacement of external doors. We have also investigated the landlord’s complaint handling.

## Money Candidates

- score=20 amount=600.00 span={'page': 1, 'paragraph': 98, 'text_span': [3327, 3333]} context=f the resident is unable to provide relevant electricity bills, given the time that ha s passed since the issue began, the landlord should discuss her estimated additional usage with her and make a reasonable offer of reimbursement. No later than 03 December 2025 3 Compensation order The landlord must pay the resident £ 600 to recognise the distress and inconvenience caused by its handling of repairs to the external structure of the building. This must be paid directly to the resident by the due
- score=9 amount=600.00 span={'page': 1, 'paragraph': 163, 'text_span': [10300, 10304]} context=icity expenditure and reimburse her for this. We have made a further order for the landlord to pay additional compensation of £150 to recognise the distress and inconvenience caused by its failure to reasonably address her concerns about the electricity expenditure. This brings the total compensation for this issue to £600. Complaint The landlord’s handling of replacement of external doors Finding Reasonable redress The landlord’s inspection on 4 December 2023 identified that the front door was
- score=9 amount=150.00 span={'page': 1, 'paragraph': 163, 'text_span': [10106, 10111]} context=caused her further distress and inconvenience. We have made an order for the landlord to contact the resident to obtain evidence, such as energy bills, for it to calculate her additional electricity expenditure and reimburse her for this. We have made a further order for the landlord to pay additional compensation of £150 to recognise the distress and inconvenience caused by its failure to reasonably address her concerns about the electricity expenditure. This brings the total compensation for t
- score=3 amount=450.00 span={'page': 1, 'paragraph': 134, 'text_span': [5663, 5668]} context=h the roof, but had identified some issues with the brickwork, which needed repointing. It said this work was scheduled for 30 September 2024. It acknowledged that it had missed an external door when it had replaced these and said it would attend to measure this within 28 days. It increased its compensation offers to: £450 for the doors £450 for the roof £144 for reimbursement of increased energy usage £150 for complaint handling Referral to the Ombudsman The resident asked us to investigate as
- score=3 amount=450.00 span={'page': 1, 'paragraph': 135, 'text_span': [5682, 5687]} context=identified some issues with the brickwork, which needed repointing. It said this work was scheduled for 30 September 2024. It acknowledged that it had missed an external door when it had replaced these and said it would attend to measure this within 28 days. It increased its compensation offers to: £450 for the doors £450 for the roof £144 for reimbursement of increased energy usage £150 for complaint handling Referral to the Ombudsman The resident asked us to investigate as she was unhappy that
- score=3 amount=450.00 span={'page': 1, 'paragraph': 173, 'text_span': [12188, 12193]} context=sed an issue with the new door on 7 October 2024, which the landlord resolved on 22 October 2024. Given the need to order a new door, this timeline suggests the landlord did install the new door within a reasonable timeframe. In its stage 2 response of 9 September 2024, the landlord increased its compensation offer to £450 and apologised for its failings. Our view is that the redress offered by the landlord was proportionate to the distress and inconvenience caused and in line with our remedies
- score=3 amount=425.00 span={'page': 1, 'paragraph': 160, 'text_span': [7989, 7994]} context=he landlord raised a new job on 17 June 2024 and a contractor attended on 24 June 2024. The inspection found that there were no faults with the roof, however there was brickwork that needed repointing. On 2 July 2024 the landlord told the resident it had incorrectly assessed her compensation and increased its offer to £425 – £225 for time and trouble and £200 for distress. On 15 July 2024 the resident asked the landlord to reconsider its offer as she said she had been using additional electricit
- score=3 amount=250.00 span={'page': 1, 'paragraph': 170, 'text_span': [11334, 11339]} context=of the doors until 17 June 2024, and it replaced the doors on 20 July 2024. We appreciate that there is a lead time to order new doors, but the 4-month delay in the landlord approving the order significantly delayed the installation, which was not appropriate. However, on 2 July 2024, the landlord offered the resident £250 compensation for the delay, which was reasonable and proportionate. In her escalation request of 15 July 2024, the resident said that the issue was with 5 doors, not just the

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202409223.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-croydon-202409223/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/05-housing-ombudsman-202409223.draft_decision.json`

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
