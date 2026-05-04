# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202348669`
Source slug: `london-quadrant-housing-trust-202348669`
Target source ID: `202348669`
Title: London & Quadrant Housing Trust   (202348669)
URL: https://www.housing-ombudsman.org.uk/decisions/london-quadrant-housing-trust-202348669/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-10-27`
- Landlord: `London & Quadrant Housing Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1010.00`
- Draft region: `london` from `London & Quadrant Housing Trust (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident live d in a 2-bedroom flat with he r 2 children . She complained that there was a mice infestation and droppings in the property and disrepair was contributing to this. She also complained as she was unhappy with plaster ing and decorating in the property following leaks . The resident reported to the landlord that she and her children ha d vulnerabilities. They moved to another property in September 2025. The complaint is about the landlord’s response to the resident’s : reports of a mice infestation and related repairs . concerns about plastering and decorating. We have also investigated the landlord’s complaint handling.

## Money Candidates

- score=20 amount=1010.00 span={'page': 1, 'paragraph': 159, 'text_span': [3447, 3457]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 24 November 2025 2 Compensation order The landlord must pay the resident £ 1, 01 0 made up as follows: £ 8 0 0 for the distress and inconvenience caused by its response to the resident’s reports that there was a mice infestation. £ 5 0 for the distress
- score=20 amount=800.00 span={'page': 1, 'paragraph': 163, 'text_span': [3477, 3485]} context=ilures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 24 November 2025 2 Compensation order The landlord must pay the resident £ 1, 01 0 made up as follows: £ 8 0 0 for the distress and inconvenience caused by its response to the resident’s reports that there was a mice infestation. £ 5 0 for the distress and in and inconvenience cause
- score=20 amount=50.00 span={'page': 1, 'paragraph': 167, 'text_span': [3604, 3610]} context=, meaningful and empathetic. It has due regard to our apologies guidance . No later than 24 November 2025 2 Compensation order The landlord must pay the resident £ 1, 01 0 made up as follows: £ 8 0 0 for the distress and inconvenience caused by its response to the resident’s reports that there was a mice infestation. £ 5 0 for the distress and in and inconvenience caused by its response to the resident’s dissatisfaction with its plastering and decorating. £1 60 for the distress and inconvenience
- score=7 amount=160.00 span={'page': 1, 'paragraph': 173, 'text_span': [3745, 3751]} context=must pay the resident £ 1, 01 0 made up as follows: £ 8 0 0 for the distress and inconvenience caused by its response to the resident’s reports that there was a mice infestation. £ 5 0 for the distress and in and inconvenience caused by its response to the resident’s dissatisfaction with its plastering and decorating. £1 60 for the distress and inconvenience caused by its complaint handling. This must be paid directly to the resident by the due date. The landlord must provide documentary evidenc
- score=3 amount=80.00 span={'page': 1, 'paragraph': 324, 'text_span': [7928, 7932]} context=ofed individually. contractors would arrange an appointment to proof the property. a kitchen replacement was on a planned works programme . It could not confirm when th is would be completed. t he resident could update her household’s vulnerabilities online . it could not compensate for the impact of pests. It offered £80 compensation for the inconvenience caused. it was only responsible for repairing the patch of plaster affected. It said the resident could call its contact centre if she was un
- score=1 amount=180.00 span={'page': 1, 'paragraph': 301, 'text_span': [7200, 7205]} context=ay 2024 The landlord raised works to proof holes in the bathroom and kitchen. 31 May 2024 The landlord issued an updated stage 1 response and said: its contractors would contact the resident that day to arrange an appointment to proof the holes in the property urgently. it apologised for a delay in repairs and offered £180 compensation for distress, inconvenience, time and effort. 9 July 2024 The landlord issued a stage 2 response and said: it apologised for the delay in its stage 2 response and
- score=1 amount=60.00 span={'page': 1, 'paragraph': 304, 'text_span': [7389, 7393]} context=t that day to arrange an appointment to proof the holes in the property urgently. it apologised for a delay in repairs and offered £180 compensation for distress, inconvenience, time and effort. 9 July 2024 The landlord issued a stage 2 response and said: it apologised for the delay in its stage 2 response and offered £60 compensation for this. the reason it did not complete proofing until there were no mice in the property was to avoid trapping them in the property. the infestation was a block

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202348669.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-quadrant-housing-trust-202348669/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/17-housing-ombudsman-202348669.draft_decision.json`

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
