# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202508313`
Source slug: `jigsaw-homes-group-limited-202508313`
Target source ID: `202508313`
Title: Jigsaw Homes Group Limited (202508313)
URL: https://www.housing-ombudsman.org.uk/decisions/jigsaw-homes-group-limited-202508313/

## Manifest Strata

- Outcome raw: `no maladministration; maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-12-16`
- Landlord: `Jigsaw Homes Group Limited`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `350.00`
- Draft region: `london` from `Jigsaw Homes Group Limited (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident lives in a 3-bedroom house with her 2 children. The resident and her children have vulnerabilities that are known to the landlord. Between February 2023 and April 2025, the resident reported recurring damp and mould issues in her home. Therefore, she asked the landlord to consider granting a management move. The complaint is about the landlord’s handling of the resident’s: Reports of damp and mould. Request for a management move. Concerns about staff conduct. We have also investigated the landlord’s complaint handling.

## Money Candidates

- score=12 amount=350.00 span={'page': 1, 'paragraph': 83, 'text_span': [2496, 2502]} context=ting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 20 January 2026 2 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 3 00 for its handling of her reports of damp and mould. This includes the £100 offered at stage 1, £50 at stage 2, plus an additional £1 50 for the fail
- score=12 amount=300.00 span={'page': 1, 'paragraph': 86, 'text_span': [2522, 2529]} context=he failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 20 January 2026 2 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 3 00 for its handling of her reports of damp and mould. This includes the £100 offered at stage 1, £50 at stage 2, plus an additional £1 50 for the failings identified in this re
- score=12 amount=150.00 span={'page': 1, 'paragraph': 90, 'text_span': [2658, 2664]} context=eaningful and empathetic. It has due regard to our apologies guidance . No later than 20 January 2026 2 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 3 00 for its handling of her reports of damp and mould. This includes the £100 offered at stage 1, £50 at stage 2, plus an additional £1 50 for the failings identified in this report. £50 for its handling of her complaint. The landlord may deduct from the total figure any payments it has already made. The landlor
- score=12 amount=100.00 span={'page': 1, 'paragraph': 90, 'text_span': [2598, 2603]} context=is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 20 January 2026 2 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 3 00 for its handling of her reports of damp and mould. This includes the £100 offered at stage 1, £50 at stage 2, plus an additional £1 50 for the failings identified in this report. £50 for its handling of her complaint. The landlord may deduct from the
- score=12 amount=50.00 span={'page': 1, 'paragraph': 90, 'text_span': [2623, 2627]} context=res identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 20 January 2026 2 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 3 00 for its handling of her reports of damp and mould. This includes the £100 offered at stage 1, £50 at stage 2, plus an additional £1 50 for the failings identified in this report. £50 for its handling of her complaint. The landlord may deduct from the total figure any paymen
- score=12 amount=50.00 span={'page': 1, 'paragraph': 92, 'text_span': [2708, 2712]} context=apologies guidance . No later than 20 January 2026 2 Compensation order The landlord must pay the resident £ 350 made up as follows: £ 3 00 for its handling of her reports of damp and mould. This includes the £100 offered at stage 1, £50 at stage 2, plus an additional £1 50 for the failings identified in this report. £50 for its handling of her complaint. The landlord may deduct from the total figure any payments it has already made. The landlord must pay this directly to the resident and provid
- score=3 amount=150.00 span={'page': 1, 'paragraph': 250, 'text_span': [7228, 7232]} context=irs were undertaken in the property. Due to insufficient evidence, it did not uphold the resident’s complaint about the staff member but apologised to her for any upset caused. It reiterated its apology for its handling of the remedial works to the kitchen and offered the resident an additional £50 compensation (total £150) for the inconvenience caused . Between June 2025 and October 2025 The landlord and resident communicated regularly about t he repairs. However, at the time of our investigati
- score=3 amount=100.00 span={'page': 1, 'paragraph': 220, 'text_span': [6146, 6151]} context=ation and reduce humidity levels . However, it noted that she did not want the vents installed in her son’s bedroom. Regarding the complaint about the staff member, it was satisfied that they had “tried to be helpful” . However, it apologised to the resident f or how the call had made her feel. It offered the resident £100 compensation. It said this was in recognition of the delays in addressing the mould in the kitchen. 24 April 2025 The resident requested to escalate her complaint. She said th

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202508313.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/jigsaw-homes-group-limited-202508313/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/13-housing-ombudsman-202508313.draft_decision.json`

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
