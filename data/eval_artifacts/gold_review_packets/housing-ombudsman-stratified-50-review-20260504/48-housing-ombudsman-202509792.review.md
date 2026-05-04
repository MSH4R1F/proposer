# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202509792`
Source slug: `barnsley-metropolitan-borough-council-202509792`
Target source ID: `202509792`
Title: Barnsley Metropolitan Borough Council (202509792)
URL: https://www.housing-ombudsman.org.uk/decisions/barnsley-metropolitan-borough-council-202509792/

## Manifest Strata

- Outcome raw: `severe maladministration; no maladministration; maladministration`
- Outcome normalized: `severe-maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-28`
- Landlord: `Barnsley Metropolitan Borough Council`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1500.00`
- Draft region: `london` from `Barnsley Metropolitan Borough Council (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident has lived at a 1-bedroom semi-detached bungalow since 2019. The landlord’s records say the resident is elderly and she suffers from breathing problems. The resident has experienced problems with damp and mould at the property and first raised concerns to the landlord in 2020 . The complaint is about the landlord’s handling of: Reports of damp and mould in the property. The associated complaint.

## Money Candidates

- score=20 amount=1500.00 span={'page': 1, 'paragraph': 99, 'text_span': [2627, 2636]} context=report. The apology must be made by a director at the landlord. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 07 January 2026 2 Compensation order The landlord must pay the resident £1, 5 00 to recognise the distress and inconvenience caused by its handling of her report s of damp and mould in the property. This must be paid directly to the resident by the due
- score=5 amount=1500.00 span={'page': 1, 'paragraph': 443, 'text_span': [13970, 13979]} context=lure to effectively deal with the damp and mould at the property over a 5 year period, together with the failure to provide appropriate redress to this point, leads to a determination of severe maladministration in its handling of the resident’s reports of damp and mould in the property. The landlord is ordered to pay £1, 5 00 compensation for the distress and inconvenience caused by its failings. This amount is calculated in line with our remedies guidance . In addition, the landlord is ordered
- score=5 amount=350.00 span={'page': 1, 'paragraph': 402, 'text_span': [12090, 12096]} context=he resident’s complaint, the evidence shows there were substantial delays by the landlord to effectively address the causes of damp and mould in the resident’s property . Both of the landlord’s complaint responses recognised it had not taken sufficient action to address issues the resident raised. The landlord offered £ 350 overall compensation for the distress and inconvenience the lack of action caused the resident. There is clear evidence of repeated visits to conduct works at the property, w
- score=3 amount=350.00 span={'page': 1, 'paragraph': 415, 'text_span': [12889, 12894]} context=ere are admitted failings by a landlord, our role is to consider whether the redress offered by the landlord put things right and resolved the resident’s complaint satisfactorily in the circumstances. When considering the landlord’s compensation offer against the criteria set out in our remedies guidance, its offer of £350 is not in line with an amount we would expect where the failings have resulted in a severe long term impact which occurred over a signif i cant period of time and where the la
- score=2 amount=350.00 span={'page': 1, 'paragraph': 106, 'text_span': [2946, 2952]} context=£1, 5 00 to recognise the distress and inconvenience caused by its handling of her report s of damp and mould in the property. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by the due date. The landlord may deduct from the total figure the sum of £ 350 offered during its internal complaints process, if already paid. 07 January 2026 3 Completing the works The landlord must take all steps to ensure an inspection is completed p
- score=1 amount=250.00 span={'page': 1, 'paragraph': 319, 'text_span': [10222, 10227]} context=pairs to the roof, chimney, brickwork and guttering due to water ingress . They also said remedial works should be carried out to treat the internal areas affected by damp and mould. On 3 April 2025 the landlord sent its response to the resident at stage 1 of its complaints process. The landlord apologised and offered £250 compensation for the delays in taking action to treat damp and mould since 2024 . It accepted that it had not stopped the damp and mould returning in the property , and said i
- score=1 amount=100.00 span={'page': 1, 'paragraph': 156, 'text_span': [4606, 4611]} context=g out inspections and repairs. The landlord said it would carry out further repairs. The resident escalated her complaint as she was not happy with its response . 9 May 2025 The landlord sent its stage 2 complaint response to the resident. It said a number of repairs had been carried out, but it apologised and offered £100 further compensation as it had not explain ed what action it would take following her initial complaint. Referral to the Ombudsman The resident referred her complaint to us as
- score=1 amount=100.00 span={'page': 1, 'paragraph': 362, 'text_span': [11098, 11103]} context=insulation or damp – proof course. The resident called the landlord on 22 April 2025 and escalated the complaint as the landlord did not provide a schedule of repair works following its stage 1 response. The landlord sent its stage 2 response to the resident on 9 May 2025. The landlord apologised and offered a further £100 compensation for not telling her when the repairs would be carried out , as it said it would . The landlord told the resident it would remove the chimney by the end of October

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202509792.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/barnsley-metropolitan-borough-council-202509792/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/48-housing-ombudsman-202509792.draft_decision.json`

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
