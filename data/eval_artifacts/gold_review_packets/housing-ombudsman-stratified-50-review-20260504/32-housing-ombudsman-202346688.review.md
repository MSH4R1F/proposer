# Housing Ombudsman Gold Review Packet

Case: `housing-ombudsman-202346688`
Source slug: `metropolitan-thames-valley-housing-mtv-202346688`
Target source ID: `202346688`
Title: Metropolitan Thames Valley Housing (MTV) (202346688)
URL: https://www.housing-ombudsman.org.uk/decisions/metropolitan-thames-valley-housing-mtv-202346688/

## Manifest Strata

- Outcome raw: `maladministration; service failure`
- Outcome normalized: `maladministration`
- Matter types: `repairs_disrepair, complaint_handling_failure`
- Primary matter type: `repairs_disrepair`
- Decision date: `2026-03-31`
- Landlord: `Metropolitan Thames Valley Housing (MTV)`

## Candidate Gold Fields

- Draft winner: `tenant`
- Draft total awarded: `275.00`
- Draft region: `london` from `Metropolitan Thames Valley Housing (MTV) (needs_human_review; REVIEW_REQUIRED)`
- Draft matter type: `repairs_disrepair`
- Draft facts: The resident lives in a first floor flat . The neighbour below is a leaseholder. The resident reported a blocked drainpipe from the flat below to the landlord several times. The blockage caused her balcony to flood. The complaint is about the landlord’s handling of: a. The resident’s reports of flooding to her balcony and the subsequent repairs. b . T he associated complaint.

## Money Candidates

- score=18 amount=275.00 span={'page': 1, 'paragraph': 117, 'text_span': [2481, 2486]} context=riting to the resident for the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 30 April 2026 2 Compensation order The landlord must pay the resident £275 made up as follows: £2 25 (this includes £25 already offered to the resident by the landlord) for the time and trouble caused by the failings in its handling of her repair rep
- score=18 amount=225.00 span={'page': 1, 'paragraph': 119, 'text_span': [2506, 2512]} context=r the failures identified in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 30 April 2026 2 Compensation order The landlord must pay the resident £275 made up as follows: £2 25 (this includes £25 already offered to the resident by the landlord) for the time and trouble caused by the failings in its handling of her repair report. £ 5 0 for the time a
- score=18 amount=25.00 span={'page': 1, 'paragraph': 122, 'text_span': [2527, 2531]} context=fied in this report. The landlord must ensure: The apology is specific to the failures identified in this decision , meaningful and empathetic. It has due regard to our apologies guidance . No later than 30 April 2026 2 Compensation order The landlord must pay the resident £275 made up as follows: £2 25 (this includes £25 already offered to the resident by the landlord) for the time and trouble caused by the failings in its handling of her repair report. £ 5 0 for the time and inconvenience caus
- score=14 amount=50.00 span={'page': 1, 'paragraph': 124, 'text_span': [2666, 2672]} context=tic. It has due regard to our apologies guidance . No later than 30 April 2026 2 Compensation order The landlord must pay the resident £275 made up as follows: £2 25 (this includes £25 already offered to the resident by the landlord) for the time and trouble caused by the failings in its handling of her repair report. £ 5 0 for the time and inconvenience caused in relation to its complaint handling. This must be paid directly to the resident by the due date. The landlord must provide documentary
- score=3 amount=225.00 span={'page': 1, 'paragraph': 420, 'text_span': [8859, 8865]} context=The landlord offered the resident £ 25 for time and trouble. W e do not consider th is compensation proportionate to the impact of its failings. W e have therefore found maladministration in the landlord’s handling of the resident’s reports of flooding to her balcony . We have order ed the landlord to pay an award of £ 225 which includes the £ 25 it already offered , for the distress, inconvenience, time, and trouble caused, in line with our remedies guidance. Complaint The handling of the compl
- score=3 amount=25.00 span={'page': 1, 'paragraph': 405, 'text_span': [8574, 8579]} context=hen it rained and s he worried that the water would eventually enter her flat. Where there are acknowledged failings as in this case, our role is to determine if the landlord resolved the issue in line with our resolution principles : be fair, put things right and learn from outcome . The landlord offered the resident £ 25 for time and trouble. W e do not consider th is compensation proportionate to the impact of its failings. W e have therefore found maladministration in the landlord’s handling
- score=1 amount=50.00 span={'page': 1, 'paragraph': 488, 'text_span': [10486, 10490]} context=T his was not correct because it hadn’t fully addressed the complaint at stage 1 as the Code require d. The landlord did not award any compensation for its handling of the complaint within its internal complaints proce dure . It was only after the resident raised the complaint with us that the landlord offered to pay £50 compensation in recognition of its poor complaint handling. While it is positive that the landlord reconsidered its position and made an offer of redress, it is not clear why it
- score=1 amount=25.00 span={'page': 1, 'paragraph': 243, 'text_span': [4478, 4483]} context=023 The landlord issued its final response. It said : i t had followed procedure s and did what was required to provide the resident with the appropriate outcome i t was satisfied with the way it managed her complaint at stage 1 i t a ccepted that its communication had been poor and apologised i t offered the resident £ 25 compensation for time and trouble Referral to the Ombudsman The resident asked us to investigate the complaint . She said she couldn’t use the balcony for months because the d

## Files

- Source bundle: `data/eval_artifacts/source_bundles/housing-ombudsman-stratified-50-review-20260504/housing-ombudsman-202346688.source_bundle.json`
- Raw text: `raw/housing_ombudsman/decisions/metropolitan-thames-valley-housing-mtv-202346688/raw.txt`
- Draft decision template: `data/eval_artifacts/gold_review_packets/housing-ombudsman-stratified-50-review-20260504/draft_decisions/32-housing-ombudsman-202346688.draft_decision.json`

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
