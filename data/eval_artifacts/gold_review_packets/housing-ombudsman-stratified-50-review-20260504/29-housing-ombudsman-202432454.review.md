# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202432454`
Source slug: `london-borough-of-lewisham-202432454`
Target source ID: `202432454`
Title: London Borough of Lewisham (202432454)
URL: https://www.housing-ombudsman.org.uk/decisions/london-borough-of-lewisham-202432454/

## Manifest Strata

- Outcome raw: `maladministration`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-12-16`
- Landlord: `London Borough of Lewisham`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `650.00`
- Draft region: `london` from `London Borough of Lewisham (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident moved into his property on 2 January 2024. He said that the landlord was aware he had multiple health conditions such as aquagenic pruritus, sickle cell trait, chronic pain, depression and anxiety. However, the landlord said it had no recorded vulnerabilities for the resident. The resident reported multiples repairs since February 2024. Although the landlord carried out repairs, the resident said some repairs remained outstanding. The complaint is about the landlord’s handling of: The repairs in the property. The associated complaint.

## Money Candidates

- score=11 amount=650.00 span={'page': 1, 'paragraph': 80, 'text_span': [2973, 2978]} context=e apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . Learning order compensation discuss vulnerabilities and update records . Inspect the proeprty thermostat. No later than 13 January 2026 2 Compensation order The landlord must pay £650 to the resident (t his is inclusive of the landlord’s offer to pay the resident £210 compensation, and it should deduct this from the above amount if already paid ) . The awar
- score=11 amount=550.00 span={'page': 1, 'paragraph': 84, 'text_span': [3173, 3178]} context=ate records . Inspect the proeprty thermostat. No later than 13 January 2026 2 Compensation order The landlord must pay £650 to the resident (t his is inclusive of the landlord’s offer to pay the resident £210 compensation, and it should deduct this from the above amount if already paid ) . The award is equivalent to: £550 to reflect the distress and inconvenience caused to the resident by its handling of the repairs to the property . £100 to reflect the impact of its complaint handling failings
- score=11 amount=210.00 span={'page': 1, 'paragraph': 81, 'text_span': [3058, 3063]} context=pathetic. It has due regard to our apologies guidance . Learning order compensation discuss vulnerabilities and update records . Inspect the proeprty thermostat. No later than 13 January 2026 2 Compensation order The landlord must pay £650 to the resident (t his is inclusive of the landlord’s offer to pay the resident £210 compensation, and it should deduct this from the above amount if already paid ) . The award is equivalent to: £550 to reflect the distress and inconvenience caused to the resi
- score=5 amount=100.00 span={'page': 1, 'paragraph': 88, 'text_span': [3292, 3297]} context=£650 to the resident (t his is inclusive of the landlord’s offer to pay the resident £210 compensation, and it should deduct this from the above amount if already paid ) . The award is equivalent to: £550 to reflect the distress and inconvenience caused to the resident by its handling of the repairs to the property . £100 to reflect the impact of its complaint handling failings. This must be paid directly to the resident by the due date. The landlord must provide documentary evidence of payment
- score=3 amount=550.00 span={'page': 1, 'paragraph': 492, 'text_span': [24783, 24788]} context=enience caused to the resident and a missed appointment in December 2024. While it was appropriate for the landlord to offer compensation, the amount did not reflect the impact of the failings identified in this report. In line with our Remedies Guidance, which is published on our website, we order the landlord to pay £550 compensation to the resident (this is inclusive of the landlord’s offer). This reflects that although the landlord took steps to resolve the repairs, its failings significantl
- score=3 amount=250.00 span={'page': 1, 'paragraph': 492, 'text_span': [25019, 25024]} context=Remedies Guidance, which is published on our website, we order the landlord to pay £550 compensation to the resident (this is inclusive of the landlord’s offer). This reflects that although the landlord took steps to resolve the repairs, its failings significantly impacted on the resident. The award is equivalent to: £250 to reflect the inconvenience and distress caused to the resident by having to repeatedly reports issues, the delays in resolving the repairs and the repeated visits. £200 to re
- score=3 amount=210.00 span={'page': 1, 'paragraph': 442, 'text_span': [12119, 12124]} context=pairing cracks and collapsing worktops , and installing insulation . He also requested compensation , a rent refund from January 2024, prioritis ing his property for major works , and improvements to the landlord complaint handling . Following referral to the Ombudsman On 14 January 2025 , t he landlord offered to pay £210 compensation to the resident, which was equivalent to: £20 for not attending the repair appointment to the windows in December 2024. £190 for the delay in repairing the bedroo
- score=3 amount=210.00 span={'page': 1, 'paragraph': 491, 'text_span': [24366, 24371]} context=tion as agreed following its May 2024 complaint response. Although it addressed this in October 2024, this was 5 months later, which was unreasonable. Its communication failings and delays caused inconvenience to the resident who had to repeatedly raise the issue. Following the end of its process, the landlord offered £210 compensation to the resident for its handling of the bedroom heater installation, the inconvenience caused to the resident and a missed appointment in December 2024. While it

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202432454.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-borough-of-lewisham-202432454/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/29-housing-ombudsman-202432454.draft_decision.json`

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
