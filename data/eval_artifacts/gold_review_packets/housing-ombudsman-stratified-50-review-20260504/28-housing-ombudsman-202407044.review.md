# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202407044`
Source slug: `clarion-housing-association-limited-202407044`
Target source ID: `202407044`
Title: Clarion Housing Association Limited (202407044)
URL: https://www.housing-ombudsman.org.uk/decisions/clarion-housing-association-limited-202407044/

## Manifest Strata

- Outcome raw: `maladministration; reasonable redress`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-28`
- Landlord: `Clarion Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `950.00`
- Draft region: `london` from `Clarion Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident first reported concerns about a retaining fence in the property’s garden in August 2022. The landlord inspected it and agreed that works needed to be done. However, works were delayed. She complained to the landlord on 21 May 2024 about a lack of progress. It apologised and paid her compensation. However, it still did not carry out the repairs. She complained to us in October 2024. The landlord carried out works on the fence in July 2025. The complaint is about the landlord’s handling of the resident’s reports of repairs required to a retaining fence in the garden. We have also considered the landlord’s complaint handling.

## Money Candidates

- score=14 amount=950.00 span={'page': 1, 'paragraph': 76, 'text_span': [2682, 2689]} context=ting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 09 January 2026 2 Compensation order The landlord must pay the resident £ 9 50 for t he distress, inconvenience, time and trouble caused by its handling of the resident’s reports of repairs required to a retaining fence in the garden. This must be paid
- score=1 amount=700.00 span={'page': 1, 'paragraph': 145, 'text_span': [5298, 5303]} context=complaint process . 21 August 2024 The landlord issued its stage 2 complaint response. It said the resident : Said that the landlord had failed to carry out the works for 3 years. Wanted greater compensation. Wanted the works completed within a reasonable timeframe. It said it would increase its compensation offer to £700 in total and would carry out works as soon as possible. 25 October 2024 The resident asked us to investigate. She said her back garden was unsafe so she could not use it. She s
- score=1 amount=700.00 span={'page': 1, 'paragraph': 175, 'text_span': [8662, 8667]} context=netheless, the resident can always report any further concerns to the landlord. If she is unhappy with its response, she can complain again. We accept, of course, that these works were complex and that they were bound to take some time. Nonetheless, the delay overall was unacceptable. The landlord offered the resident £700 in compensation in the stage 2 complaint response of 21 August 2024. The amount of £650 of this was compensation for the delays to the works and the frustration this caused he
- score=1 amount=650.00 span={'page': 1, 'paragraph': 34, 'text_span': [1484, 1489]} context=rd has offered reasonable redress for its complaint handling failure. We have made orders for the landlord to put things right. Summary of reasons Resident’s reports of repairs required to a garden wall. The landlord delayed for several years in carrying out works to the retaining fence. It has offered compensation of £650 in recognition of delay up to August 2024. However, the delay then continued until July 2025. C omplaint handling The landlord delayed significantly in providing a stage 1 res
- score=1 amount=650.00 span={'page': 1, 'paragraph': 175, 'text_span': [8750, 8755]} context=s unhappy with its response, she can complain again. We accept, of course, that these works were complex and that they were bound to take some time. Nonetheless, the delay overall was unacceptable. The landlord offered the resident £700 in compensation in the stage 2 complaint response of 21 August 2024. The amount of £650 of this was compensation for the delays to the works and the frustration this caused her, particularly given her disability. This was an appropriate sum to compensate the resi
- score=1 amount=350.00 span={'page': 1, 'paragraph': 131, 'text_span': [4738, 4743]} context=had, however, been a delay in finding out who had the responsibility for maintaining the fencing. It had now verified that it was responsible. Said it would therefore visit the site in August 2024 to survey the area and work out a solution. Apologised for the inconvenience its inaction had caused. Offered the resident £350 in compensation comprising: £300 for the inconvenience caused by the delay in addressing the issue. £50 for its delayed complaint response. 20 July 2024 The resident asked to
- score=1 amount=300.00 span={'page': 1, 'paragraph': 131, 'text_span': [4771, 4776]} context=ding out who had the responsibility for maintaining the fencing. It had now verified that it was responsible. Said it would therefore visit the site in August 2024 to survey the area and work out a solution. Apologised for the inconvenience its inaction had caused. Offered the resident £350 in compensation comprising: £300 for the inconvenience caused by the delay in addressing the issue. £50 for its delayed complaint response. 20 July 2024 The resident asked to escalate her complaint to stage 2
- score=1 amount=50.00 span={'page': 1, 'paragraph': 37, 'text_span': [1723, 1727]} context=ars in carrying out works to the retaining fence. It has offered compensation of £650 in recognition of delay up to August 2024. However, the delay then continued until July 2025. C omplaint handling The landlord delayed significantly in providing a stage 1 response to the resident’s complaint. However, it offered her £50 and an apology for this delay which is sufficient to redress the inconvenience and distress this failure caused. Putting things right Where we find service failure, maladminist

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202407044.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/clarion-housing-association-limited-202407044/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/28-housing-ombudsman-202407044.draft_decision.json`

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
