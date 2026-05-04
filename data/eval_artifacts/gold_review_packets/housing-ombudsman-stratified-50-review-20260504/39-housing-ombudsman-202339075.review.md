# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202339075`
Source slug: `clarion-housing-association-limited-202339075`
Target source ID: `202339075`
Title: Clarion Housing Association Limited (202339075)
URL: https://www.housing-ombudsman.org.uk/decisions/clarion-housing-association-limited-202339075/

## Manifest Strata

- Outcome raw: `resolved with intervention`
- Outcome normalized: `resolved-with-intervention`
- Matter types: `repairs_disrepair`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-24`
- Landlord: `Clarion Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1345.00`
- Draft region: `london` from `Clarion Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: In November 2021 the resident told the landlord she had concerns about the safety of the insulation in her loft. She chased the landlord for updates about her reports throughout 2022. Despite multiple inspections, at the time of making her complaint in March 2023, the repairs remained outstanding. The complaint is about the landlord’s response to the resident’s concerns about insulation.

## Money Candidates

- score=3 amount=1345.00 span={'page': 1, 'paragraph': 44, 'text_span': [1051, 1059]} context=Our decision (determination) The complaint was resolved with intervention. We have made recommendations for the landlord to put things right. Summary of reasons At the end of the complaints process the landlord apologised to the resident for its poor communication, the delays and inconvenience caused . It awarded h er £1 ,345 compensation and completed the outstanding works . The landlord did not provide the resident with an explanation of the steps it would take to improve communication with it
- score=3 amount=250.00 span={'page': 1, 'paragraph': 57, 'text_span': [1638, 1645]} context=vided it with a summary of our understanding o f events. This included some comments on areas that could have been handled better, such as providing the resident with an explanation, and what the landlord could do to resolve the resident’s complaint. Following our intervention, the landlord offered to pay the resident £2 5 0 compensation and provide h er with the explanation s he was seeking. Both parties agreed to this as a resolution to the complaint. We are therefore satisfied that, following
- score=3 amount=250.00 span={'page': 1, 'paragraph': 72, 'text_span': [2289, 2294]} context=anation to the points outlined below, we are satisfied the complaint will be resolved satisfactorily. Putting things right Recommendations The complaint has been resolved with intervention on the basis the landlord follows our recommendations . Our recommendations 1. Within 14 days the landlord should pay the resident £250 compensation. 2. Within 14 days the landlord should provide the resident with a written explanation to set out the steps it has taken since this incident / timeframe to improv

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202339075.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/clarion-housing-association-limited-202339075/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/39-housing-ombudsman-202339075.draft_decision.json`

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
