# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202316658`
Source slug: `sovereign-network-group-202316658`
Target source ID: `202316658`
Title: Sovereign Network Group (202316658)
URL: https://www.housing-ombudsman.org.uk/decisions/sovereign-network-group-202316658/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-14`
- Landlord: `Sovereign Network Group`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `200.00`
- Draft region: `london` from `Sovereign Network Group (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives in a 2-bedroom semi-detached house. The landlord is aware the resident has mental health vulnerabilities and does not have digital access . She said she was unhappy with the landlord’s response to her reports of anti-social behaviour (ASB). She was also unhappy they had not provided a copy of the homes Energy Performance Certificate (EPC). The complaint is about the landlord’s response to the resident’s: reports of ASB and associated fencing repairs . request for an E nergy P erformance C ertificate . complaint of discrimination. associated complaint.

## Money Candidates

- score=20 amount=200.00 span={'page': 1, 'paragraph': 124, 'text_span': [3127, 3134]} context=ing to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 12 December 2025 2 Compensation order The landlord must pay the resident £ 2 00 for the distress and inconvenience caused to her by its handling of the reports of ASB. This must be paid directly to the resident by the due date. The landlord must provide

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202316658.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/sovereign-network-group-202316658/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/24-housing-ombudsman-202316658.draft_decision.json`

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
