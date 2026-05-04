# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202509252`
Source slug: `london-borough-of-hounslow-202509252`
Target source ID: `202509252`
Title: London Borough of Hounslow (202509252)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-hounslow-202509252/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-14`
- Landlord: `London Borough of Hounslow`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `700.00`
- Draft region: `london` from `London Borough of Hounslow (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The property is a 2-bedroom flat on the first (top) floor. The landlord’s handling of damp and mould. We have also investigated the landlord’s complaint handling.

## Money Candidates

- score=15 amount=700.00 span={'page': 1, 'paragraph': 99, 'text_span': [2480, 2487]} context=dlord must contact the resident and confirm details of all vulnerabilities affecting her and her family and centrally record these. A written update to be sent to the resident confirming this has been done. No later than 12 December 2025 4 Compensation order The landlord must provide evidence it has pa id the resident £ 7 00 to recognise the distress and inconvenience caused by its failures, made up as follows: £ 600 for its handling of the damp and mould (inclusive of the £200 already offered).
- score=11 amount=600.00 span={'page': 1, 'paragraph': 102, 'text_span': [2575, 2581]} context=r family and centrally record these. A written update to be sent to the resident confirming this has been done. No later than 12 December 2025 4 Compensation order The landlord must provide evidence it has pa id the resident £ 7 00 to recognise the distress and inconvenience caused by its failures, made up as follows: £ 600 for its handling of the damp and mould (inclusive of the £200 already offered). £ 100 for its complaint handling. The landlord must confirm with the resident whether she want
- score=11 amount=200.00 span={'page': 1, 'paragraph': 104, 'text_span': [2638, 2643]} context=t to the resident confirming this has been done. No later than 12 December 2025 4 Compensation order The landlord must provide evidence it has pa id the resident £ 7 00 to recognise the distress and inconvenience caused by its failures, made up as follows: £ 600 for its handling of the damp and mould (inclusive of the £200 already offered). £ 100 for its complaint handling. The landlord must confirm with the resident whether she wants this paid to her rent account or directly to her. The landlor
- score=11 amount=100.00 span={'page': 1, 'paragraph': 104, 'text_span': [2661, 2667]} context=rming this has been done. No later than 12 December 2025 4 Compensation order The landlord must provide evidence it has pa id the resident £ 7 00 to recognise the distress and inconvenience caused by its failures, made up as follows: £ 600 for its handling of the damp and mould (inclusive of the £200 already offered). £ 100 for its complaint handling. The landlord must confirm with the resident whether she wants this paid to her rent account or directly to her. The landlord may deduct from the t
- score=5 amount=600.00 span={'page': 1, 'paragraph': 495, 'text_span': [16915, 16921]} context=of compensation wa s reasonable to reflect the level of distress and inconvenience caused to the resident . In consultation with our remedies guidance, we find that the redress offered was not proportionate . Therefore, there was maladministration by the landlord . We order it to apologise to the resident and pay her £ 600 compensation (inclusive of the £200 already offered). This reflects the failures which adversely affected her, and the redress needed to put things right is substantial. This
- score=5 amount=200.00 span={'page': 1, 'paragraph': 497, 'text_span': [16952, 16957]} context=eflect the level of distress and inconvenience caused to the resident . In consultation with our remedies guidance, we find that the redress offered was not proportionate . Therefore, there was maladministration by the landlord . We order it to apologise to the resident and pay her £ 600 compensation (inclusive of the £200 already offered). This reflects the failures which adversely affected her, and the redress needed to put things right is substantial. This is because of the distress, inconven
- score=3 amount=2500.00 span={'page': 1, 'paragraph': 503, 'text_span': [17270, 17277]} context=e £200 already offered). This reflects the failures which adversely affected her, and the redress needed to put things right is substantial. This is because of the distress, inconvenience, time and trouble she incurred as a result of the landlord’s failures. The resident has told us she wants the landlord to clear her £2,500 rent arrears, instead of paying compensation. Our compensation awards are based on our remedies guidance and this does not support an award of £2,500 in the circumstances .
- score=3 amount=2500.00 span={'page': 1, 'paragraph': 504, 'text_span': [17420, 17427]} context=ecause of the distress, inconvenience, time and trouble she incurred as a result of the landlord’s failures. The resident has told us she wants the landlord to clear her £2,500 rent arrears, instead of paying compensation. Our compensation awards are based on our remedies guidance and this does not support an award of £2,500 in the circumstances . As we have ordered the landlord to pay some compensation, it should confirm if the resident wants this paid to her rent account or to her directly. Th

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202509252.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-hounslow-202509252/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/08-housing-ombudsman-202509252.draft_decision.json`

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
