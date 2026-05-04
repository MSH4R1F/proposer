# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202404522`
Source slug: `sovereign-network-group-202404522`
Target source ID: `202404522`
Title: Sovereign Network Group (202404522)
URL: https://www.housing-ombudsman.org.uk/decisions/sovereign-network-group-202404522/

## Manifest Strata

- Outcome raw: `service failure; reasonable redress`
- Outcome normalized: `service-failure`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-12`
- Landlord: `Sovereign Network Group`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `50.00`
- Draft region: `london` from `Sovereign Network Group (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a 2-bedroom first floor flat, with her children. The landlord is aware that 1 of the children has asthma. She complained about damp and mould in the children’s bedroom. The complaint is about the landlord’s handling of: Reports of damp and mould in a bedroom. The complaint.

## Money Candidates

- score=24 amount=50.00 span={'page': 1, 'paragraph': 52, 'text_span': [1768, 1773]} context=l other cases within our jurisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 50 to recognise the distress and inconvenience caused by its handling of the complaint. This must be paid directly to the resident by the due date. The landlord must provide docu
- score=3 amount=1080.00 span={'page': 1, 'paragraph': 208, 'text_span': [8480, 8486]} context=duled and the mould wash was complete. It acknowledged the delays and increased its compensation offer to £675 for the impact of the delay, distress, time, and trouble. Following its final response, the resident challenged its compensation offer. The landlord admitted it had miscalculated its offer and increased it to £1,080. Its offer was in line with our remedies guidance for when there has been a significant impact. In summary, while the landlord delayed in completing the required repairs, it
- score=3 amount=675.00 span={'page': 1, 'paragraph': 169, 'text_span': [4392, 4396]} context=mation about the flat below . It said its surveyor visited on 12 February 2024 and recommended further works , but delays followed in forwarding the report and approving the repair s . It confirmed the orders had been raised , apologised for the lack of action since October 2023 and increased its compensation offer to £675. Referral to the Ombudsman The resident asked us to investigate, stating that although the mould was treated, the root cause remained un re solved. She told us that she moved
- score=3 amount=430.00 span={'page': 1, 'paragraph': 121, 'text_span': [3485, 3490]} context=edroom wall which required treatment . It also noted the absence of a kitchen extrac tor fan . It acknowledged taking no action despite the resident’s follow-ups and apologi s ed. It said it would conduct an urgent mould wash, instal l a kitchen extractor fan and instruct a surveyor to find the root cause . It offered £430 compensation for time and inconvenience. 23 February 2024 The resident asked the landlord to escalate the complaint due to poor communication and a missed response deadline .
- score=1 amount=675.00 span={'page': 1, 'paragraph': 207, 'text_span': [8266, 8271]} context=line with its policy. In its stage 2 response on 3April 2024, the landlord invited the resident to submit a SAR. However, it could have shared the inspection report upon completion. It confirmed the works were scheduled and the mould wash was complete. It acknowledged the delays and increased its compensation offer to £675 for the impact of the delay, distress, time, and trouble. Following its final response, the resident challenged its compensation offer. The landlord admitted it had miscalcula
- score=1 amount=430.00 span={'page': 1, 'paragraph': 203, 'text_span': [6669, 6674]} context=. No further communication is recorded until 21 January 2024, when the resident submitted her complaint. She said she never received the survey report, no work had been done, and the issue remained unresolved. The landlord’s stage 1 response acknowledged its failings, apologised and outlined an action plan. It offered £430 compensation for the time taken and inconvenience caused. However, it did not demonstrate that it advised the resident to claim on contents insurance, provide liability insure
- score=0 amount=1080.00 span={'page': 1, 'paragraph': 67, 'text_span': [2293, 2302]} context=nt by the due date. No later than 10 December 2025 Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations Our finding of reasonable redress for the landlord’s handling of r eports of damp and mould is made on the basis that it pays the resident the sum of £1 , 080 it offered on 10 April 2024, if not already paid. We recommend the landlord arrange a survey to assess the property , including any ongoing damp and identify any repairs i

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202404522.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/sovereign-network-group-202404522/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/41-housing-ombudsman-202404522.draft_decision.json`

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
