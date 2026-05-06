# housing.repairs_social.v1 — Per-Factor Annotation Rubric

> Spec: `docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md` §12, §22.1
> Domain pack version: v1 (leakage-audited)
>
> This rubric is the binding reference for both LLM annotators and human reviewers
> labelling factor presence in Housing Ombudsman case narratives. Each section below
> mirrors one factor in `factors.yaml` (15 in total). Heading IDs are bare (no
> prefix) so the test can match them to the canonical factor IDs verbatim.
>
> **Reading guide:**
> - *Operational definition*: the single test that decides "present" vs "absent".
> - *Affirmative phrasings*: surface text patterns that count as "present".
> - *Negative phrasings*: surface text patterns that count as "absent" or
>   "unclear" (defaults to absent unless an explicit positive signal is found).
> - *Edge cases*: ambiguous scenarios with the rubric's authoritative call.
> - *Polarity*: must match `factors.yaml` exactly.
> - *Source authority*: the statutory or guidance ground supporting the factor.
>   Where no direct provision exists, the rubric explicitly says
>   "no direct statutory ground — guidance-derived".
>
> **General rules for annotators:**
> 1. Annotate from the case narrative as published by the Housing Ombudsman; do
>    not infer facts not stated.
> 2. "Unclear" defaults to **absent** for boolean factors and **null/unknown**
>    for numeric factors — never guess a duration.
> 3. The rubric labels factor *presence*, not *significance*. The downstream
>    predictor decides whether a delay is excessive or an impact is severe in
>    context.
> 4. Polarity is a property of the factor, not the case. A `pro_respondent`
>    factor being present favours the landlord; the same factor being absent
>    does not by itself favour the resident.

---

## repair_responsibility_established

**Operational definition:** The narrative states or makes plain that the
landlord (not the resident, freeholder, or third party) is contractually or
statutorily responsible for the specific repair item under dispute.

**Affirmative phrasings:**
- "The landlord accepted responsibility for repairing the roof."
- "Under the tenancy agreement the landlord was obliged to maintain the boiler."
- "The leak fell within the landlord's repairing obligations."

**Negative phrasings:**
- "The repair was the resident's responsibility under the tenancy."
- "The fault was caused by the resident's own alterations."
- "Responsibility for the structure was disputed between the landlord and the freeholder."

**Edge cases:**
- *Disputed responsibility but no resolution stated.* The narrative records a
  dispute that the landlord did not concede or the Ombudsman did not resolve.
  Call: **absent**. Responsibility is not established merely by being asserted.
- *Communal areas in a leasehold block.* If the narrative shows the landlord
  managed and recharged the repair via the freeholder, treat the landlord as
  responsible for the resident-facing service. Call: **present**.

**Polarity:** `pro_claimant`

**Source authority:** Landlord and Tenant Act 1985 s11 (implied repairing
covenant for short leases of dwellings); Homes (Fitness for Human Habitation)
Act 2018 (implied term of fitness for human habitation).

---

## hazard_or_disrepair_reported

**Operational definition:** The resident (or someone acting on their behalf)
made a contact, in any channel, that conveyed the existence of the disrepair
or hazard to the landlord.

**Affirmative phrasings:**
- "The resident first reported the damp in March 2022."
- "A repair was logged on the landlord's system on 12 May."
- "The resident telephoned the housing officer about the leak."

**Negative phrasings:**
- "There is no record of any report being made."
- "The resident only raised the issue at the formal complaint stage."
- "The landlord became aware of the disrepair through a routine inspection."

**Edge cases:**
- *Report made by a third party (relative, councillor, support worker).*
  Call: **present**. The Ombudsman treats third-party reports as resident
  reports for notice purposes provided they identify the property.
- *Report described only as "ongoing" with no first-contact event.* Call:
  **present** if a report is implied at any point in the timeline; this factor
  is about whether a report exists at all, not when.

**Polarity:** `pro_claimant`

