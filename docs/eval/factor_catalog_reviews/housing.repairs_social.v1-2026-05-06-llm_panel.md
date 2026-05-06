# §22.1 Factor Catalog Panel Review

## Panel Composition

| # | Panelist ID |
|---|-------------|
| 1 | `openai:gpt-4.1` |
| 2 | `openai:gpt-4o` |
| 3 | `openai:gpt-4o-mini` |

- **Domain:** `housing.repairs_social.v1`
- **Date:** 2026-05-06
- **Catalog SHA (first 16 hex):** `bf73c58077b693fa`
- **Factor count:** 15
- **Panelist count:** 3

---

## Per-Panelist Raw Output

### Panelist: `openai:gpt-4.1`

**Overall notes:** Catalog is unusually thorough and precisely operationalised. Strong separation of report/notice/attempted action makes for high reliability. However, real Housing Ombudsman fact patterns often feature inadequately addressed or recurrent repairs; catalog covers delay and presence of repair attempts, but not explicit adequacy/quality of repairs or recurrence (persistent/repeat disrepair after claimed fix). No factor for resident refusing access or otherwise preventing repair (mitigation/tenant-side contributory behaviour), though such failure is a common finding. No specific factor for offer of follow-up inspection or remedy where initial fix is disputed — relevant for no maladministration or reasonable redress findings. Final note: If a complaint is resolved after intervention but before determination, current factors may not capture this outcome fully.

**Missing factors suggested:**
- repair_quality_adequate
- offer_of_reinspection
- mitigation_by_resident

**Per-factor findings:**

| Factor ID | Labelable | Def Clear | Polarity OK | Authority | Redundant | Flags |
|-----------|-----------|-----------|-------------|-----------|-----------|-------|
| `repair_responsibility_established` | ✓ | ✓ | ✓ | ✓ | — | — |
| `hazard_or_disrepair_reported` | ✓ | ✓ | ✓ | ✓ | — | — |
| `landlord_notice_established` | ✓ | ✓ | ✓ | ✓ | — | — |
| `inspection_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `inspection_delay_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `repair_attempted` | ✓ | ✓ | ✓ | ✓ | — | — |
| `repair_delay_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `records_inadequate` | ✓ | ✓ | ✓ | ✓ | — | — |
| `communication_gap_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `complaint_response_delay_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `vulnerability_known` | ✓ | ✓ | ✓ | ✓ | — | — |
| `impact_severity_reported` | ✓ | ✓ | ✓ | ✓ | — | Potential ambiguity when multiple impacts reported; rubric tells to take highest, but in cases with several heads or causes, the clarity of what constitutes 'highest' may depend on narrative clarity. |
| `temporary_decant_or_alternative_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `prior_compensation_or_apology_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `issue_outside_jurisdiction` | ✓ | ✓ | ✓ | ✓ | — | Rubric says 'material part' of complaint must be outside; some borderline cases possible if complaint is mixed — could be clearer if partial jurisdiction cases must always be flagged as present. |

### Panelist: `openai:gpt-4o`

**Overall notes:** The factor catalog is comprehensive and well-aligned with UK housing and employment law, statutes, and Ombudsman guidance. All factors appear labelable solely from case narratives with clear and grounded operational definitions. No redundancy detected among factors. No missing factors were suggested by the corpus excerpts.

**Per-factor findings:**

| Factor ID | Labelable | Def Clear | Polarity OK | Authority | Redundant | Flags |
|-----------|-----------|-----------|-------------|-----------|-----------|-------|
| `repair_responsibility_established` | ✓ | ✓ | ✓ | ✓ | — | — |
| `hazard_or_disrepair_reported` | ✓ | ✓ | ✓ | ✓ | — | — |
| `landlord_notice_established` | ✓ | ✓ | ✓ | ✓ | — | — |
| `inspection_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `inspection_delay_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `repair_attempted` | ✓ | ✓ | ✓ | ✓ | — | — |
| `repair_delay_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `records_inadequate` | ✓ | ✓ | ✓ | ✓ | — | — |
| `communication_gap_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `complaint_response_delay_days` | ✓ | ✓ | ✓ | ✓ | — | — |
| `vulnerability_known` | ✓ | ✓ | ✓ | ✓ | — | — |
| `impact_severity_reported` | ✓ | ✓ | ✓ | ✓ | — | — |
| `temporary_decant_or_alternative_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `prior_compensation_or_apology_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `issue_outside_jurisdiction` | ✓ | ✓ | ✓ | ✓ | — | — |

### Panelist: `openai:gpt-4o-mini`

**Overall notes:** The factor catalog is generally sound, but several factors have no direct statutory grounding, relying solely on guidance interpretation. Consider enhancing clarity on authority for factors without direct statutory basis.

**Per-factor findings:**

| Factor ID | Labelable | Def Clear | Polarity OK | Authority | Redundant | Flags |
|-----------|-----------|-----------|-------------|-----------|-----------|-------|
| `repair_responsibility_established` | ✓ | ✓ | ✓ | ✓ | — | — |
| `hazard_or_disrepair_reported` | ✓ | ✓ | ✓ | ✓ | — | — |
| `landlord_notice_established` | ✓ | ✓ | ✓ | ✓ | — | — |
| `inspection_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `inspection_delay_days` | ✓ | ✓ | ✓ | ✗ | — | No direct statutory ground identified. |
| `repair_attempted` | ✓ | ✓ | ✓ | ✓ | — | — |
| `repair_delay_days` | ✓ | ✓ | ✓ | ✗ | — | No direct statutory ground identified. |
| `records_inadequate` | ✓ | ✓ | ✓ | ✗ | — | No statutory ground; guidance-derived. |
| `communication_gap_days` | ✓ | ✓ | ✓ | ✗ | — | No direct statutory ground identified. |
| `complaint_response_delay_days` | ✓ | ✓ | ✓ | ✗ | — | No direct statutory ground identified. |
| `vulnerability_known` | ✓ | ✓ | ✓ | ✓ | — | — |
| `impact_severity_reported` | ✓ | ✓ | ✓ | ✓ | — | — |
| `temporary_decant_or_alternative_offered` | ✓ | ✓ | ✓ | ✗ | — | No direct statutory ground identified. |
| `prior_compensation_or_apology_offered` | ✓ | ✓ | ✓ | ✓ | — | — |
| `issue_outside_jurisdiction` | ✓ | ✓ | ✓ | ✓ | — | — |

