# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202318374`
Source slug: `peabody-trust-202318374`
Target source ID: `202318374`
Title: Peabody Trust (202318374)
URL: https://www.housing-ombudsman.org.uk/decisions/peabody-trust-202318374/

## Manifest Strata

- Outcome raw: `reasonable redress`
- Outcome normalized: `reasonable-redress`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-12-22`
- Landlord: `Peabody Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `500.00`
- Draft region: `london` from `Peabody Trust (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident has reported recurring leaks affecting the bathroom and kitchen in the property in July 2023. The complaint is about the landlord’s response to the resident’s: Reports of a leak. Complaint.

## Money Candidates

- score=3 amount=500.00 span={'page': 1, 'paragraph': 140, 'text_span': [9396, 9401]} context=ws for discretionary awards where residents experience distress, inconvenience, or time and trouble due to service failure. It provides for higher awards where issues are prolonged or require repeated attendance. In this case, the landlord acknowledged delays in resolving the leak and the disruption caused. It awarded £500 in line with its compensation policy, having regard to the duration of the issue and the number of attendances required. Our remedies guidance suggests awards of this level ar
- score=1 amount=800.00 span={'page': 1, 'paragraph': 44, 'text_span': [1678, 1683]} context=e can make orders for the landlord to put things right. We have the discretion to make recommendations in all other cases within our jurisdiction. Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations It is recommended that the landlord pays the resident £800 compensation offered at Stage 2 , if it has not already done so. This comprises: £500 for time, trouble and inconvenience; and £300 reflecting the delay in issuing the stage 1
- score=1 amount=800.00 span={'page': 1, 'paragraph': 96, 'text_span': [3334, 3341]} context=her works were required. 21 December 2023 The landlord acknowledged the stage 2 escalation and confirmed that it would carry out the review. 06 February 2024 The landlord issued its stage 2 response , r evised its compensation offer to £500 for time and trouble and £ 3 00 for the impact of its poor complaint handling (£ 8 00 total). Referral to the Ombudsman The resident told us she did not consider the compensation the landlord offered was appropriate. S he said she was seeking an increased com
- score=1 amount=500.00 span={'page': 1, 'paragraph': 46, 'text_span': [1764, 1769]} context=recommendations in all other cases within our jurisdiction. Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations It is recommended that the landlord pays the resident £800 compensation offered at Stage 2 , if it has not already done so. This comprises: £500 for time, trouble and inconvenience; and £300 reflecting the delay in issuing the stage 1 complaint response. Our determination of reasonable redress is based on this sum being
- score=1 amount=500.00 span={'page': 1, 'paragraph': 64, 'text_span': [2678, 2685]} context=23 The landlord issued its stage 1 response . The landlord acknowledged delays in resolving the July 2023 leak, stated that works were now complete, and signposted the resident to make an insurance claim for damaged belongings. It awarded £ 2 00 for time, trouble and inconvenience and £300 for poor complaint handling (£ 5 00 total). 12 December 2023 The resident escalated her complaint to stage 2. She disputed key findings in the stage response, stated that leaks had been ongoing for years, and
- score=1 amount=500.00 span={'page': 1, 'paragraph': 90, 'text_span': [3250, 3255]} context=xperienced. She also disputed the supervisor’s November 2023 assessment that no further works were required. 21 December 2023 The landlord acknowledged the stage 2 escalation and confirmed that it would carry out the review. 06 February 2024 The landlord issued its stage 2 response , r evised its compensation offer to £500 for time and trouble and £ 3 00 for the impact of its poor complaint handling (£ 8 00 total). Referral to the Ombudsman The resident told us she did not consider the compensat
- score=1 amount=300.00 span={'page': 1, 'paragraph': 47, 'text_span': [1810, 1815]} context=jurisdiction. Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations It is recommended that the landlord pays the resident £800 compensation offered at Stage 2 , if it has not already done so. This comprises: £500 for time, trouble and inconvenience; and £300 reflecting the delay in issuing the stage 1 complaint response. Our determination of reasonable redress is based on this sum being paid to the resident. . Our investigation The
- score=1 amount=300.00 span={'page': 1, 'paragraph': 64, 'text_span': [2644, 2649]} context=complaint handler. 22 November 2023 The landlord issued its stage 1 response . The landlord acknowledged delays in resolving the July 2023 leak, stated that works were now complete, and signposted the resident to make an insurance claim for damaged belongings. It awarded £ 2 00 for time, trouble and inconvenience and £300 for poor complaint handling (£ 5 00 total). 12 December 2023 The resident escalated her complaint to stage 2. She disputed key findings in the stage response, stated that leaks

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202318374.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/peabody-trust-202318374/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/37-housing-ombudsman-202318374.draft_decision.json`

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
