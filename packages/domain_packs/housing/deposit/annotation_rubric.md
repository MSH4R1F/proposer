# Housing Deposit v1 — Annotation Rubric

> Spec: `docs/superpowers/specs/2026-05-06-factor-proposition-kg-controlled-cbr-rag.md` §19 PR 4
> Domain pack version: v1
>
> This rubric is the binding reference for both LLM annotators and human
> reviewers labelling factor presence in tenancy-deposit narratives. Each
> section below mirrors one factor in `factors.yaml` (3 in total). Heading IDs
> are bare (no prefix) so the test can match them to the canonical factor IDs
> verbatim.

---

## deposit_protection_status

**Operational definition:** Whether the landlord protected the tenant's
deposit in a Tenancy Deposit Protection (TDP) scheme on time, late, or never.
The 30-day statutory window runs from receipt of the deposit (Housing Act
2004 ss213-215).

**Enum values:**
- `protected_on_time` — registered with a recognised scheme within 30 days.
- `protected_late` — registered with a scheme but more than 30 days after
  receipt.
- `not_protected` — no record of the deposit being registered with any
  scheme as of the dispute date.
- `unknown` — the narrative does not contain the dates needed to decide.

**Affirmative phrasings:**
- "The deposit was protected with the DPS on 12 March."
- "The landlord registered the deposit with MyDeposits within the statutory
  window."

**Negative phrasings:**
- "The landlord did not protect the deposit at any point during the
  tenancy."
- "Protection was effected three months after receipt of the deposit."

**Polarity:** `pro_claimant` (statutory breach when present as
`not_protected` or `protected_late`).

**Source authority:** Housing Act 2004 ss213-215; Tenancy Deposit Schemes
(England) Order 2007.

---

## prescribed_information_status

**Operational definition:** Whether the landlord gave the tenant the
prescribed information (scheme details, contacts, dispute procedure) on
time, late, or never. Same 30-day statutory window as protection itself
(Housing Act 2004 s213(6)(a)).

**Enum values:**
- `provided_on_time` — given to the tenant within 30 days of receipt.
- `provided_late` — given more than 30 days after receipt.
- `not_provided` — never given as of the dispute date.
- `unknown` — narrative lacks the dates needed to decide.

**Affirmative phrasings:**
- "The prescribed information was served on the tenant on 5 April, 14 days
  after the deposit was paid."

**Negative phrasings:**
- "The tenant never received the prescribed information."
- "The prescribed information was first served when the dispute was
  raised."

**Polarity:** `pro_claimant` (statutory breach when not provided on time).

**Source authority:** Housing Act 2004 s213(6); The Housing (Tenancy
Deposits) (Prescribed Information) Order 2007 (SI 2007/797).

---

## check_in_inventory_baseline

**Operational definition:** Whether a check-in inventory exists as a
baseline for damage / cleaning deductions. Without one, the landlord
typically cannot prove condition at the start of the tenancy and most
deduction claims are refused or substantially reduced.

**Enum values:**
- `present` — a check-in inventory was created and signed by both parties
  (or one party plus credible third-party evidence such as photos).
- `absent` — no check-in inventory exists.
- `unknown` — the narrative does not say either way.

**Affirmative phrasings:**
- "A check-in inventory was completed by the agent and signed by the
  tenant."
- "Photographs taken on the move-in date are referenced as the baseline."

**Negative phrasings:**
- "No inventory was carried out at the start of the tenancy."
- "The landlord could not produce any check-in evidence."

**Polarity:** `pro_respondent` (presence supports the landlord's deduction
claim).

**Source authority:** TDP scheme adjudication guidance (e.g. TDS, DPS, and
MyDeposits dispute resolution rules); no direct statutory ground.
