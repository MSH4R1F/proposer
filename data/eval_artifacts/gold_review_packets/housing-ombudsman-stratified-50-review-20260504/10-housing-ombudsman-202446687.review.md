# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202446687`
Source slug: `peabody-trust-202446687`
Target source ID: `202446687`
Title: Peabody Trust (202446687)
URL: https://www.housing-ombudsman.org.uk/decisions/peabody-trust-202446687/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-11-26`
- Landlord: `Peabody Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1000.00`
- Draft region: `london` from `Peabody Trust (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a 2 bedroom flat with her children. She reported that the poor condition of her windows caused damp and mould in the property. The landlord’s handling of: Reports of damp and mould. Reports about the poor condition of windows in the property. The associated complaint

## Money Candidates

- score=20 amount=1000.00 span={'page': 1, 'paragraph': 90, 'text_span': [2483, 2490]} context=his report. The landlord must ensure: T he apology is provided by a senior member of staff The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 January 2026 2 Compensation Order The landlord must pay the resident £1,000 made up as follows: £250 for the distress and inconvenience caused by its handling of reports of damp and mould. £600 for the distress and inconvenience caused by its handli
- score=16 amount=600.00 span={'page': 1, 'paragraph': 91, 'text_span': [2603, 2608]} context=e failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 January 2026 2 Compensation Order The landlord must pay the resident £1,000 made up as follows: £250 for the distress and inconvenience caused by its handling of reports of damp and mould. £600 for the distress and inconvenience caused by its handling of reports about the poor condition of the windows in the property. £150 for the distress and inconvenience cause by
- score=16 amount=250.00 span={'page': 1, 'paragraph': 90, 'text_span': [2510, 2515]} context=st ensure: T he apology is provided by a senior member of staff The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 05 January 2026 2 Compensation Order The landlord must pay the resident £1,000 made up as follows: £250 for the distress and inconvenience caused by its handling of reports of damp and mould. £600 for the distress and inconvenience caused by its handling of reports about the poo
- score=16 amount=150.00 span={'page': 1, 'paragraph': 94, 'text_span': [2734, 2739]} context=January 2026 2 Compensation Order The landlord must pay the resident £1,000 made up as follows: £250 for the distress and inconvenience caused by its handling of reports of damp and mould. £600 for the distress and inconvenience caused by its handling of reports about the poor condition of the windows in the property. £150 for the distress and inconvenience cause by its complaint handling. The landlord may deduct any payments it has already made from this total figure. This must be paid directly
- score=14 amount=250.00 span={'page': 1, 'paragraph': 185, 'text_span': [9584, 9589]} context=the issue at its source. It also failed to carry out a risk assessment or a damp and mould survey in line with its own policies. The resident had to live with ongoing damp and mould for 8 months and repeatedly clean this away throughout the timeline. In addition to a written apology, the landlord must pay the resident £250 compensation for the distress and inconvenience caused by its poor handling of the damp and mould. This is in line with our published remedies guidance for failings which adve
- score=12 amount=600.00 span={'page': 1, 'paragraph': 228, 'text_span': [14637, 14642]} context=poor communication. The landlord’s learning from its stage 1 response was to complete jobs in a reasonable timeframe. It failed to demonstrate this learning in practice over the following 6 months. We therefore find there has been maladministration. In addition to a written apology, the landlord must pay the resident £600 compensation for the distress and inconvenience caused by its poor handling of the window replacements. This is in line with our published remedies guidance for failings which
- score=5 amount=210.00 span={'page': 1, 'paragraph': 136, 'text_span': [5619, 5624]} context=o answer and that the resident was away in May 2025, delaying repairs further. It advised that its communication was inadequate. It confirmed it expected to replace the windows the week commencing 11 August 2025. This would resolve the mould issues as she would be able to ventilate her home again. The landlord offered £210 compensation made up of: £140 for distress and inconvenience related to repairs and communication. £70 for time and trouble related to delays and communications with its compl
- score=5 amount=150.00 span={'page': 1, 'paragraph': 256, 'text_span': [17045, 17050]} context=nt handling. Our remedies guidance suggests an offer in this range when there has been a failing over a short duration. The delay here was 7 months and so the offer of £70 was insufficient and failed to take into account the full extent of distress and inconvenience. We have ordered the landlord to pay compensation of £150 for its complaint handling failures. This is in line with our published remedies guidance for failings which adversely affect the resident, but which do not have a permanent i

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202446687.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/peabody-trust-202446687/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/10-housing-ombudsman-202446687.draft_decision.json`

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