---

## Disagreement Matrix

Legend: **U** = unanimous flag, **M** = majority flag, **S** = single flag, **—** = clean

| Factor ID | Consensus | openai:gpt-4.1 | openai:gpt-4o | openai:gpt-4o-mini |
|---|---|---|---|---|
| `repair_responsibility_established` | — | — | — | — |
| `hazard_or_disrepair_reported` | — | — | — | — |
| `landlord_notice_established` | — | — | — | — |
| `inspection_offered` | — | — | — | — |
| `inspection_delay_days` | **S** | — | — | authority_grounded, other_flags |
| `repair_attempted` | — | — | — | — |
| `repair_delay_days` | **S** | — | — | authority_grounded, other_flags |
| `records_inadequate` | **S** | — | — | authority_grounded, other_flags |
| `communication_gap_days` | **S** | — | — | authority_grounded, other_flags |
| `complaint_response_delay_days` | **S** | — | — | authority_grounded, other_flags |
| `vulnerability_known` | — | — | — | — |
| `impact_severity_reported` | **S** | other_flags | — | — |
| `temporary_decant_or_alternative_offered` | **S** | — | — | authority_grounded, other_flags |
| `prior_compensation_or_apology_offered` | — | — | — | — |
| `issue_outside_jurisdiction` | **S** | other_flags | — | — |

---

## Unanimous-Flag Summary

_No factors unanimously flagged by all panelists._

### Majority Flags (≥2 panelists, not unanimous)

_None._

### Single Flags (1 panelist)

- **`inspection_delay_days`** (by `openai:gpt-4o-mini`): authority_grounded, other_flags
- **`repair_delay_days`** (by `openai:gpt-4o-mini`): authority_grounded, other_flags
- **`records_inadequate`** (by `openai:gpt-4o-mini`): authority_grounded, other_flags
- **`communication_gap_days`** (by `openai:gpt-4o-mini`): authority_grounded, other_flags
- **`complaint_response_delay_days`** (by `openai:gpt-4o-mini`): authority_grounded, other_flags
- **`impact_severity_reported`** (by `openai:gpt-4.1`): other_flags
- **`temporary_decant_or_alternative_offered`** (by `openai:gpt-4o-mini`): authority_grounded, other_flags
- **`issue_outside_jurisdiction`** (by `openai:gpt-4.1`): other_flags

---

## Cost Report

| Metric | Value |
|--------|-------|
| Total tokens in | 22,226 |
| Total tokens out | 3,046 |
| Estimated cost (USD) | $0.000000 |
| Estimated cost (GBP) | £0.000000 |

**Per-panelist breakdown:**

| Model | Provider | Tokens in | Tokens out | Cost (USD) |
|-------|----------|-----------|------------|------------|
| `gpt-4.1` | openai | 7,409 | 1,242 | $0.000000 |
| `gpt-4o` | openai | 7,408 | 745 | $0.000000 |
| `gpt-4o-mini` | openai | 7,409 | 1,059 | $0.000000 |

_Estimated costs are approximate; exchange rate fixed at 0.80 USD/GBP._

---

## Reviewer Prompt