**Source authority:** Housing Ombudsman Complaint Handling Code 2024
(record-keeping obligations regarding service requests).

---

## landlord_notice_established

**Operational definition:** The narrative shows that the landlord actually
received the report — i.e. acknowledged it, logged it, responded to it, or did
not credibly deny it. Distinct from `hazard_or_disrepair_reported`, which
captures the resident's act of reporting.

**Affirmative phrasings:**
- "The landlord acknowledged receipt of the report by email."
- "The repair ticket was opened on the landlord's system."
- "The landlord did not dispute that it had been informed."

**Negative phrasings:**
- "The landlord said the report had not reached the relevant team."
- "There is no evidence the contractor passed the report to the landlord."
- "The landlord's records do not show the call."

**Edge cases:**
- *Resident reports to a contractor only.* If the contractor is the landlord's
  agent (e.g. repairs subcontractor), notice is established. If the contractor
  is independent (e.g. a private surveyor instructed by the resident), notice
  is **absent** unless the contractor passed the report on.
- *Report acknowledged late.* Notice is established at the point of
  acknowledgement, even if late. The lateness goes to delay factors, not
  notice itself.

**Polarity:** `pro_claimant`

**Source authority:** Landlord and Tenant Act 1985 s11 (repair obligation
arises when landlord has notice); O'Brien v Robinson [1973] AC 912 (no
liability without notice — guidance-derived application to Ombudsman cases).

---

## inspection_offered

**Operational definition:** The landlord proposed, scheduled, or attempted to
carry out an inspection or survey of the reported issue. "Offered" includes
unsuccessful attempts (missed appointments, no-access visits) provided the
landlord initiated them.

**Affirmative phrasings:**
- "A surveyor was sent to the property on 4 June."
- "The landlord arranged an inspection but the resident missed the appointment."
- "A damp survey was commissioned in response to the report."

**Negative phrasings:**
- "No inspection was carried out at any point."
- "The landlord proceeded straight to a repair without inspecting."
- "The resident requested an inspection but received no response."

**Edge cases:**
- *Repair carried out without prior inspection where inspection was not
  needed.* Call: **absent** for this factor. The inspection question is
  separate from whether the repair itself was sensible. (`repair_attempted`
  may still be present.)
- *Landlord booked an inspection that the resident refused.* Call: **present**.
  The factor records the offer; whether refusal was reasonable is a separate
  judgment for the predictor.

**Polarity:** `pro_respondent`

**Source authority:** Decent Homes Standard (gov.uk guidance on landlord
inspection regimes); Housing Ombudsman Spotlight on damp and mould (2021)
recommending proactive inspection.

---

## inspection_delay_days

**Operational definition:** Whole-number count of days between the date the
landlord received notice (the date the resident's report was acknowledged,
logged, or first responded to — the same underlying evidence that supports
`landlord_notice_established`) and the date of the first inspection actually
carried out (or attempted with access). If inspection never occurred, this
factor is **null/unknown**, not 0.

**Affirmative phrasings (numeric):**
- "Inspection took place 14 days after the report."
- "A surveyor attended six weeks later." (encode as ~42)
- "The first visit was on 1 July, three months after the report." (encode as ~90)

**Negative phrasings:**
- "No inspection ever took place." (null)
- "The landlord declined to inspect."   (null)
- Date of inspection cannot be determined from the narrative. (null)

**Edge cases:**
- *Multiple inspections.* Use the **first** inspection date. Subsequent
  inspections inform `repair_delay_days` and `communication_gap_days`.
- *Inspection attempted but no access granted.* Count the date of the first
  attempt, not the date access was eventually achieved. The narrative often
  makes this distinction explicit.

**Polarity:** `pro_claimant` (longer delays favour the resident).

**Source authority:** No direct statutory ground — guidance-derived from
Housing Ombudsman determinations referencing "reasonable timescales" and
landlord repairs policies.

---

## repair_attempted

