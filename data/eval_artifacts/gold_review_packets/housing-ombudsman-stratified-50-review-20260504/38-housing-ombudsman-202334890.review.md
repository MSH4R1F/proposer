# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202334890`
Source slug: `london-quadrant-housing-trust-202334890`
Target source ID: `202334890`
Title: London & Quadrant Housing Trust   (202334890)
URL: https://www.housing-ombudsman.org.uk/decisions/london-quadrant-housing-trust-202334890/

## Manifest Strata

- Outcome raw: `resolved with intervention`
- Outcome normalized: `resolved-with-intervention`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2025-10-29`
- Landlord: `London & Quadrant Housing Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `2137.00`
- Draft region: `london` from `London & Quadrant Housing Trust (landlord_name_keyword; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The landlord was aware of a damp bedroom wall at the resident’s property since November 2022. It inspected the wall and carried out some works over the next year. The resident complained to the landlord on 6 December 2023 as she said the wall was still damp. The complaint is about the landlord’s handling of the resident’s reports of a damp bedroom wall.

## Money Candidates

- score=3 amount=2137.00 span={'page': 1, 'paragraph': 34, 'text_span': [1774, 1781]} context=ed better and what it could do to resolve the resident’s complaint. Following our intervention the landlord accepted that it had incorrectly calculated the compensation due to the resident for the loss of use of the bedroom. The landlord agreed to apologise to the resident, increase the overall compensation payment to £2,137 (including the revised figure of £1,228 for loss of use of the bedroom) and £150 additional compensation for its calculation error. The landlord also agreed to inspect the r
- score=3 amount=1228.00 span={'page': 1, 'paragraph': 34, 'text_span': [1814, 1821]} context=e the resident’s complaint. Following our intervention the landlord accepted that it had incorrectly calculated the compensation due to the resident for the loss of use of the bedroom. The landlord agreed to apologise to the resident, increase the overall compensation payment to £2,137 (including the revised figure of £1,228 for loss of use of the bedroom) and £150 additional compensation for its calculation error. The landlord also agreed to inspect the resident’s bedroom wall again to check if
- score=3 amount=980.57 span={'page': 1, 'paragraph': 32, 'text_span': [1100, 1107]} context=ve made recommendations for the landlord to put things right. Summary of reasons The landlord’s records show it inspected the property and carried out some repairs to the damp bedroom wall after the resident had reported it. The landlord apologised for the delays in taking action in its complaint responses and offered £980.57 compensation, which included £221.57 for the loss of use of the bedroom. The resident remained dissatisfied and asked us to investigate its handling of her complaint. We co
- score=3 amount=221.57 span={'page': 1, 'paragraph': 32, 'text_span': [1137, 1144]} context=ord to put things right. Summary of reasons The landlord’s records show it inspected the property and carried out some repairs to the damp bedroom wall after the resident had reported it. The landlord apologised for the delays in taking action in its complaint responses and offered £980.57 compensation, which included £221.57 for the loss of use of the bedroom. The resident remained dissatisfied and asked us to investigate its handling of her complaint. We contacted the landlord on 27 October 20
- score=3 amount=150.00 span={'page': 1, 'paragraph': 34, 'text_span': [1857, 1862]} context=ntervention the landlord accepted that it had incorrectly calculated the compensation due to the resident for the loss of use of the bedroom. The landlord agreed to apologise to the resident, increase the overall compensation payment to £2,137 (including the revised figure of £1,228 for loss of use of the bedroom) and £150 additional compensation for its calculation error. The landlord also agreed to inspect the resident’s bedroom wall again to check if rendering and drainage is required. Both p
- score=-4 amount=2137.00 span={'page': 1, 'paragraph': 40, 'text_span': [2470, 2478]} context=on, the landlord has agreed to take actions to remedy matters which resolve the complaint satisfactorily. Putting things right Recommendations The complaint has been resolved with intervention on the basis the landlord follows our recommendations. Our recommendations The landlord should apologise and make a payment of £ 2,137 to the resident. The landlord may deduct the amount of £980.57 if already paid. The landlord should arrange to inspect the damp wall at the resident’s property, and if nece
- score=-4 amount=980.57 span={'page': 1, 'paragraph': 43, 'text_span': [2533, 2540]} context=hich resolve the complaint satisfactorily. Putting things right Recommendations The complaint has been resolved with intervention on the basis the landlord follows our recommendations. Our recommendations The landlord should apologise and make a payment of £ 2,137 to the resident. The landlord may deduct the amount of £980.57 if already paid. The landlord should arrange to inspect the damp wall at the resident’s property, and if necessary, schedule works to carry out repairs to address the issue

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202334890.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/london-quadrant-housing-trust-202334890/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/38-housing-ombudsman-202334890.draft_decision.json`

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
