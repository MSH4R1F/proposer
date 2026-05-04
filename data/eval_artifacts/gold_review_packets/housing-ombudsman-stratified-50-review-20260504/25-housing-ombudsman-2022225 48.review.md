# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-2022225 48`
Source slug: `southern-housing-202222548`
Target source ID: `2022225 48`
Title: Southern Housing  (202222548)
URL: https://www.housing-ombudsman.org.uk/decisions/southern-housing-202222548/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-20`
- Landlord: `Southern Housing`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `650.00`
- Draft region: `london` from `Southern Housing (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident has lived in the property, a one-bedroom flat, since 2010. The property is on an estate which ha s road s with speed ramps . The landlord’s handling of the resident’s: Reports of a hazard. Associated formal complaint.

## Money Candidates

- score=11 amount=650.00 span={'page': 1, 'paragraph': 121, 'text_span': [2123, 2129]} context=a senior member of its leadership team. The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 18 December 2025 2 Compensation order The landlord must provide documentary evidence it has paid directly to the resident £ 650 compensation to recognise the distress and inconvenience caused by its failures, made up as follows: £500 for its response to his reports of a hazard (inclusive of the £125 pr
- score=11 amount=150.00 span={'page': 1, 'paragraph': 126, 'text_span': [2324, 2329]} context=December 2025 2 Compensation order The landlord must provide documentary evidence it has paid directly to the resident £ 650 compensation to recognise the distress and inconvenience caused by its failures, made up as follows: £500 for its response to his reports of a hazard (inclusive of the £125 previously offered) . £150 for its response to his formal complaint. No later than 18 December 2025 3 Case review The landlord must provide documentary evidence it has reviewed the complaint handling fa
- score=3 amount=500.00 span={'page': 1, 'paragraph': 123, 'text_span': [2230, 2235]} context=n , meaningful and empathetic. It has due regard to our apologies guidance . No later than 18 December 2025 2 Compensation order The landlord must provide documentary evidence it has paid directly to the resident £ 650 compensation to recognise the distress and inconvenience caused by its failures, made up as follows: £500 for its response to his reports of a hazard (inclusive of the £125 previously offered) . £150 for its response to his formal complaint. No later than 18 December 2025 3 Case r
- score=3 amount=150.00 span={'page': 1, 'paragraph': 472, 'text_span': [11463, 11468]} context=n extension with him. The landlord did not acknowledge the delays and failings in its complaint handling . It did not offer any explanations, apologies, or redress for this. We have , therefore, found maladministration in its handling of the complaint. It is ordered to write to the resident with an apology and pay him £150 compensation for the upset and inconvenience caused by its failures, in line with our remedies guidance. On 8 February 2024 we issued the statutory Complaint Handling Code (th
- score=3 amount=125.00 span={'page': 1, 'paragraph': 125, 'text_span': [2297, 2302]} context=uidance . No later than 18 December 2025 2 Compensation order The landlord must provide documentary evidence it has paid directly to the resident £ 650 compensation to recognise the distress and inconvenience caused by its failures, made up as follows: £500 for its response to his reports of a hazard (inclusive of the £125 previously offered) . £150 for its response to his formal complaint. No later than 18 December 2025 3 Case review The landlord must provide documentary evidence it has reviewe
- score=3 amount=125.00 span={'page': 1, 'paragraph': 218, 'text_span': [4362, 4367]} context=missed appointments and repair delays. It said it could not give timescales for planned repairs but would update on the progress. It had engaged new contractors due to challenges experienced with the previous one . It detailed an action plan. It upheld the complaint due to ‘sub-standard’ service and delays. It offered £125 compensation for inconvenience, time, and trouble. December 2024 The speed ramp was removed. Referral to the Ombudsman The resident was unhappy with the time taken to address
- score=3 amount=125.00 span={'page': 1, 'paragraph': 368, 'text_span': [8410, 8415]} context=his area that the speed ramp was placed . We have not seen evidence that the installation of the speed ramp was suitably risk assessed or that , once it was brought to the landlord’s attention, it did so then . We have found maladministration in the landlord’s handling of the resident’s reports of a hazard. It offered £125 compensation , saying its compensation policy did not allow for redress to be paid for communal repairs. However, this was not an appropriate position to take . The resident h
- score=-9 amount=500.00 span={'page': 1, 'paragraph': 393, 'text_span': [9183, 9190]} context=hope someone would act. He repeatedly faced a lack of updates and progress . U ltimately , the length of time it took to meaningfully address the issue was unreasonable and disproportionate to the risk posed. The landlord is ordered to write to the resident with a sincere apology for its failings. It is ordered to pay £ 50 0 compensation (inclusive of the £1 25 previously offered ) for the trouble, upset, and inconvenience caused by its failings. T his is in line with our remedies guidance, cons

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-2022225 48.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/southern-housing-202222548/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/25-housing-ombudsman-2022225 48.draft_decision.json`

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
