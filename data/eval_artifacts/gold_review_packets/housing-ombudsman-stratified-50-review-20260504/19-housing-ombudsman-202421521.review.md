# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202421521`
Source slug: `london-quadrant-housing-trust-202421521`
Target source ID: `202421521`
Title: London & Quadrant Housing Trust   (202421521)
URL: https://www.housing-ombudsman.org.uk/decisions/london-quadrant-housing-trust-202421521/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-30`
- Landlord: `London & Quadrant Housing Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `540.00`
- Draft region: `london` from `London & Quadrant Housing Trust (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives in a block of flats and has use of a purpose-built shed. Earlier in the year, the resident reported that the shed door had been hanging off and plywood had been stolen. He complained then the landlord fitted a new lock, it gave the key to a neighbour. At the time of the complaint the neighbour had given the resident the key, however he did not want to go into the shed without the landlord being present. The resident asked us to investigate as he was not satisfied with the landlord’s final response. The resident advised us he has memory dyslexia. The complaint is about: The landlord giving the shed key to another resident. How the landlord r espon ded to reports that...

## Money Candidates

- score=24 amount=540.00 span={'page': 1, 'paragraph': 82, 'text_span': [2762, 2767]} context=st comply with our orders in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order Inclusive of the landlord’s previous compensation award, t he landlord must pay the resident £ 540. This comprises: £ 34 0 to recognise the distress and incon veni ence caused by the maladministration in the landlord giving the shed key to another resident . £200 to recogn
- score=24 amount=340.00 span={'page': 1, 'paragraph': 83, 'text_span': [2785, 2792]} context=rs in the manner and timescales we specify. The landlord must provide documentary evidence of compliance with our orders by the due date set. Order What the landlord must do Due date 1 Compensation order Inclusive of the landlord’s previous compensation award, t he landlord must pay the resident £ 540. This comprises: £ 34 0 to recognise the distress and incon veni ence caused by the maladministration in the landlord giving the shed key to another resident . £200 to recognise the distress and in
- score=24 amount=200.00 span={'page': 1, 'paragraph': 91, 'text_span': [2928, 2933]} context=rder What the landlord must do Due date 1 Compensation order Inclusive of the landlord’s previous compensation award, t he landlord must pay the resident £ 540. This comprises: £ 34 0 to recognise the distress and incon veni ence caused by the maladministration in the landlord giving the shed key to another resident . £200 to recognise the distress and inconvenience caused by the service failure in the landlord’s complaint handling. This must be paid directly to the resident by the due date. The
- score=3 amount=340.00 span={'page': 1, 'paragraph': 192, 'text_span': [12673, 12677]} context=ndlord giving the shed key to another resident . The landlord awarded £140 for the resident’s time, effort, distress, and inconvenience. It advised it added clearer notes to prevent a recurrence. Due to the further failings we have identified, we have increased the compensation by a further £200, bringing the total to £340. We note the resident would like the landlord to move him. We have discussed this with the resident and confirmed this is not a remedy we can make. In addition, the resident h
- score=3 amount=200.00 span={'page': 1, 'paragraph': 192, 'text_span': [12645, 12651]} context=maladministration in the landlord giving the shed key to another resident . The landlord awarded £140 for the resident’s time, effort, distress, and inconvenience. It advised it added clearer notes to prevent a recurrence. Due to the further failings we have identified, we have increased the compensation by a further £200, bringing the total to £340. We note the resident would like the landlord to move him. We have discussed this with the resident and confirmed this is not a remedy we can make.
- score=3 amount=140.00 span={'page': 1, 'paragraph': 191, 'text_span': [12423, 12428]} context=ectly contacted the neighbour causing unnecessary tension between them. Therefore, the landlord made some attempt to put things right, but it failed to fully address the detriment to the resident. As such we find there was maladministration in the landlord giving the shed key to another resident . The landlord awarded £140 for the resident’s time, effort, distress, and inconvenience. It advised it added clearer notes to prevent a recurrence. Due to the further failings we have identified, we hav
- score=3 amount=120.00 span={'page': 1, 'paragraph': 135, 'text_span': [6098, 6103]} context=neighbour this. He had been waiting for it to contact him to give him the key. It told the resident it would speak with the neighbour, however before this happened, he had already approached them. After this it spoke with the neighbour which is when they gave the key to the resident. It awarded the resident a total of £120 for its failings. £40 for the resident’s distress, £40 for inconvenience and £40 for its late response. 27 July 2024 The resident asked to escalate his complaint. He did not a
- score=3 amount=40.00 span={'page': 1, 'paragraph': 135, 'text_span': [6121, 6125]} context=been waiting for it to contact him to give him the key. It told the resident it would speak with the neighbour, however before this happened, he had already approached them. After this it spoke with the neighbour which is when they gave the key to the resident. It awarded the resident a total of £120 for its failings. £40 for the resident’s distress, £40 for inconvenience and £40 for its late response. 27 July 2024 The resident asked to escalate his complaint. He did not agree with some findings

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202421521.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-quadrant-housing-trust-202421521/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/19-housing-ombudsman-202421521.draft_decision.json`

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
