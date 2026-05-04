# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202427803`
Source slug: `clarion-housing-association-limited-202427803`
Target source ID: `202427803`
Title: Clarion Housing Association Limited (202427803)
URL: https://www.housing-ombudsman.org.uk/decisions/clarion-housing-association-limited-202427803/

## Manifest Strata

- Outcome raw: `service failure; reasonable redress`
- Outcome normalized: `service-failure`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-05`
- Landlord: `Clarion Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `650.00`
- Draft region: `london` from `Clarion Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a ground-floor flat. In August 2023, they contacted the landlord to ask when it would complete repairs to the render at the rear of the property and to a brick pillar in the front garden. While both the resident and his partner contacted the landlord during the complaints procedure, this report refers to them collectively as ‘the resident’. The complaint is about the landlord’s handling of: External repairs to the render of the property and a brick pillar in the garden. The associated complaint.

## Money Candidates

- score=24 amount=650.00 span={'page': 1, 'paragraph': 59, 'text_span': [2296, 2301]} context=l other cases within our jurisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £650 to recognise the distress and inconvenience caused by its handling of the external repairs. This includes the £550 it offered previously th r ough its complaints procedure and
- score=20 amount=550.00 span={'page': 1, 'paragraph': 61, 'text_span': [2411, 2416]} context=specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £650 to recognise the distress and inconvenience caused by its handling of the external repairs. This includes the £550 it offered previously th r ough its complaints procedure and an additional payment of £100. This must be paid directly to the resident by the due date. The landlord must provid
- score=20 amount=100.00 span={'page': 1, 'paragraph': 66, 'text_span': [2502, 2506]} context=he due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £650 to recognise the distress and inconvenience caused by its handling of the external repairs. This includes the £550 it offered previously th r ough its complaints procedure and an additional payment of £100. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by the due date. The landlord may deduct from the total
- score=7 amount=100.00 span={'page': 1, 'paragraph': 190, 'text_span': [14163, 14168]} context=£550 did not account for this. On this basis, there was service failure in its handling of the external repairs. Our remedies guidance (published on our website) sets out our approach to compensation. It says that when the landlord’s offer does not fully reflect the impact on the resident, an additional award of up to £100 may be appropriate. In this case, we consider a further £100 reasonable to recognise the landlord’s failure to fulfil the commitments made during the complaints procedure. We
- score=5 amount=100.00 span={'page': 1, 'paragraph': 190, 'text_span': [14224, 14229]} context=ce failure in its handling of the external repairs. Our remedies guidance (published on our website) sets out our approach to compensation. It says that when the landlord’s offer does not fully reflect the impact on the resident, an additional award of up to £100 may be appropriate. In this case, we consider a further £100 reasonable to recognise the landlord’s failure to fulfil the commitments made during the complaints procedure. We have ordered the landlord to pay this in addition to the comp
- score=3 amount=650.00 span={'page': 1, 'paragraph': 130, 'text_span': [5223, 5227]} context=ick pillar was repaired on 17 September 2024, corrected earlier misinformation about when damp and mould concerns were first raised, and acknowledged the overall repair delays. It arranged a post-inspection for 30 October 2024 and awarded an additional £250 for its failures , increasing the total compensation offer to £650. Referral to the Ombudsman The resident referred the complaint to us as they felt the compensation offered did not reflect the extent of the delays and failures they experienc
- score=3 amount=550.00 span={'page': 1, 'paragraph': 189, 'text_span': [13843, 13848]} context=etween November 2024 and February 2025, we will not order a further inspection of the rende r. Putting things right While the landlord sought to put things right during its complaints procedure, it did not fulfil all the commitments made in its complaint responses (as identified above). Its total compensation offer of £550 did not account for this. On this basis, there was service failure in its handling of the external repairs. Our remedies guidance (published on our website) sets out our appro
- score=3 amount=300.00 span={'page': 1, 'paragraph': 107, 'text_span': [4494, 4499]} context=not raised again until after its repairs service moved in-house in August 2023. The rebuild was scheduled for September 2024. It apologised for the delays and its poor communication. It offered the resident: £50 for complaint handling failures. £50 under the right-to-repair scheme relating to the brick pillar delays. £300 for delays and inconvenience caused by the repair delays. The resident escalated their complaint the same day. They were dissatisfied with the compensation offered and the repa

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202427803.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/clarion-housing-association-limited-202427803/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/40-housing-ombudsman-202427803.draft_decision.json`

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
