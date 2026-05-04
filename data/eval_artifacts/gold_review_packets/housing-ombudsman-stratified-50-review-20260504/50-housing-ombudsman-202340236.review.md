# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202340236`
Source slug: `metropolitan-thames-valley-housing-mtv-202340236`
Target source ID: `202340236`
Title: Metropolitan Thames Valley Housing (MTV) (202340236)
URL: https://www.housing-ombudsman.org.uk/decisions/metropolitan-thames-valley-housing-mtv-202340236/

## Manifest Strata

- Outcome raw: `None`
- Outcome normalized: `unknown`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-27`
- Landlord: `Metropolitan Thames Valley Housing (MTV)`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `960.00`
- Draft region: `london` from `Metropolitan Thames Valley Housing (MTV) (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: On 27 December 2023 the resident reported to the landlord there was a leak into the property which was causing water damage. The resident complained to the landlord on 5 January 2025 that it had not repaired the leak. The repairs to address the leak and the resultant water damage in the property were completed by the landlord in October 2024. The complaint is about the landlord’s handling of a leak into the property.

## Money Candidates

- score=3 amount=960.00 span={'page': 1, 'paragraph': 34, 'text_span': [1573, 1577]} context=2025 and provided it with a summary of our understanding of events. This included some comments on areas that the landlord could have handled better and what it could do to resolve the resident’s complaint. The landlord offered to apologise to the resident for the repair delays and increased its compensation offer to £960. Both parties agreed to this as a resolution to the complaint. We are therefore satisfied that, following our intervention, the landlord has agreed to take actions to remedy th
- score=3 amount=960.00 span={'page': 1, 'paragraph': 45, 'text_span': [2015, 2020]} context=ntion, the landlord has agreed to take actions to remedy the matters which resolve the complaint satisfactorily. Putting things right Recommendations T he complaint has been resolved with intervention on this basis the landlord follows our recommendations . Our recommendations The landlord should apolog ise and make a £960 compensation payment to the resident. The landlord should provide us with documentary evidence that it has sent the apology and paid the compensation to the resident.
- score=3 amount=360.00 span={'page': 1, 'paragraph': 32, 'text_span': [986, 991]} context=ber 2024. What the complaint is about The complaint is about the landlord’s handling of a leak into the property. Our decision (determination) The complaint was resolved following our intervention. We have made recommendations for the landlord to put things right. Summary of reasons The landlord apologised and offered £360 compensation for its failure to repair the leak and the damage it caused the property in its complaint responses sent to the resident in March and April 2024. The outstanding

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202340236.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/metropolitan-thames-valley-housing-mtv-202340236/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/50-housing-ombudsman-202340236.draft_decision.json`

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
