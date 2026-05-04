# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202332724`
Source slug: `homes-plus-limited-202332724`
Target source ID: `202332724`
Title: Homes Plus Limited (202332724)
URL: https://www.housing-ombudsman.org.uk/decisions/homes-plus-limited-202332724/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-28`
- Landlord: `Homes Plus Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `400.00`
- Draft region: `london` from `Homes Plus Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident reported a leak coming from the loft on 31 October 2023 causing mould to form on the ceiling. He reported the leak again on 14 November 2023 and told the landlord that he had mould all around his property. The resident complained to the landlord on 4 December 2023 that the issues he reported were not taken seriously and the damp in the property was worsening. The landlord’s response to the resident’s reports of: A leak from the roof including damaged loft insulation. Damp and mould. We have also investigated the landlord’s response to the resident’s complaint.

## Money Candidates

- score=16 amount=400.00 span={'page': 1, 'paragraph': 80, 'text_span': [2655, 2663]} context=ting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 08 January 2026 2 Compensation order The landlord must pay the resident £ 4 0 0 made up as follows: £100 offered in its stage 1 complaint response, Additional £ 1 00 for the likely inconvenience and frustration in its additional failures relating to th
- score=16 amount=100.00 span={'page': 1, 'paragraph': 83, 'text_span': [2683, 2688]} context=failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 08 January 2026 2 Compensation order The landlord must pay the resident £ 4 0 0 made up as follows: £100 offered in its stage 1 complaint response, Additional £ 1 00 for the likely inconvenience and frustration in its additional failures relating to the resident’s reports of a lea
- score=16 amount=100.00 span={'page': 1, 'paragraph': 86, 'text_span': [2742, 2749]} context=re: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 08 January 2026 2 Compensation order The landlord must pay the resident £ 4 0 0 made up as follows: £100 offered in its stage 1 complaint response, Additional £ 1 00 for the likely inconvenience and frustration in its additional failures relating to the resident’s reports of a leak from the roof. £ 150 for its failures in its response to
- score=12 amount=150.00 span={'page': 1, 'paragraph': 94, 'text_span': [2881, 2887]} context=dance . No later than 08 January 2026 2 Compensation order The landlord must pay the resident £ 4 0 0 made up as follows: £100 offered in its stage 1 complaint response, Additional £ 1 00 for the likely inconvenience and frustration in its additional failures relating to the resident’s reports of a leak from the roof. £ 150 for its failures in its response to the resident’s reports of damp and mould. £ 50 for its response to the resident’s complaint. This must be paid directly to the resident by
- score=5 amount=100.00 span={'page': 1, 'paragraph': 194, 'text_span': [10932, 10937]} context=l report of the leak as an emergency repair. The landlord acted appropriately regarding loft insulation. However, we identified an additional failure in responding to a further report of a leak in early February 2024. Therefore, we have found a service failure and ordered the landlord to pay the resident an additional £100 compensation, in line with our remedies guidance, to acknowledge the distress and inconvenience caused. Complaint The landlord’s response to the resident’s reports of d amp an
- score=3 amount=150.00 span={'page': 1, 'paragraph': 208, 'text_span': [13694, 13699]} context=hing its decisions. The landlord did not acknowledge its failures in handling the resident’s reports of damp and mould. Considering its failure to raise an initial inspection promptly and delays in raising identified works, we have made a finding of maladministration. We have ordered the landlord to award the resident £150 compensation. This recognises the landlord’s failure to follow its policy and acknowledges that, while there was no permanent impact on the resident, the delays caused inconve
- score=3 amount=50.00 span={'page': 1, 'paragraph': 224, 'text_span': [15566, 15570]} context=ppropriate of the landlord as it was outside its timescales in its policy of 20 working days. Taking into account the low impact the landlord’s complaint handling failure had on the resident, we have made a finding of service failure. In line with our remedies guidance, we have ordered the landlord to pay the resident £50 compensation. This reflects that these were minor failures by the landlord and had a likely low impact on the resident. Learning The landlord should ensure that all follow-on r
- score=1 amount=100.00 span={'page': 1, 'paragraph': 149, 'text_span': [4725, 4730]} context=ty. An appointment was made to remove the infected loft insulation and replace it. It had not carried out property inspections since prior to Covid-19, and this programme was under review. It acknowledged that an emergency appointment should have been raised after the initial report of a leak from the loft. It awarded £100 compensation as an apology for its service failure. 10 January 2024 The resident told the landlord he was unhappy with the resolution offered at stage 1. He was unhappy with t

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202332724.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/homes-plus-limited-202332724/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/11-housing-ombudsman-202332724.draft_decision.json`

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