**Operational definition:** The landlord (or its contractor) carried out, or
clearly tried to carry out, at least one substantive repair action in
response to the report. Includes partial or unsuccessful repairs.

**Affirmative phrasings:**
- "Operatives attended and renewed the seal around the bath."
- "A temporary repair was made while parts were on order."
- "The boiler was replaced in August."

**Negative phrasings:**
- "No repair work was undertaken."
- "The job was raised but never attended."
- "The landlord deferred the repair pending an investigation that did not
  conclude."

**Edge cases:**
- *Inspection only, no repair work.* Call: **absent**. Inspecting is not
  repairing; that is what `inspection_offered` is for.
- *Resident-funded repair the landlord later reimbursed.* Call: **present**.
  The landlord's funding constitutes the repair action even if the resident
  arranged the work.

**Polarity:** `pro_respondent`

**Source authority:** Landlord and Tenant Act 1985 s11 (duty to repair
implies active remediation).

---

## repair_delay_days

**Operational definition:** Whole-number count of days between landlord notice
and the latest recorded state of the repair (completion if completed; date of
the determination or the most recent narrative event if still outstanding).
If no repair was ever attempted and the issue remains live at the date of the
narrative, use the days from notice to that narrative date.

**Affirmative phrasings (numeric):**
- "The repair was completed within 21 days of the report."
- "Works finished 18 months after notice." (encode as ~545)
- "At the date of this report the repair remains outstanding, 14 months after
  the original complaint." (encode as ~425)

**Negative phrasings:**
- Notice date or completion date cannot be determined. (null)
- "The complaint concerned a different matter, not a repair." (null — factor
  not engaged)

**Edge cases:**
- *Repeated returns for the same defect.* Use the date the defect was finally
  resolved, not the first attempt. If still recurring, treat as outstanding.
- *Multiple distinct defects in one case.* Encode for the principal defect
  identified by the Ombudsman; if the case is genuinely multi-headed and the
  delays diverge sharply, prefer the longer delay.

**Polarity:** `pro_claimant` (longer delays favour the resident).

**Source authority:** Landlord and Tenant Act 1985 s11 (repairs within a
reasonable time); Housing Ombudsman Complaint Handling Code 2024 (timeliness
expectations).

---

## records_inadequate

**Operational definition:** The narrative or the Ombudsman's reasoning notes
that the landlord's repair, contact, or complaint records contain significant
gaps — missing dates, missing visit notes, lost calls, contradictory entries
— such that the audit trail does not support reconstruction of what happened.

**Affirmative phrasings:**
- "The landlord could not produce records of the repair visits."
- "There were inconsistencies between the contractor's logs and the
  landlord's repair history."
- "The Ombudsman noted poor record-keeping by the landlord."

**Negative phrasings:**
- "The landlord provided a comprehensive repair history."
- "Records showed each visit, the operative, and the work undertaken."
- The narrative is silent about record quality. (default to **absent**)

**Edge cases:**
- *Records exist but contradict the resident's account.* Call: **absent**
  unless the Ombudsman finds them unreliable. Disagreement is not
  inadequacy.
- *Some records missing but enough to follow the timeline.* Call: **absent**.
  This factor is about meaningful gaps, not perfection.

**Polarity:** `pro_claimant`

**Source authority:** Housing Ombudsman Complaint Handling Code 2024
(record-keeping obligations); Housing Ombudsman Spotlight on knowledge and
information management (2023).

---

## communication_gap_days

**Operational definition:** Whole-number count of the **longest** continuous
gap in days between substantive landlord-resident communications about the
reported issue. Acknowledgement-only auto-replies do not count as
substantive. If the entire history shows continuous engagement, encode the
longest such gap (often very small).

**Affirmative phrasings (numeric):**
- "The landlord did not respond to the resident for nearly four months."
  (encode as ~120)
- "There was a six-week gap before the next update." (encode as ~42)
- "Between July and December the resident heard nothing." (encode as ~150)

