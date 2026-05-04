# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202325309`
Source slug: `sparrow-shared-ownership-limited-202325309`
Target source ID: `202325309`
Title: Sparrow Shared Ownership Limited (202325309)
URL: https://www.housing-ombudsman.org.uk/decisions/sparrow-shared-ownership-limited-202325309/

## Manifest Strata

- Outcome raw: `service failure; reasonable redress`
- Outcome normalized: `service-failure`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-12-18`
- Landlord: `Sparrow Shared Ownership Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `50.00`
- Draft region: `london` from `Sparrow Shared Ownership Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident has been a shared owner of the property since March 2022. The resident told the landlord she was not happy with the condition of the garden following repair works carried out in December 2022. The complaint is about the landlord’s handling of the resident’s concerns about the condition of her garden. We have also considered the landlord’s complaint handling.

## Money Candidates

- score=20 amount=50.00 span={'page': 1, 'paragraph': 78, 'text_span': [2666, 2670]} context=ting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 19 January 2026 2 Compensation order The landlord must pay the resident £50 to recognise the distress and inconvenience caused by its complaint handling failure. This must be paid directly to the resident by the due date. The landlord must provide us w
- score=14 amount=15.00 span={'page': 1, 'paragraph': 80, 'text_span': [2960, 2964]} context=ord must pay the resident £50 to recognise the distress and inconvenience caused by its complaint handling failure. This must be paid directly to the resident by the due date. The landlord must provide us with documentary evidence of the payment by the due date. The landlord may deduct from the total figure the sum of £15 offered during its internal complaints process, if already paid. No later than 1 9 January 2026 Recommendation Our recommendations are not binding, and a landlord may decide no
- score=3 amount=50.00 span={'page': 1, 'paragraph': 35, 'text_span': [1316, 1320]} context=y of reasons The landlord’s handling of the resident’s concerns about the condition of her garden The landlord was not responsible to carry out remedial works in the resident’s garden. Its attempts to arrange for the property developer to repair damage it had caused were reasonable. The landlord apologised and offered £50 compensation for the time it took to provide updates during its complaints process. The redress offered by the landlord was proportionate to the level of failings identified by
- score=3 amount=50.00 span={'page': 1, 'paragraph': 89, 'text_span': [3254, 3258]} context=e total figure the sum of £15 offered during its internal complaints process, if already paid. No later than 1 9 January 2026 Recommendation Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendation If it has not already done so, the landlord should re-offer the resident the £50 compensation offered during its complaints process. Our finding of reasonable redress for the landlord’s complaint handling is made on the basis that this compensation is re-of
- score=3 amount=50.00 span={'page': 1, 'paragraph': 152, 'text_span': [10132, 10136]} context=and Learn from Outcomes, as well as our own guidance on remedies. The landlord was not responsible to carry out maintenance or to make good damage caused to the garden. Its offer to arrange for the property developer to level the garden and put things right was reasonable in the circumstances. The landlord’s offer of £50 compensation for its lack of communication with the resident was also proportionate and consistent with an amount we would expect when considering our remedies guidance where th
- score=3 amount=50.00 span={'page': 1, 'paragraph': 164, 'text_span': [12163, 12167]} context=the evidence shows there were delays in the landlord’s complaint handling process. Although the landlord offered some redress, it did not address the delayed response to the initial complaint. This failure leads to a determination of service failure in the landlord’s complaint handling. The landlord is ordered to pay £50 compensation to the resident. This amount has been calculated in accordance with our remedies guidance for situations where there have been failures by the landlord and it did n
- score=1 amount=50.00 span={'page': 1, 'paragraph': 114, 'text_span': [4266, 4270]} context=ched area and level the garden, but the resident had declined as she wanted it to be re-turfed. 1 December 2023 The resident escalated her complaint as she was not happy with the landlord’s response . 29 December 2023 The landlord sent its stage 2 complaint response to the resident. The landlord apologised and offered £50 compensation for not replying to her correspondence , and £15 for not acknowledging her escalated complaint. Referral to the Ombudsman The resident referred her complaint to us
- score=1 amount=50.00 span={'page': 1, 'paragraph': 148, 'text_span': [8949, 8953]} context=ord to arrange this or give her compensation to allow her to get the works completed herself. The resident added that the landlord did not previously reply to her emails when she asked for updates. The landlord sent its stage 2 complaint response to the resident on 29 December 2023. The landlord apologised and offered £50 compensation for not always replying to her emails promptly. The landlord reiterated that she could arrange for the developer to do the previously proposed garden works, or she

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202325309.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/sparrow-shared-ownership-limited-202325309/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/46-housing-ombudsman-202325309.draft_decision.json`

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
