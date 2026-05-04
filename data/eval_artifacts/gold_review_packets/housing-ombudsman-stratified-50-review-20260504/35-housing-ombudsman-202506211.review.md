# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202506211`
Source slug: `peabody-trust-202506211`
Target source ID: `202506211`
Title: Peabody Trust (202506211)
URL: https://www.housing-ombudsman.org.uk/decisions/peabody-trust-202506211/

## Manifest Strata

- Outcome raw: `reasonable redress`
- Outcome normalized: `reasonable-redress`
- Matter types: `repairs_damp_mould, repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_damp_mould`
- Decision date: `2026-01-07`
- Landlord: `Peabody Trust`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `1500.00`
- Draft region: `london` from `Peabody Trust (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_damp_mould`
- Draft facts: The resident moved in to the property in November 2023 and she reported damp and mould in her hallway, in January 2024. In March 2024, the landlord identified that the damp was caused by an issue with guttering. The guttering was repaired and between June and August 2024, it stripped back the hallway, replastered and redecorated. However, it failed to ensure the walls were dry, which meant damp and mould returned and the work needed redoing. The complaint was brought to us in May 2025 once all work had been completed, as the resident was unhappy with the level of compensation offered by the landlord. The complaint is about the landlord’s handling of reported water ingress, damp and...

## Money Candidates

- score=5 amount=1500.00 span={'page': 1, 'paragraph': 107, 'text_span': [8704, 8711]} context=the landlord increased its offer later to recognise that after the stage 2 response was issued, the resident was caused further inconvenience having to wait several more months for the work associated with the damp to be completed. This certainly amounts to good practice, The landlord acknowledged its failings and the £1,500 compensation offered was in line with its own guidance, as it reflected that overall, the resident suffered “serious disruption”. The amount offered is also in line with thi
- score=5 amount=800.00 span={'page': 1, 'paragraph': 106, 'text_span': [8301, 8306]} context=accepted there were failings. The only issue is the whether the compensation offered by the landlord sufficiently remedies the poor service identified. At stage 2, the landlord offered the resident £700 compensation for the delay and disruption the damp caused her over a long period of time. It then offered a further £800 compensation later once all further works were complete. It was positive that the landlord increased its offer later to recognise that after the stage 2 response was issued, th
- score=5 amount=700.00 span={'page': 1, 'paragraph': 106, 'text_span': [8180, 8185]} context=ork or ensuring the resident was regularly updated. There is no dispute that there has been poor service, as the landlord accepted there were failings. The only issue is the whether the compensation offered by the landlord sufficiently remedies the poor service identified. At stage 2, the landlord offered the resident £700 compensation for the delay and disruption the damp caused her over a long period of time. It then offered a further £800 compensation later once all further works were complet
- score=1 amount=950.00 span={'page': 1, 'paragraph': 66, 'text_span': [4250, 4255]} context=the work needed to be redone. It apologised for the stress and inconvenience caused. It also accepted it had failed to keep the resident informed of progress as agreed at stage 1. The landlord said it had arranged for the property to be assessed by a surveyor and had learned from its mistakes. It offered the resident £950 compensation : £700 for the disruption caused and £250 for the inconvenience of not following its complaints policy or procedure. The £950 was paid to the resident on 11 Decemb
- score=1 amount=950.00 span={'page': 1, 'paragraph': 68, 'text_span': [4389, 4394]} context=nformed of progress as agreed at stage 1. The landlord said it had arranged for the property to be assessed by a surveyor and had learned from its mistakes. It offered the resident £950 compensation : £700 for the disruption caused and £250 for the inconvenience of not following its complaints policy or procedure. The £950 was paid to the resident on 11 December 2024. 23 April 2025 The landlord finalised all outstanding works and offered additional compensation to the resident of £800. This was
- score=1 amount=800.00 span={'page': 1, 'paragraph': 70, 'text_span': [4554, 4558]} context=ed the resident £950 compensation : £700 for the disruption caused and £250 for the inconvenience of not following its complaints policy or procedure. The £950 was paid to the resident on 11 December 2024. 23 April 2025 The landlord finalised all outstanding works and offered additional compensation to the resident of £800. This was made up of £500 for delays completing all works and disruption to her home ( £100 per month since the stage 2 response ) . It also offered a further £ 300 compensati
- score=1 amount=700.00 span={'page': 1, 'paragraph': 67, 'text_span': [4270, 4275]} context=be redone. It apologised for the stress and inconvenience caused. It also accepted it had failed to keep the resident informed of progress as agreed at stage 1. The landlord said it had arranged for the property to be assessed by a surveyor and had learned from its mistakes. It offered the resident £950 compensation : £700 for the disruption caused and £250 for the inconvenience of not following its complaints policy or procedure. The £950 was paid to the resident on 11 December 2024. 23 April 2
- score=1 amount=500.00 span={'page': 1, 'paragraph': 70, 'text_span': [4580, 4585]} context=nsation : £700 for the disruption caused and £250 for the inconvenience of not following its complaints policy or procedure. The £950 was paid to the resident on 11 December 2024. 23 April 2025 The landlord finalised all outstanding works and offered additional compensation to the resident of £800. This was made up of £500 for delays completing all works and disruption to her home ( £100 per month since the stage 2 response ) . It also offered a further £ 300 compensation to acknowledge the resi

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202506211.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/peabody-trust-202506211/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/35-housing-ombudsman-202506211.draft_decision.json`

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
