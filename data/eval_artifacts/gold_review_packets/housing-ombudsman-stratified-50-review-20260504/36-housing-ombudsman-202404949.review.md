# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202404949`
Source slug: `southwark-council-202404949`
Target source ID: `202404949`
Title: Southwark Council (202404949)
URL: https://www.housing-ombudsman.org.uk/decisions/southwark-council-202404949/

## Manifest Strata

- Outcome raw: `reasonable redress`
- Outcome normalized: `reasonable-redress`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2025-11-27`
- Landlord: `Southwark Council`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `500.00`
- Draft region: `london` from `Southwark Council (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident has lived in the property, a one-bedroom ground-floor flat, since August 2022. He reported numerous leaks into his bathroom from the flat above before raising a complaint with the landlord. The complaint is about the landlord’s handling of the resident’s reports of leaks. We have also considered the landlord’s handling of the associated complaint.

## Money Candidates

- score=5 amount=500.00 span={'page': 1, 'paragraph': 163, 'text_span': [7120, 7125]} context=onse. Th ese included delays in carrying out the investigative works needed and failures in chasing the work it had issued to contractors. This points to record keeping and communication failures. The landlord offered compensation for its handling of these reports as follows: £500 for the delays in resolving the leak. £500 for the distress and inconvenience caused by the leak. £50 for a missed appointment in April 2024. The delays that the landlord identified were not made clear in the response
- score=5 amount=50.00 span={'page': 1, 'paragraph': 164, 'text_span': [7180, 7184]} context=ve works needed and failures in chasing the work it had issued to contractors. This points to record keeping and communication failures. The landlord offered compensation for its handling of these reports as follows: £500 for the delays in resolving the leak. £500 for the distress and inconvenience caused by the leak. £50 for a missed appointment in April 2024. The delays that the landlord identified were not made clear in the response provided to the resident. However, it was clear that there w
- score=3 amount=500.00 span={'page': 1, 'paragraph': 162, 'text_span': [7077, 7082]} context=d some further failings in its stage 2 response. Th ese included delays in carrying out the investigative works needed and failures in chasing the work it had issued to contractors. This points to record keeping and communication failures. The landlord offered compensation for its handling of these reports as follows: £500 for the delays in resolving the leak. £500 for the distress and inconvenience caused by the leak. £50 for a missed appointment in April 2024. The delays that the landlord iden
- score=2 amount=1000.00 span={'page': 1, 'paragraph': 170, 'text_span': [8077, 8084]} context=eks rather than months. The longer delay was caused by the landlord not being able to gain access to the flat above, which was not the fault of the landlord. We have considered the offer of £500 for the delays and the £500 for the distress and inconvenience together in our consideration of this complaint. A payment of £1,000 is appropriate when there has been maladministration with a significant impact on the resident. The prolonged duration of the issue and the delays in resolving this will hav
- score=2 amount=500.00 span={'page': 1, 'paragraph': 170, 'text_span': [7947, 7952]} context=ocess of gaining access to the flat above. These failings were of a reasonably short-term nature, with the landlord delaying by weeks rather than months. The longer delay was caused by the landlord not being able to gain access to the flat above, which was not the fault of the landlord. We have considered the offer of £500 for the delays and the £500 for the distress and inconvenience together in our consideration of this complaint. A payment of £1,000 is appropriate when there has been maladmin
- score=2 amount=500.00 span={'page': 1, 'paragraph': 170, 'text_span': [7975, 7980]} context=he flat above. These failings were of a reasonably short-term nature, with the landlord delaying by weeks rather than months. The longer delay was caused by the landlord not being able to gain access to the flat above, which was not the fault of the landlord. We have considered the offer of £500 for the delays and the £500 for the distress and inconvenience together in our consideration of this complaint. A payment of £1,000 is appropriate when there has been maladministration with a significant
- score=0 amount=1300.00 span={'page': 1, 'paragraph': 56, 'text_span': [1789, 1796]} context=inistration we can make orders for the landlord to put things right. We have the discretion to make recommendations in all other cases within our jurisdiction. Recommendations Our recommendations are not binding, and a landlord may decide not to follow them. Our recommendations The landlord should pay the resident the £1,300 it offered for the failings it identified in the handling of the resident’s reports of leaks and complaint , if it has not done so already. Our findings of reasonable redres
- score=0 amount=500.00 span={'page': 1, 'paragraph': 99, 'text_span': [3523, 3528]} context=1 response not being provided by the managing agent at the time of the initial complaint. It also highlighted that the complaint was not escalated to stage 2 when the resident asked for this to happen . It offered £250 for this failing . It offered £50 for a missed appointment in April 2024. I n addition, i t offered £500 for the distress and inconvenience caused. It explained that it was continuing to try to gain access to the flat above to resolve the issues with the leak, but this was proving

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202404949.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/southwark-council-202404949/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/36-housing-ombudsman-202404949.draft_decision.json`

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
