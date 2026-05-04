# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202334994`
Source slug: `london-borough-of-redbridge-202334994`
Target source ID: `202334994`
Title: London Borough of Redbridge (202334994)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-redbridge-202334994/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-27`
- Landlord: `London Borough of Redbridge`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `50.00`
- Draft region: `london` from `London Borough of Redbridge (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: In July 2022 the resident reported a broken fence in her back garden to the landlord. Following her report the landlord attended to inspect, however, it did not complete repairs. The complaint is about the landlord’s response to the fence repair. This investigation has also considered the landlord’s complaint handling.

## Money Candidates

- score=24 amount=50.00 span={'page': 1, 'paragraph': 57, 'text_span': [1897, 1901]} context=l other cases within our jurisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £50 to recognise the distress and inconvenience caused by its failure in response to the fence repair. This must be paid directly to the resident by the due date. The landlord must
- score=13 amount=50.00 span={'page': 1, 'paragraph': 165, 'text_span': [6413, 6417]} context=ght was appropriate but not proportionate on its own given the impact of its failure to clarify the repair responsibility sooner. The resident spent time and effort pursuing the matter and received misleading information before the landlord confirmed its position. To recognise this, we have ordered the landlord to pay £50 compensation to the resident. The compensation ordered is in line with our remedies guidance, which recommends this amount would be suitable where a failure caused inconvenienc

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202334994.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-redbridge-202334994/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/27-housing-ombudsman-202334994.draft_decision.json`

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
