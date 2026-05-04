# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202441018`
Source slug: `london-borough-of-hammersmith-and-fulham-202441018`
Target source ID: `202441018`
Title: London Borough of Hammersmith and Fulham (202441018)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-hammersmith-and-fulham-202441018/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-04`
- Landlord: `London Borough of Hammersmith and Fulham`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `500.00`
- Draft region: `london` from `London Borough of Hammersmith and Fulham (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident is a secure tenant of the landlord which is a local authority. The tenancy started on 17 September 2012. The property is a 1 bedroom ground floor flat in a purpose-built block. The landlord is aware that the resident has vulnerabilities, including mobility issues. The landlord carried out property inspections during March and June 2024. It identified a schedule of works which included the shower enclosure in the wet room. On 21 June the resident emailed the landlord to ask to delay works. Works commenced during August. On 23 September the resident moved to temporary accommodation. Works were completed in October 2024. The complaint is about the landlord’s handling of:...

## Money Candidates

- score=20 amount=500.00 span={'page': 1, 'paragraph': 80, 'text_span': [2863, 2869]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision, meaningful and empathetic. It has due regard to our apologies guidance . No later than 0 2 December 2025 2 Compensation order The landlord must pay the resident £ 500 made up as follows: £ 400 for the distress and inconvenience caused by the failures in it handling of the repairs. £ 100 for the distress and inconvenience caused by its comp
- score=20 amount=400.00 span={'page': 1, 'paragraph': 82, 'text_span': [2889, 2895]} context=e failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision, meaningful and empathetic. It has due regard to our apologies guidance . No later than 0 2 December 2025 2 Compensation order The landlord must pay the resident £ 500 made up as follows: £ 400 for the distress and inconvenience caused by the failures in it handling of the repairs. £ 100 for the distress and inconvenience caused by its complaint handling failures. T
- score=16 amount=100.00 span={'page': 1, 'paragraph': 86, 'text_span': [2984, 2990]} context=failures identified in this decision, meaningful and empathetic. It has due regard to our apologies guidance . No later than 0 2 December 2025 2 Compensation order The landlord must pay the resident £ 500 made up as follows: £ 400 for the distress and inconvenience caused by the failures in it handling of the repairs. £ 100 for the distress and inconvenience caused by its complaint handling failures. This must be paid directly to the resident by the due date. The landlord must provide documentar
- score=1 amount=1000.00 span={'page': 1, 'paragraph': 471, 'text_span': [20439, 20445]} context=ing and tried to put things right. However, the amount of compensation offered was not proportionate to the distress and inconvenience experienced by the resident. Therefore the landlord has been ordered to pay the resident £400. This is in line with the landlord’s compensation which says it will offer between £300 to £1000 compensation where we have found maladministration. The landlord may deduct the £200 it has offered if this has already been paid. Complaint H andling of the complaint Findin
- score=1 amount=400.00 span={'page': 1, 'paragraph': 471, 'text_span': [20343, 20347]} context=es and put things right. The landlord acknowledged some of its failures, demonstrated some learning and tried to put things right. However, the amount of compensation offered was not proportionate to the distress and inconvenience experienced by the resident. Therefore the landlord has been ordered to pay the resident £400. This is in line with the landlord’s compensation which says it will offer between £300 to £1000 compensation where we have found maladministration. The landlord may deduct th
- score=1 amount=300.00 span={'page': 1, 'paragraph': 471, 'text_span': [20431, 20436]} context=me learning and tried to put things right. However, the amount of compensation offered was not proportionate to the distress and inconvenience experienced by the resident. Therefore the landlord has been ordered to pay the resident £400. This is in line with the landlord’s compensation which says it will offer between £300 to £1000 compensation where we have found maladministration. The landlord may deduct the £200 it has offered if this has already been paid. Complaint H andling of the complain
- score=1 amount=225.00 span={'page': 1, 'paragraph': 390, 'text_span': [7786, 7791]} context=alth . It signposted the resident to make an insurance claim for los s or damage to personal belongings and personal injuries . There was no evidence of service failure following its Stage 1 complaint response . It apologise d for the issues . It said it woul d use its learning to ensure changes were made. It offer ed £225 compensation comprised of: £25 for the delay in its complaint response. £200 for time, trouble and inconvenience . It would monitor works and work closely with the resident un
- score=1 amount=200.00 span={'page': 1, 'paragraph': 396, 'text_span': [7863, 7868]} context=age to personal belongings and personal injuries . There was no evidence of service failure following its Stage 1 complaint response . It apologise d for the issues . It said it woul d use its learning to ensure changes were made. It offer ed £225 compensation comprised of: £25 for the delay in its complaint response. £200 for time, trouble and inconvenience . It would monitor works and work closely with the resident until she was satisfied . It would also arrange for them to be post inspected .

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202441018.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-hammersmith-and-fulham-202441018/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/21-housing-ombudsman-202441018.draft_decision.json`

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