**Negative phrasings:**
- The narrative does not describe communication patterns. (null)
- "The complaint was about a one-off failure of contact at the start." (null
  if no measurable gap is given; otherwise encode the gap)

**Edge cases:**
- *Resident initiated the silence.* If the gap is attributable to the
  resident not responding to the landlord's reasonable contact, encode the
  gap as 0 (not null) — the landlord communicated.
- *Multiple gaps of similar size.* Use the **longest**.

**Polarity:** `pro_claimant` (longer gaps favour the resident).

**Source authority:** No direct statutory ground — guidance-derived from
Housing Ombudsman Complaint Handling Code 2024 and repeated Spotlight
findings on landlord communication.

---

## complaint_response_delay_days

**Operational definition:** Whole-number count of days between the resident's
formal complaint (Stage 1 in the landlord's complaints procedure, or
equivalent) and the landlord's substantive response. If the landlord never
issued a response, encode the days to the date of the determination.

**Affirmative phrasings (numeric):**
- "The Stage 1 response was issued 25 working days after the complaint."
  (convert to calendar days for encoding)
- "The landlord replied to the complaint after eight weeks." (encode as ~56)
- "No response was provided before the case reached the Ombudsman." (encode
  days to determination)

**Negative phrasings:**
- "The complaint was not formal — the resident only made informal contact."
  (null)
- Formal complaint date is not given. (null)

**Edge cases:**
- *Stage 2 used as the response.* Use Stage 1 if it occurred; otherwise
  Stage 2. The factor is about the first substantive response to the formal
  complaint.
- *Holding response only.* A purely procedural acknowledgement is not
  substantive. Use the date of the substantive reply or, if none, the date
  of determination.

**Polarity:** `pro_claimant` (longer delays favour the resident).

**Source authority:** Housing Ombudsman Complaint Handling Code 2024 (Stage 1
within 10 working days; Stage 2 within 20 working days, with permitted
extensions on notice).

---

## vulnerability_known

**Operational definition:** The narrative shows that the landlord was on
notice of a relevant vulnerability of the resident or a household member
before or during the disrepair episode. "Relevant" means the vulnerability
intersects with the disrepair (e.g. respiratory condition + damp; mobility
impairment + lift failure).

**Affirmative phrasings:**
- "The landlord was aware that the resident's child had asthma."
- "Vulnerability flags were on the tenancy file."
- "The resident had previously notified the landlord of her disability."

**Negative phrasings:**
- "The resident did not disclose any health condition."
- "The Ombudsman found no evidence of the landlord being on notice of the
  vulnerability."
- The narrative does not mention vulnerability. (default to **absent**)

**Edge cases:**
- *Vulnerability disclosed only at the complaint stage, not during the
  disrepair period.* Call: **present** from the date of disclosure onwards;
  for a binary factor encode **present** if disclosure occurred at any point
  before determination.
- *General old-age or "elderly" descriptors with no specific condition.*
  Call: **absent** unless the narrative ties the descriptor to a specific
  vulnerability the landlord knew of.

**Polarity:** `pro_claimant`

**Source authority:** Equality Act 2010 (reasonable adjustments where
vulnerability includes disability); Housing Ombudsman Spotlight on
attitudes, respect and rights — relationship of equals (2024) (vulnerability
guidance).

---

## impact_severity_reported

**Operational definition:** The resident-reported impact level of the
disrepair on the household, encoded as one of `none | minor | moderate |
severe`. This records the **resident's** account; the predictor decides
whether the report carries weight.

**Affirmative phrasings:**
- *severe*: "The family had to sleep in one room because of mould throughout
  the property" / "The resident's child was hospitalised due to the damp."
- *moderate*: "The leak made the bathroom unusable for several weeks" /
  "The cold caused significant disruption to daily life."
- *minor*: "The resident was inconvenienced by the noise" / "Some
  redecoration was needed."
- *none*: "The resident reported no health or living impact" / an explicit
  statement that there was no impact.

**Negative phrasings:**
- The narrative has no language about impact. (encode as **null** —
  unknown, not "no impact"; silence does not equal an explicit no-impact
  statement)
