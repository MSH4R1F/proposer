# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202513245`
Source slug: `stonewater-limited-202513245`
Target source ID: `202513245`
Title: Stonewater Limited (202513245)
URL: https://www.housing-ombudsman.org.uk/decisions/stonewater-limited-202513245/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2026-01-27`
- Landlord: `Stonewater Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `550.00`
- Draft region: `london` from `Stonewater Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a flat with their young child. At the time the landlord was investigating this complaint, the resident was pregnant. The landlord’s handling of damp and mould in the property. We have also considered the landlord’s complaints handling.

## Money Candidates

- score=22 amount=550.00 span={'page': 1, 'paragraph': 59, 'text_span': [1889, 1895]} context=l other cases within our jurisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 550 made up as follows: £ 500 to recognise the distress and concern associated with the ongoing damp and mould issues. £ 50 to recognise the inconvenience associated with the lan
- score=22 amount=500.00 span={'page': 1, 'paragraph': 61, 'text_span': [1915, 1921]} context=urisdiction. Orders Landlords must comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 550 made up as follows: £ 500 to recognise the distress and concern associated with the ongoing damp and mould issues. £ 50 to recognise the inconvenience associated with the landlord’s complaints handlin
- score=22 amount=50.00 span={'page': 1, 'paragraph': 65, 'text_span': [2010, 2015]} context=fy. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order The landlord must pay the resident £ 550 made up as follows: £ 500 to recognise the distress and concern associated with the ongoing damp and mould issues. £ 50 to recognise the inconvenience associated with the landlord’s complaints handling. This must be paid directly to the resident by the due date. The landlord must provide docume
- score=5 amount=350.00 span={'page': 1, 'paragraph': 307, 'text_span': [16154, 16159]} context=f planned repairs which is shared with the resident. If the landlord determines that it is unable to complete the planned works in line with its repairs policy timescales, it must provide the resident with a plan for temporary rehousing while the works are ongoing. During the complaints procedure, the landlord offered £350 to address distress and inconvenience, with the remaining compensation relating to missed appointments and communication issues. The £350 was appropriate when considering the
- score=3 amount=475.00 span={'page': 1, 'paragraph': 136, 'text_span': [4141, 4146]} context=a landlord may decide not to follow them. Our recommendations The landlord should request details from the resident of the items which have been damaged by damp and mould. The landlord should then outline its position on compensating the resident or replacing the damaged items or refer the matter to its insurers . The £475 in compensation the landlord committed to in its internal complaints procedure should be paid to the resident if it has not yet paid this amount. Our investigation The complai
- score=3 amount=475.00 span={'page': 1, 'paragraph': 247, 'text_span': [7129, 7133]} context=e reasonable adjustments when scheduling repairs, and £200 for the resident’s inconvenience, time and trouble The landlord said it could not factor in any personal injury concerns, and the resident should seek legal advice if they wished to pursue a claim. This brought the total compensation offered by the landlord to £475. 1 August 2025 The resident contacted us again and said they were extremely stressed as the y felt the landlord was not helping them . They said the stress was impacting their
- score=3 amount=475.00 span={'page': 1, 'paragraph': 300, 'text_span': [14592, 14597]} context=there could be other factors contributing to the situation, it would be appropriate for the landlord to carry out a further inspection. To address this, we have ordered the landlord to carry out an inspection that considers possible structural factors. During the complaints process, the landlord apologised and offered £475 compensation. This was positive and showed it recognised the impact on the resident. However, as the damp and mould issue remains unresolved, we cannot conclude the landlord h
- score=3 amount=350.00 span={'page': 1, 'paragraph': 307, 'text_span': [16292, 16297]} context=th its repairs policy timescales, it must provide the resident with a plan for temporary rehousing while the works are ongoing. During the complaints procedure, the landlord offered £350 to address distress and inconvenience, with the remaining compensation relating to missed appointments and communication issues. The £350 was appropriate when considering the period covered by the landlord’s complaints process. However, as the issues remain unresolved, we consider this amount to no longer be app

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202513245.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/stonewater-limited-202513245/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/16-housing-ombudsman-202513245.draft_decision.json`

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
