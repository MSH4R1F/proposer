# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202409957`
Source slug: `london-borough-of-islington-202409957`
Target source ID: `202409957`
Title: London Borough of Islington (202409957)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-islington-202409957/

## Manifest Strata

- Outcome raw: `severe maladministration; maladministration`
- Outcome normalized: `severe-maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-27`
- Landlord: `London Borough of Islington`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `2431.41`
- Draft region: `london` from `London Borough of Islington (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lived in a ground floor flat within a converted terraced house. In 2022 she reported that she could not open her windows because they had moved out of alignment. In 2023 the adjoining terraced house began extensive renovation works, which she believed caused movement in her flat. She also reported damp and mould during this period. She has since moved to a new property but says the landlord failed to handle these concerns properly. The complaint is about how the landlord handled: Reports of faulty windows. Concerns of subsidence. Reports of damp and mould. The associated complaint.

## Money Candidates

- score=20 amount=2431.41 span={'page': 1, 'paragraph': 95, 'text_span': [3449, 3460]} context=eport. The landlord must ensure: T he apology is provided by the chief executive officer . The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 06 January 2026 2 Compensation order The landlord must pay the resident £2, 4 31.41 made up as follows: £ 6 00 to reflect the distress and inconvenience caused in its handling of her window reports. £331.41 for the loss of amenity during the handling o
- score=20 amount=600.00 span={'page': 1, 'paragraph': 99, 'text_span': [3481, 3488]} context=T he apology is provided by the chief executive officer . The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 06 January 2026 2 Compensation order The landlord must pay the resident £2, 4 31.41 made up as follows: £ 6 00 to reflect the distress and inconvenience caused in its handling of her window reports. £331.41 for the loss of amenity during the handling of her subsidence concerns , calcu
- score=20 amount=331.41 span={'page': 1, 'paragraph': 102, 'text_span': [3576, 3583]} context=res identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 06 January 2026 2 Compensation order The landlord must pay the resident £2, 4 31.41 made up as follows: £ 6 00 to reflect the distress and inconvenience caused in its handling of her window reports. £331.41 for the loss of amenity during the handling of her subsidence concerns , calculated at 15% of the weekly rent over a 4-month period. £1,000 for distress and inconvenience a
- score=11 amount=1000.00 span={'page': 1, 'paragraph': 107, 'text_span': [3717, 3724]} context=mpensation order The landlord must pay the resident £2, 4 31.41 made up as follows: £ 6 00 to reflect the distress and inconvenience caused in its handling of her window reports. £331.41 for the loss of amenity during the handling of her subsidence concerns , calculated at 15% of the weekly rent over a 4-month period. £1,000 for distress and inconvenience arising from the seriousness of the failings identified in its handling of her subsidence concerns. £300 for the distress and inconvenience ca
- score=5 amount=925.00 span={'page': 1, 'paragraph': 303, 'text_span': [18304, 18308]} context=unication up to November 2024 was not a reasonable response in the circumstances. Finally, the landlord offered the resident £875 for the distress and inconvenience caused in the handling of the issues raised in her complaint, and a further £50 for the delay in processing her transfer form, bringing its total offer to £925. Of this, £100 related to the additional cost of heating her home and has already been discounted in our window assessment, and £25 related to complaint-handling delays, which
- score=5 amount=300.00 span={'page': 1, 'paragraph': 315, 'text_span': [22243, 22248]} context=that by this stage the landlord was in the process of rehousing the resident, this did not remove its responsibility to assess the impact on her living conditions and, where appropriate, offer redress for any failings identified. However, it did not do this. In line with the Ombudsman’s Remedies Guidance, we consider £300 to be appropriate compensation for the distress and inconvenience caused by the landlord’s failure to investigate the resident’s damp and mould reports over the 5-month period
- score=5 amount=100.00 span={'page': 1, 'paragraph': 303, 'text_span': [18319, 18324]} context=November 2024 was not a reasonable response in the circumstances. Finally, the landlord offered the resident £875 for the distress and inconvenience caused in the handling of the issues raised in her complaint, and a further £50 for the delay in processing her transfer form, bringing its total offer to £925. Of this, £100 related to the additional cost of heating her home and has already been discounted in our window assessment, and £25 related to complaint-handling delays, which has also been c
- score=5 amount=50.00 span={'page': 1, 'paragraph': 259, 'text_span': [8083, 8087]} context=se about its handling of the resident’s transfer application. It said: Her property was unsafe, and she needed to be rehoused. It had received the required documents and apologised for the delay in sending them to the correct department. It upheld her complaint due to poor communication and delays. It was awarding her £50 compensation for the distress and inconvenience caused. Referral to the Ombudsman The resident asked us to investigate because she remained dissatisfied with the condition of h

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202409957.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-islington-202409957/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/47-housing-ombudsman-202409957.draft_decision.json`

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
