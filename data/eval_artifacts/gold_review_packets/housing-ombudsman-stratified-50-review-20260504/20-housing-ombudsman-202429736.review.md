# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202429736`
Source slug: `trident-housing-association-limited-202429736`
Target source ID: `202429736`
Title: Trident Housing Association Limited (202429736)
URL: https://www.housing-ombudsman.org.uk/decisions/trident-housing-association-limited-202429736/

## Manifest Strata

- Outcome raw: `maladministration; service failure; outside jurisdiction`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-04`
- Landlord: `Trident Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `350.00`
- Draft region: `london` from `Trident Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident and her partner live in a 2-bedroom ground floor flat in a high-rise building. In February 2024 the landlord sent the resident notice of her new rent and service charges for the upcoming year. She queried the new charges in March 2024. The complaint is about the landlord’s response to the resident’s: Service charge queries. Reports of anti-social behaviour (ASB). Associated complaint.

## Money Candidates

- score=24 amount=350.00 span={'page': 1, 'paragraph': 82, 'text_span': [2650, 2655]} context=s report. The landlord must ensure: T he apology is provided by a senior member of staff. The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 03 December 2025 2 Compensation order The landlord must pay the resident £350 made up as follows: £300 to recognise the distress and inconvenience caused by its handling of the service charge queries. £50 for the time and trouble likely caused by its ha
- score=24 amount=300.00 span={'page': 1, 'paragraph': 82, 'text_span': [2675, 2680]} context=st ensure: T he apology is provided by a senior member of staff. The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 03 December 2025 2 Compensation order The landlord must pay the resident £350 made up as follows: £300 to recognise the distress and inconvenience caused by its handling of the service charge queries. £50 for the time and trouble likely caused by its handling of the complaint.
- score=22 amount=50.00 span={'page': 1, 'paragraph': 83, 'text_span': [2778, 2782]} context=s identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 03 December 2025 2 Compensation order The landlord must pay the resident £350 made up as follows: £300 to recognise the distress and inconvenience caused by its handling of the service charge queries. £50 for the time and trouble likely caused by its handling of the complaint. This must be paid directly to the resident by the due date. The landlord must provide documentary evide
- score=5 amount=300.00 span={'page': 1, 'paragraph': 219, 'text_span': [13375, 13380]} context=not only did it fail to uphold its commitments , but it also failed to evidence that it ensured the heating system was working as intended. As a result of the failings identified, we have found maladministration in the landlord’s handling of the resident’s service charge queries. We have ordered it to pay the resident £300 compensation for the distress and inconvenience likely caused. This is in line with our remedies guidance for situations where there were failures which adversely affected the
- score=0 amount=1799.68 span={'page': 1, 'paragraph': 209, 'text_span': [9284, 9293]} context=wed at least once a year and the landlord must give the resident at least 4 weeks’ notice of any change. The landlord confirmed the charges were variable. The weekly charge increased from £39.86 to £82.27. The letter included a cost breakdown with a line entitled “2022/23 (surplus)/deficit carried forward” which added £1,799.68. This approach was consistent with the tenancy agreement which allows the landlord to carry forward deficits when calculating charges. However, the letter did not provide
- score=0 amount=82.27 span={'page': 1, 'paragraph': 209, 'text_span': [9162, 9168]} context=firming her service charges from 1 April 2024. This was in line with the tenancy agreement which says charges may be reviewed at least once a year and the landlord must give the resident at least 4 weeks’ notice of any change. The landlord confirmed the charges were variable. The weekly charge increased from £39.86 to £82.27. The letter included a cost breakdown with a line entitled “2022/23 (surplus)/deficit carried forward” which added £1,799.68. This approach was consistent with the tenancy a
- score=0 amount=50.00 span={'page': 1, 'paragraph': 237, 'text_span': [16983, 16986]} context=not confirm whether the resident asked for any points to be included that were not reflected in the response. The landlord unreasonably delaying registering complaints about the issues raised and failure to provide reasons for rejecting them amounted to service failure. We have ordered the landlord to pay the resident £50. This amount is within the range of awards set out in our remedies guidance for situations where there was a failing by the landlord which may not have significantly affected t
- score=0 amount=39.86 span={'page': 1, 'paragraph': 209, 'text_span': [9152, 9158]} context=y 2024 confirming her service charges from 1 April 2024. This was in line with the tenancy agreement which says charges may be reviewed at least once a year and the landlord must give the resident at least 4 weeks’ notice of any change. The landlord confirmed the charges were variable. The weekly charge increased from £39.86 to £82.27. The letter included a cost breakdown with a line entitled “2022/23 (surplus)/deficit carried forward” which added £1,799.68. This approach was consistent with the

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202429736.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/trident-housing-association-limited-202429736/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/20-housing-ombudsman-202429736.draft_decision.json`

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
