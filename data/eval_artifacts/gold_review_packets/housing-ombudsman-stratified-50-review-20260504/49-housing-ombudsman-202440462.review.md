# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202440462`
Source slug: `london-borough-of-lambeth-202440462`
Target source ID: `202440462`
Title: London Borough of Lambeth (202440462)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-lambeth-202440462/

## Manifest Strata

- Outcome raw: `severe maladministration; no maladministration; maladministration; outside jurisdiction`
- Outcome normalized: `severe-maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-12-08`
- Landlord: `London Borough of Lambeth`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1900.00`
- Draft region: `london` from `London Borough of Lambeth (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives in a flat on the fifth floor of a block with her children, one of whom is very young. The resident and 2 of her children are vulnerable and have health conditions. When she moved into the property it was a new build within a defects period. She complained to the landlord about various repairs, the suitability of the property, and its handling of other matters. She also made a later complaint about its handling of electrical repairs in her kitchen. The complaint is about the landlord’s handling of: Repairs to the balcony doors, windows, lift, and electrics in the kitchen. Reports of antisocial behaviour (ASB) and thefts. The death of a neighbour. Rent arrears. The...

## Money Candidates

- score=20 amount=1900.00 span={'page': 1, 'paragraph': 108, 'text_span': [3841, 3850]} context=in this report. The landlord must ensure: T he apology is provided by the chief executive. The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 13 January 2026 2 Compensation order The landlord must pay the resident £ 1 ,900 made up as follows: £ 1,500 for the substantial distress, worry, inconvenience, time and trouble caused for the resident over a number of years by its severe maladministra
- score=20 amount=1500.00 span={'page': 1, 'paragraph': 113, 'text_span': [3870, 3878]} context=must ensure: T he apology is provided by the chief executive. The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 13 January 2026 2 Compensation order The landlord must pay the resident £ 1 ,900 made up as follows: £ 1,500 for the substantial distress, worry, inconvenience, time and trouble caused for the resident over a number of years by its severe maladministration. £ 100 for the distress
- score=20 amount=100.00 span={'page': 1, 'paragraph': 120, 'text_span': [4027, 4033]} context=. It has due regard to our apologies guidance . No later than 13 January 2026 2 Compensation order The landlord must pay the resident £ 1 ,900 made up as follows: £ 1,500 for the substantial distress, worry, inconvenience, time and trouble caused for the resident over a number of years by its severe maladministration. £ 100 for the distress and inconvenience caused by its failings in handling reports of ASB. £ 200 for the distress and inconvenience caused by its failings in handling her rent arr
- score=11 amount=200.00 span={'page': 1, 'paragraph': 123, 'text_span': [4119, 4125]} context=order The landlord must pay the resident £ 1 ,900 made up as follows: £ 1,500 for the substantial distress, worry, inconvenience, time and trouble caused for the resident over a number of years by its severe maladministration. £ 100 for the distress and inconvenience caused by its failings in handling reports of ASB. £ 200 for the distress and inconvenience caused by its failings in handling her rent arrears. £ 100 for the additional time and trouble caused by its complaint handling failings. Th
- score=5 amount=200.00 span={'page': 1, 'paragraph': 447, 'text_span': [23254, 23259]} context=icated with her or reassured her that she would not lose her home. It would have been reasonable to have proactively done this, regardless of whether the initial error was its or the council ’ s. There was maladministration. To reflect the distress and inconvenience caused, an order has been made that the landlord pay £200 compensation to her. Complaint The landlord’s handling of t he suitability of the property. Finding Outside jurisdiction We can only investigate complaints about councils wher
- score=5 amount=100.00 span={'page': 1, 'paragraph': 399, 'text_span': [19474, 19481]} context=e landlord has followed its ASB policy, and with the problem ongoing, there was maladministration. This has caused the resident to be fearful of the communal areas especially as she ha s young children. It ha s also caused distress and inconvenience. To reflect the impact, an order ha s been made that the landlord pay £1 0 0 compensation to her. Complaint The landlord’s handling of t he death of a neighbour. Finding No maladministration The resident suspected that her elderly neighbour had died,
- score=5 amount=100.00 span={'page': 1, 'paragraph': 488, 'text_span': [26768, 26773]} context=The landlord did not follow its complaints policy, did not retain or provide evidence and could not show it acknowledged either complaint or escalation request. Both its stage 2 responses were delayed, and it failed to recognise this. To reflect the additional time and trouble caused an order has been made that it pay £100 compensation to the resident. Learning There is evidence that the landlord has not followed its policies or that it had approached its repairing and other obligations with a l
- score=3 amount=23000.00 span={'page': 1, 'paragraph': 183, 'text_span': [6760, 6768]} context=windows could be opened by her children and were not safe. ASB in the communal areas caused by youths and parcels having been stolen. Not having received an apology or compensation for the time the lift was broken. The landlord’s slow response when a neighbour died and the impact this had on her mental health. Having £23,000 worth o f arrears added to her rent account when she was in receipt of benefits to pay her rent. Having raised complaints previously b ut the landlord not responding. 27 Dec

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202440462.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-lambeth-202440462/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/49-housing-ombudsman-202440462.draft_decision.json`

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
