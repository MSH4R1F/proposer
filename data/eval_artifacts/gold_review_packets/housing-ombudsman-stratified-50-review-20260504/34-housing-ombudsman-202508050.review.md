# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202508050`
Source slug: `sovereign-network-group-202508050`
Target source ID: `202508050`
Title: Sovereign Network Group (202508050)
URL: https://www.housing-ombudsman.org.uk/decisions/sovereign-network-group-202508050/

## Manifest Strata

- Outcome raw: `reasonable redress`
- Outcome normalized: `reasonable-redress`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-26`
- Landlord: `Sovereign Network Group`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `450.00`
- Draft region: `london` from `Sovereign Network Group (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident has v ulnerabilities including learning difficulties, mental health, and asthma , which the landlord is aware of. He complained about how it handled reports about a leak. The resident is represented by his sister in bringing the complaint to the landlord and us. For convenience, the sister and the resident are referred to as “the resident” in this report. The complaint is about the landlord’s handling of: Reports of a leak over the front door . The complaint.

## Money Candidates

- score=3 amount=450.00 span={'page': 1, 'paragraph': 68, 'text_span': [1848, 1853]} context=for the landlord to put things right. We have the discretion to make recommendations in all other cases within our jurisdiction. Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations If it has not already done so, the landlord should pay the resident the £450 as agreed in the final complaint response. Our finding of reasonable redress for the landlord’s handling of reports of a leak is made on the basis that this compensation is pa
- score=3 amount=200.00 span={'page': 1, 'paragraph': 78, 'text_span': [2385, 2390]} context=ld provide weekly updates to the resident. It must give clear timescales for completing both external and internal repairs and take all steps to meet them. If works can not be completed on time, it must explain why and provide a revised timescale. If it has not already done so, the landlord should pay the resident the £200 as agreed in the final complaint response. Our finding of reasonable redress for its complaint handling is made on the basis that this compensation is paid to the resident. Ou
- score=1 amount=650.00 span={'page': 1, 'paragraph': 135, 'text_span': [3628, 3633]} context=h its stage 2 response due to an inspection and follow on works. 23 October 2024 The landlord sent its stage 2 complaint response to the resident. It clarified details of the planned major works and gave intended start dates of November and December 2024. It apologised for its poor communication and delays. It offered £650 compensation comprising: £50 for its delay issuing a stage 1 response. £100 for its failure to escalate to stage 2 when requested. £50 for its delay issuing a stage 2 response
- score=1 amount=450.00 span={'page': 1, 'paragraph': 282, 'text_span': [7815, 7820]} context=atch of damp and mould . However, it gave details of other moving options which was a positive action . The landlord’s stage 2 response acknowledged communication had been poor and apologised for the stress and anxiety caused. It said the planned balcony works were due to start in November or December 2024 and offered £450 compensation for poor communication and inconvenience. Following the landlords final response, it completed balcony works on 12 December 2024. However, in January 2025 he repo
- score=1 amount=250.00 span={'page': 1, 'paragraph': 138, 'text_span': [3810, 3815]} context=major works and gave intended start dates of November and December 2024. It apologised for its poor communication and delays. It offered £650 compensation comprising: £50 for its delay issuing a stage 1 response. £100 for its failure to escalate to stage 2 when requested. £50 for its delay issuing a stage 2 response. £250 for the lack of communication between 2023 and 2024. £200 for the impact and inconvenience. What we found and why The circumstances of th is complaint are well known by the par
- score=1 amount=200.00 span={'page': 1, 'paragraph': 139, 'text_span': [3868, 3873]} context=December 2024. It apologised for its poor communication and delays. It offered £650 compensation comprising: £50 for its delay issuing a stage 1 response. £100 for its failure to escalate to stage 2 when requested. £50 for its delay issuing a stage 2 response. £250 for the lack of communication between 2023 and 2024. £200 for the impact and inconvenience. What we found and why The circumstances of th is complaint are well known by the parties involved, so it is not necessary to detail everything
- score=1 amount=200.00 span={'page': 1, 'paragraph': 341, 'text_span': [9327, 9332]} context=working days late in providing its stage 2 response . The landlord’s stage 2 response gave the resident conflicting dates of the planned works and an incorrect date of escalation . Landlords must ensure accuracy in complaint responses. That said, the landlord acknowledged its failings, apologised and made a n offer of £200 compensation. This is in line with our remedies guidance. Learning Landlords must ensure accuracy of information given in complaint responses to avoid confusion. Knowledge inf
- score=1 amount=100.00 span={'page': 1, 'paragraph': 136, 'text_span': [3704, 3709]} context=2024 The landlord sent its stage 2 complaint response to the resident. It clarified details of the planned major works and gave intended start dates of November and December 2024. It apologised for its poor communication and delays. It offered £650 compensation comprising: £50 for its delay issuing a stage 1 response. £100 for its failure to escalate to stage 2 when requested. £50 for its delay issuing a stage 2 response. £250 for the lack of communication between 2023 and 2024. £200 for the imp

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202508050.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/sovereign-network-group-202508050/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/34-housing-ombudsman-202508050.draft_decision.json`

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
