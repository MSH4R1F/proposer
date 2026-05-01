"""LLM prompts for transcript → KG extraction (SHA-34).

The model receives the intake transcript (or assembled CaseFile narrative)
and emits a JSON document of typed Event nodes, Evidence→Claim support
edges, and optional Issue refinements. Output is Pydantic-validated, then
KGValidator (SHA-35) gets the final say.

This complements `extraction.py` (which produces a CaseFile) — SHA-34 takes
the CaseFile-derived KG (from GraphBuilder) and enriches it with temporal
events and evidence-claim links the structured CaseFile schema can't
capture cleanly.
"""

KG_EXTRACTION_SYSTEM_PROMPT = """You are a legal-fact extractor for UK tenancy deposit disputes.

You receive a transcript of an intake conversation (and optionally a
summary of the case file already extracted). Your job is to identify:

1. TIMELINE EVENTS the user mentions, with dates when known.
2. EVIDENCE → CLAIM links — which piece of evidence supports which monetary claim.

Critical rules:
- Only extract facts the transcript explicitly states. NEVER infer beyond the text.
- Assign a confidence score 0.0–1.0 to every extracted item.
- For events: use ISO date format YYYY-MM-DD when an explicit date is given. Omit the date field if the user is vague (e.g. "last summer").
- For evidence→claim links: only emit a link when the user explicitly tied a piece of evidence to a specific monetary claim. Do NOT speculate.
- DO NOT extract Party / Property / Lease facts — those go through the regular CaseFile extractor.

Hard temporal-logic constraints (the validator will REJECT outputs that violate these):
- An event's date cannot be before the tenancy start date when the event_type is anything other than 'tenancy_start', 'deposit_paid', 'deposit_lodged', 'deposit_received', or 'deposit_protected'.
- A deposit_protected event cannot be before the deposit was paid or received. The 30-day deadline runs from deposit receipt, not tenancy start.

If you would need to violate these constraints to fit the user's account, leave the date off the event and lower its confidence to <0.5.

Output as a single valid JSON object. No markdown fences.
"""


KG_EXTRACTION_USER_PROMPT = """CASE CONTEXT:
{case_summary}

TRANSCRIPT:
{transcript}

Extract events and evidence→claim links as JSON:

{{
  "events": [
    {{
      "event_type": "<one of: tenancy_start | tenancy_end | inspection | damage_discovered | complaint_made | repair_requested | deposit_paid | deposit_protected | deposit_returned | notice_served | check_out | mediation_started | other>",
      "date": "YYYY-MM-DD or null",
      "description": "<short factual description>",
      "actors": ["tenant" | "landlord" | "agent", ...],
      "confidence": <float 0.0-1.0>
    }}
  ],
  "evidence_supports_claims": [
    {{
      "evidence_description": "<short — match an existing evidence item from the case file>",
      "claim_description": "<short — match an existing claim from the case file>",
      "claimant": "tenant" | "landlord",
      "confidence": <float 0.0-1.0>
    }}
  ],
  "no_new_info": false
}}

If nothing extractable, return: {{ "events": [], "evidence_supports_claims": [], "no_new_info": true }}
"""
