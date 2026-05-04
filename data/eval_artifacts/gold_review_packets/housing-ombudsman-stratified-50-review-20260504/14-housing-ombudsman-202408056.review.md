# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202408056`
Source slug: `orbit-housing-association-limited-202408056`
Target source ID: `202408056`
Title: Orbit Housing Association Limited (202408056)
URL: https://www.housing-ombudsman.org.uk/decisions/orbit-housing-association-limited-202408056/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-12-17`
- Landlord: `Orbit Housing Association Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1440.00`
- Draft region: `london` from `Orbit Housing Association Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The property was newly built when the resident moved in and there was no radiator installed in the hallway. She is unhappy the landlord refused to install one despite her reporting that the hallway was cold and damp. The landlord’s handling of the resident’s request for it to install a radiator in the hallway. We have also investigated the landlord’s handling of the resident’s complaint.

## Money Candidates

- score=14 amount=1440.00 span={'page': 1, 'paragraph': 97, 'text_span': [2464, 2472]} context=fied in this report. The landlord must ensure: t he apology is provided by a senior manager t he apology is specific to the failures identified in this decision , meaningful and empathetic i t has due regard to our apologies guidance No later than 14 January 2026 2 Compensation order The landlord must pay the resident £ 1,440 offered in its letter of 12 February 2025. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment by the due
- score=7 amount=1000.00 span={'page': 1, 'paragraph': 211, 'text_span': [8432, 8439]} context=lling this as a goodwill gesture, and that it was not a requirement. It failed to recognise that it had disregarded 2 professionals ’ opinions during its complaint investigation, and did not apologise for this, which was not appropriate. The landlord did not make it clear in this letter what the compensation amount of £1,000 was for. It has recently explained to us that this was to recognise the time, trouble and inconvenience caused to the resident by its delay in installing the radiator and th
- score=5 amount=1140.00 span={'page': 1, 'paragraph': 212, 'text_span': [8682, 8689]} context=did not make it clear in this letter what the compensation amount of £1,000 was for. It has recently explained to us that this was to recognise the time, trouble and inconvenience caused to the resident by its delay in installing the radiator and the effort she had to go to for this to be resolved. Its total offer of £1,140 in relation to the radiator and damp and mould issues was reasonable, and in line with our remedies guidance. This offer does not prevent a finding of maladministration as it
- score=5 amount=300.00 span={'page': 1, 'paragraph': 232, 'text_span': [10388, 10393]} context=cale of 5 working days it sent its stage 2 response 48 working days after the complaint should have been escalated (29 May to 5 August 2024) – which was not in line with its policy timescale of 20 working days The landlord’s letter of 12 February 2025 recognised its complaint handling failures and offered the resident £300 compensation to recognise this. As explained above, it was not appropriate that this was not awarded until 6 months after it sent its stage 2 response. However, t his amount w
- score=5 amount=175.00 span={'page': 1, 'paragraph': 119, 'text_span': [3494, 3499]} context=vestigate the complaint. 23 May 2024 The landlord sent its stage 1 response, in which it said: it conducted a damp and mould inspection in April 2024 and completed work that was identified the resident told it that works had not resolved the damp and mould and it had raised new repairs on a 28-day timescale it offered £175 compensation to recognise that not all required works were identified first time 29 May 2024 The resident told the landlord she was not happy with its response. She questioned
- score=3 amount=1440.00 span={'page': 1, 'paragraph': 144, 'text_span': [4631, 4639]} context=lord’s response. She said it had carried out a survey which recommended heating be installed in the hallway and she wanted this to be done. 12 February 2025 The landlord wrote to the resident and said that as a goodwill gesture it would be installing a radiator in the hallway. It increased its offer of compensation to £1,440, broken down as follows: £140 for lost services in line with its service level agreements £1,000 for time, trouble and inconvenience £300 for poor complaint handling What we
- score=3 amount=1000.00 span={'page': 1, 'paragraph': 146, 'text_span': [4728, 4735]} context=he hallway and she wanted this to be done. 12 February 2025 The landlord wrote to the resident and said that as a goodwill gesture it would be installing a radiator in the hallway. It increased its offer of compensation to £1,440, broken down as follows: £140 for lost services in line with its service level agreements £1,000 for time, trouble and inconvenience £300 for poor complaint handling What we found and why The circumstances of th is complaint are well known by the parties involved, so it
- score=3 amount=300.00 span={'page': 1, 'paragraph': 147, 'text_span': [4771, 4776]} context=12 February 2025 The landlord wrote to the resident and said that as a goodwill gesture it would be installing a radiator in the hallway. It increased its offer of compensation to £1,440, broken down as follows: £140 for lost services in line with its service level agreements £1,000 for time, trouble and inconvenience £300 for poor complaint handling What we found and why The circumstances of th is complaint are well known by the parties involved, so it is not necessary to detail everything that

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202408056.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/orbit-housing-association-limited-202408056/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/14-housing-ombudsman-202408056.draft_decision.json`

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
