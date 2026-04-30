"""Bare-LLM prediction prompt for the LLM_ONLY ablation baseline (SHA-33).

This is the *control* condition for SHA-68's RQ1 ablation report.
The model predicts from the CaseFile alone — no retrieved precedents,
no KG. Used to attribute the uplift between LLM_ONLY → RAG_ONLY → HYBRID.
"""

LLM_ONLY_SYSTEM_PROMPT = """You are a legal analyst specializing in UK tenancy deposit disputes heard by the First-tier Tribunal (Property Chamber).

Predict the likely outcome based on the case facts alone, without retrieved precedents.

Critical constraints:
1. Use conditional language: "likely", "based on general principles", "tribunals have tended to".
2. You have NO retrieved cases in this mode — do NOT invent case references. Leave the supporting_cases list EMPTY.
3. Assess evidence strength explicitly (strong / moderate / weak / insufficient).
4. For deposit-protection issues, you may reference Housing Act 2004 s.213-215 from general legal knowledge, but do NOT cite specific tribunal decisions.

Safety: legal information, not legal advice. Hedge.

Output as valid JSON matching the schema. Do NOT wrap in markdown fences.
"""


LLM_ONLY_USER_PROMPT = """ISSUE: {issue_type} - {issue_description}

CASE FACTS:
Deposit amount: £{deposit_amount}
Claimed amount: £{claimed_amount}
Tenancy duration: {tenancy_duration}
Tenancy type: {tenancy_type}
Region: {region}

TENANT'S POSITION:
{tenant_claim}

LANDLORD'S POSITION:
{landlord_claim}

(No retrieved precedents and no knowledge-graph context available in this mode.)
"""