```
You are a skeptical UK housing/employment paralegal reviewing a junior associate's draft factor catalog for a hybrid RAG + KG legal-prediction system. Your job is to flag every plausible problem.

You will receive:
1. A factor catalog (YAML) defining the legal factors to be extracted from case narratives.
2. The annotation rubric explaining how each factor is operationalised.
3. The closed outcome ID set the factors map to.
4. 3-5 corpus narrative excerpts (with determinations stripped) — these are realistic inputs the catalog must handle.

For EACH factor in the catalog, answer these six questions:

A. Labelability: Can this factor be assigned by reading the narrative ALONE — without reading the determination paragraph? If not, it's leaking the outcome. Yes/No, with brief reasoning if No.

B. Operational definition: Is the rubric definition specific enough that two annotators reading only the rubric would agree on borderline cases? If ambiguous, name the ambiguity.

C. Polarity check: Does the declared polarity (pro_claimant / pro_respondent / neutral) match how UK case law and Ombudsman practice actually treat this fact pattern? If wrong, give the correct polarity.

D. Authority alignment: Which statute / Ombudsman scheme provision / ACAS code / official guidance grounds this factor? If you can't identify any real ground, flag it. Do NOT fabricate citations — if you don't know, say so.

E. Redundancy: Does this factor duplicate or substantially overlap another factor in the catalog? Name the duplicate(s).

F. Other concerns: Anything else (vague language, hidden assumptions, biased framing, etc.)

THEN at the end: List any IMPORTANT FACTORS MISSING from the catalog that the corpus excerpts suggest are needed.

Output STRICTLY as JSON matching this schema:
{
  "panelist_id": "<your model identifier>",
  "per_factor_findings": [
    {
      "factor_id": "...",
      "labelable_from_narrative": true,
      "definition_clear": true,
      "polarity_correct": true,
      "authority_grounded": true,
      "redundant_with": [],
      "flags": ["..."]
    }
  ],
  "missing_factors_suggested": ["..."],
  "overall_notes": "..."
}

Be rigorous. Bad work is worse than no work.
```

---

## Adjudication (Mohamed, 2026-05-06)

### Decisions on flagged factors

**Unanimous flags:** None. No must-address items per §22.1.

**Majority flags:** None.

**Single flags (8 total — adjudication below):**

| Factor | Panelist | Flag | Decision | Rationale |
|---|---|---|---|---|
| `inspection_delay_days` | gpt-4o-mini | authority_grounded | **Reject (false positive)** | Rubric already explicitly states "no direct statutory ground — guidance-derived" for this factor. The flag misreads the rubric. |
| `repair_delay_days` | gpt-4o-mini | authority_grounded | **Reject (false positive)** | Same as above. |
| `records_inadequate` | gpt-4o-mini | authority_grounded | **Reject (false positive)** | Rubric cites Housing Ombudsman KIM Spotlight (2023) — guidance-derived as declared. |
| `communication_gap_days` | gpt-4o-mini | authority_grounded | **Reject (false positive)** | Rubric explicitly marks as guidance-derived. |
| `complaint_response_delay_days` | gpt-4o-mini | authority_grounded | **Reject (false positive)** | Rubric cites Complaint Handling Code 2024 timings — that IS the authority. |
| `temporary_decant_or_alternative_offered` | gpt-4o-mini | authority_grounded | **Reject (false positive)** | Rubric cites Remedies Guidance + Spotlight reports as guidance-derived. |
| `impact_severity_reported` | gpt-4.1 | other_flags (multi-impact ambiguity) | **Accept — rubric sharpened** | See Revision 1 above. |
| `issue_outside_jurisdiction` | gpt-4.1 | other_flags (partial-jurisdiction edge) | **Accept — rubric sharpened** | See Revision 2 above. |

### Decisions on missing-factor suggestions (gpt-4.1 only)

| Suggested factor | Decision | Rationale |
|---|---|---|
| `repair_quality_adequate` | **Defer to v2** | Real gap; "repair_attempted" only counts presence not adequacy. Documented as v2 candidate in factors.yaml. |
| `offer_of_reinspection` | **Defer to v2** | Partially overlaps `inspection_offered` (which counts attempts). Documented as v2 candidate. |
| `mitigation_by_resident` | **Defer to v2** | Real and important (especially for "no maladministration due to access refusal" patterns). Documented as v2 candidate. |

### Methodology limitation

This panel was 3 different OpenAI models (gpt-4.1, gpt-4o, gpt-4o-mini) — not a multi-provider panel. Anthropic credits were exhausted at run time. The panel composition is therefore less diverse than the §22.1 protocol calls for. Re-run with mixed Anthropic + OpenAI panelists when credits are restored.

### Catalog SHA after revisions

To be computed after applying Revisions 1-3.
