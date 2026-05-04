# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202410423`
Source slug: `clarion-housing-association-limited-202410423`
Target source ID: `202410423`
Title: Clarion Housing Association Limited (202410423)
URL: https://www.housing-ombudsman.org.uk/decisions/clarion-housing-association-limited-202410423/

## Manifest Strata

- Outcome raw: `maladministration; reasonable redress`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-28`
- Landlord: `Clarion Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `100.00`
- Draft region: `london` from `Clarion Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives in a one-bedroom ground floor flat and pays a variable service charge. She told us she has difficulty with her memory. She raised concerns that the service charges were unclear, some services were not being provided, and the landlord did not properly monitor their quality or frequency. She asked us to investigate how the landlord responded to these concerns. The complaint is about: The landlord’s response to the resident’s concerns about her service charges. How the landlord responded to the complaint.

## Money Candidates

- score=24 amount=100.00 span={'page': 1, 'paragraph': 67, 'text_span': [2555, 2562]} context=rd must ensure: The apology is provided by a senior member of the complaint handling team. The apology is specific to the failures identified in this decision, meaningful and empathetic. It has due regard to our apologies guidance . No later than 25 November 2025 2 Compensation order The landlord must pay the resident £ 1 00 to recognise the distress and inconvenience caused by its complaint handling. This must be paid directly to the resident by the due date. The landlord must provide documenta
- score=5 amount=100.00 span={'page': 1, 'paragraph': 132, 'text_span': [4583, 4588]} context=3 The landlord issued its stage 1 response. It confirmed the charges for the TV aerial and door entry system had been removed and had written to the resident to explain this on 26 May 2023. It said it had delayed in responding to her initial query because of a backlog. It apologised for its error and delay and offered £100 compensation to recognise this. 14 June 2023 The resident escalated her complaint because she had not received a breakdown of her service charges that she had requested in 202
- score=1 amount=100.00 span={'page': 1, 'paragraph': 158, 'text_span': [5437, 5442]} context=ice charges were applied correctly, with no evidence of contractor fault for the fire system. It clarified that some services were not included in the resident’s charges and cyclical works were planned for between the 2025 to 20 26 financial year . The landlord acknowledged a delay in responding at stage 2 and awarded £100 compensation. Referral to the Ombudsman The resident told us she still had concerns because: She thought some s ervice charges had been introduced without consultation. She wa

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202410423.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/clarion-housing-association-limited-202410423/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/18-housing-ombudsman-202410423.draft_decision.json`

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
