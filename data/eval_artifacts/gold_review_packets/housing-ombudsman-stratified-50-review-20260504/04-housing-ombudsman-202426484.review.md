# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202426484`
Source slug: `london-borough-of-ealing-202426484`
Target source ID: `202426484`
Title: London Borough of Ealing (202426484)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-ealing-202426484/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-10-31`
- Landlord: `London Borough of Ealing`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `500.00`
- Draft region: `london` from `London Borough of Ealing (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident has been the leaseholder of the property since November 2023. The property is a 3-bedroom, ground and first floor maisonette. Between February 2022 and November 2023, the property’s previous owner made multiple reports of a leak from the flat above. From November 2023 the resident started to report to the landlord that the leak occurred whenever it rained. From February to July 2024 the landlord carried out some repairs, but these did not resolve the leak. The complaint is about the landlord’s response to: A leak in the resident’s home and the subsequent damp. The associated complaint.

## Money Candidates

- score=18 amount=500.00 span={'page': 1, 'paragraph': 81, 'text_span': [2785, 2791]} context=the landlord’s management team . The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 28 November 2025 2 Compensation order If it has not already done so, the landlord must pay the resident the total compensation of £ 500 offered through its complaints process and the letter of 12 September 2025 . It must also pay an additional £100 for its failure to inspect and treat the damp and mould. This
- score=18 amount=100.00 span={'page': 1, 'paragraph': 86, 'text_span': [2899, 2904]} context=and empathetic. It has due regard to our apologies guidance . No later than 28 November 2025 2 Compensation order If it has not already done so, the landlord must pay the resident the total compensation of £ 500 offered through its complaints process and the letter of 12 September 2025 . It must also pay an additional £100 for its failure to inspect and treat the damp and mould. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment
- score=3 amount=450.00 span={'page': 1, 'paragraph': 252, 'text_span': [17903, 17907]} context=bedroom whenever it rains. In view of this, a finding of maladministration has been found. We have ordered the landlord to apologise for the failings identified in this report and pay an additional £100 for its failure to inspect and treat the damp and mould. This brings the compensation for this head of complaint to £450. This sum is in-line with the Ombudsman’s published remedies guidance for complaints where the landlord acknowledged failings and made some attempt to put things right, but the
- score=3 amount=300.00 span={'page': 1, 'paragraph': 249, 'text_span': [16241, 16246]} context=by deteriorated pipes between her property and the 1 above. It confirmed the works to fix this would start ‘imminently’ and would be overseen to ensure they were progressed in a timely manner. It also said it would make sure the resident was regularly updated. As part of this review the landlord offered an additional £300 compensation. It did not provide a breakdown for this additional compensation, therefore the Ombudsman is of the understanding that £150 of this was for its response to the lea
- score=3 amount=200.00 span={'page': 1, 'paragraph': 206, 'text_span': [6875, 6880]} context=en they attended. The landlord apologised for this but explained that surveyors needed to discuss issues with the contractor before sharing information with the resident. It said this was to avoid providing any potential misinformation. In recognition of its service failure and the distress caused the landlord offered £200 compensation. 25 February 2025 The resident confirmed that she wanted this Service to investigate the complaint. She said the leak had been ongoing since November 2023 despite
- score=3 amount=150.00 span={'page': 1, 'paragraph': 249, 'text_span': [16378, 16383]} context=rseen to ensure they were progressed in a timely manner. It also said it would make sure the resident was regularly updated. As part of this review the landlord offered an additional £300 compensation. It did not provide a breakdown for this additional compensation, therefore the Ombudsman is of the understanding that £150 of this was for its response to the leak and the other £150 was for its complaint handling. The Ombudsman may make a determination of reasonable redress where a landlord has o
- score=3 amount=150.00 span={'page': 1, 'paragraph': 249, 'text_span': [16438, 16443]} context=also said it would make sure the resident was regularly updated. As part of this review the landlord offered an additional £300 compensation. It did not provide a breakdown for this additional compensation, therefore the Ombudsman is of the understanding that £150 of this was for its response to the leak and the other £150 was for its complaint handling. The Ombudsman may make a determination of reasonable redress where a landlord has offered compensation that provides redress for failures and s
- score=3 amount=150.00 span={'page': 1, 'paragraph': 260, 'text_span': [20646, 20651]} context=age 2 response within its policy timescales. It also acknowledged it had not addressed the delays in the complaint response. As part of this review the landlord offered an additional £300 compensation. It did not provide a breakdown for this additional compensation, therefore the Ombudsman is of the understanding that £150 of this was for the complaint handling failures. The landlord also said it had provided additional training to staff on managing complaints and recruited specialist staff for

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202426484.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-ealing-202426484/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/04-housing-ombudsman-202426484.draft_decision.json`

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