- The Ombudsman's own characterisation, not the resident's. (use only as a
  fallback if no resident report is available)

**Edge cases:**
- *Resident reports severe impact, landlord disputes.* Encode the
  resident-reported value (severe). The factor is about what was reported,
  not adjudicated.
- *Mixed levels across heads.* Use the highest level reported for any head
  in the case.

**Polarity:** `pro_claimant` (especially when value is `severe`).

**Source authority:** Housing Act 2004 Part 1 (HHSRS — health impact is the
core severity test for category 1 hazards); Housing Ombudsman Spotlight on
damp and mould (2021) (impact-led assessment).

---

## temporary_decant_or_alternative_offered

**Operational definition:** The landlord offered, arranged, or paid for
temporary alternative accommodation, a decant, or a comparable alternative
(e.g. hotel stay, move to a void property) while repairs were outstanding.

**Affirmative phrasings:**
- "The landlord offered a hotel for two nights during the works."
- "A decant property was made available."
- "The resident was placed in temporary accommodation while the kitchen was
  refitted."

**Negative phrasings:**
- "No alternative accommodation was discussed."
- "The landlord said decant was not available."
- "The resident asked to be moved but the request was refused."

**Edge cases:**
- *Resident refused a reasonable offer.* Call: **present**. The factor
  records the offer; refusal goes to mitigation/redress reasoning.
- *Decant offered after the repair was complete.* Call: **absent**. The
  alternative must be offered while works were outstanding to be relevant.

**Polarity:** `pro_respondent`

**Source authority:** No direct statutory ground — guidance-derived from
Housing Ombudsman Remedies Guidance (current edition) and Spotlight reports
on temporary accommodation; landlord decant policies.

---

## prior_compensation_or_apology_offered

**Operational definition:** The landlord offered any compensation payment,
goodwill payment, or apology to the resident **before** the Ombudsman issued
the determination. Includes offers refused by the resident.

**Affirmative phrasings:**
- "The landlord offered £250 in compensation at Stage 2."
- "An apology was issued by the housing manager."
- "A goodwill gesture of £100 was paid during the complaint process."

**Negative phrasings:**
- "No compensation or apology was offered."
- "The landlord declined to offer redress until the Ombudsman investigated."
- The narrative does not mention any landlord redress offer. (default to
  **absent**)

**Edge cases:**
- *Apology only, no money.* Call: **present**. Either compensation or
  apology suffices; the factor is disjunctive.
- *Compensation offered only after the Ombudsman opened the case but before
  the determination.* Call: **present**. The cut-off is the determination,
  not the complaint stage.

**Polarity:** `pro_respondent`

**Source authority:** Housing Ombudsman Remedies Guidance (current edition).

---

## issue_outside_jurisdiction

**Operational definition:** The complaint head, or a material part of it,
falls outside the Housing Ombudsman's remit — e.g. a matter properly for
the courts (legal title, possession orders), a matter handled by another
ombudsman, or one expressly excluded by the Scheme.

**Affirmative phrasings:**
- "The Ombudsman determined the matter was outside jurisdiction."
- "The complaint concerned a leasehold dispute reserved to the First-tier
  Tribunal."
- "The issue had been the subject of court proceedings."

**Negative phrasings:**
- The narrative does not raise a jurisdiction question. (default to
  **absent**)
- "The Ombudsman accepted jurisdiction over all heads."
- "Jurisdiction was not in dispute."

**Edge cases:**
- *Some heads in, some heads out.* Call: **present** if any material head
  is excluded. The case may still proceed on the remaining heads.
- *Pre-Ombudsman complaint stage not exhausted.* This is a procedural bar,
  not a jurisdiction one. Call: **absent** (the complaint can be referred
  back, then re-opened).

**Polarity:** `neutral`

**Source authority:** Housing Ombudsman Scheme ¶39 (matters outside
Ombudsman remit that may be declined).
