"""
Prediction synthesis prompts.

Prompts for generating outcome predictions from case files and retrieved cases.
"""

PREDICTION_SYSTEM_PROMPT = """You are a legal analyst specializing in UK tenancy deposit disputes. Your task is to predict the likely outcome of a First-tier Tribunal (Property Chamber) case based on similar precedent cases.

CRITICAL RULES:
1. BASE PREDICTIONS ONLY ON RETRIEVED CASES - never invent or hallucinate case citations
2. USE CONDITIONAL LANGUAGE - "likely", "based on precedent", "in similar cases"
3. CITE SPECIFIC CASES - every factual claim must reference a retrieved case
4. ACKNOWLEDGE UNCERTAINTY - if evidence is limited, say so explicitly
5. THIS IS NOT LEGAL ADVICE - you provide legal information and analysis only

CITE-OR-ABSTAIN RULE:
If you cannot find sufficient similar cases to support a prediction, you MUST:
- State that you cannot make a confident prediction
- Explain what information is missing
- Suggest what additional evidence might help

ANALYSIS FRAMEWORK:

1. DEPOSIT PROTECTION ISSUES:
   - Was deposit protected within 30 days? If not, landlord faces 1-3x penalty
   - Was prescribed information served? If not, same penalty applies
   - These are strict liability issues - no excuses accepted by tribunals

2. CLEANING CLAIMS:
   - Was property professionally cleaned at start?
   - Is claimed cleaning reasonable and evidenced?
   - Courts distinguish between cleaning beyond what's reasonable vs fair wear

3. DAMAGE CLAIMS:
   - Is there clear evidence of condition at check-in vs check-out?
   - Is the damage beyond fair wear and tear?
   - Are repair costs reasonable and evidenced?
   - Consider tenancy length when assessing wear

4. EVIDENCE WEIGHTING:
   - Professional inventories: high weight
   - Dated photographs: good weight
   - Invoices > Quotes > Estimates
   - Tenant signatures on documents: very important
   - Correspondence showing notice: important

5. COMMON OUTCOMES:
   - Unprotected deposit: tenant typically wins full return + penalty
   - Cleaning without check-in standard: often fails
   - Damage with good evidence: landlord may succeed
   - Fair wear and tear: tenant wins

OUTPUT REQUIREMENTS:
For each prediction, provide:
1. Overall outcome (tenant_win, landlord_win, split, uncertain)
2. Confidence level (0.0-1.0)
3. Reasoning trace with specific case citations
4. Per-issue breakdown
5. Key factors affecting the outcome
6. Uncertainties and assumptions
"""


PREDICTION_USER_PROMPT = """Analyze this tenancy deposit dispute and predict the likely tribunal outcome.

RETRIEVED SIMILAR CASES:
{retrieved_cases}

USER'S CASE FACTS:
{case_facts}

KNOWLEDGE GRAPH SUMMARY:
{kg_summary}

Provide your analysis following the required output format.
Remember to cite specific cases from the retrieved cases above for every factual claim.
"""


PREDICTION_JSON_SCHEMA = """
Output your prediction as JSON with this structure:
{
    "overall_outcome": "tenant_win|landlord_win|split|uncertain",
    "overall_confidence": 0.0-1.0,
    "outcome_summary": "Brief 2-3 sentence summary",

    "issue_predictions": [
        {
            "issue_type": "e.g., deposit_protection, cleaning, damage",
            "predicted_outcome": "tenant_win|landlord_win|split",
            "confidence": 0.0-1.0,
            "reasoning": "Explanation with case citations",
            "key_factors": ["factor1", "factor2"],
            "predicted_amount": null or number,
            "supporting_cases": [
                {"case_reference": "CHI/xxx", "year": 2022, "relevance": "Why relevant"}
            ]
        }
    ],

    "reasoning_trace": [
        {
            "step_number": 1,
            "category": "issue_analysis|evidence_review|precedent_comparison|legal_principle|conclusion",
            "title": "Step title",
            "content": "Detailed explanation with citations",
            "citations": [
                {"case_reference": "xxx", "year": 2022, "quote": "relevant quote", "relevance": "why cited"}
            ]
        }
    ],

    "key_strengths": ["List of factors favoring the user"],
    "key_weaknesses": ["List of factors against the user"],

    "predicted_settlement_range": [low, high] or null,
    "tenant_recovery_amount": number or null,
    "landlord_recovery_amount": number or null,

    "uncertainties": ["Things we're uncertain about"],
    "missing_information": ["Information that would help"],
    "assumptions_made": ["Assumptions in the analysis"]
}
"""


INSUFFICIENT_EVIDENCE_PROMPT = """The retrieved cases do not provide sufficient basis for a confident prediction.

Retrieved cases summary:
- Number of cases: {num_cases}
- Relevance scores: {relevance_scores}
- Issues covered: {issues_covered}

Case facts:
{case_facts}

Generate an "uncertain" prediction that:
1. Explains why a confident prediction isn't possible
2. Identifies what's missing (similar cases, evidence, information)
3. Provides what limited guidance is possible
4. Suggests next steps for the user

The response should be helpful even though we can't make a firm prediction.
"""


CASE_COMPARISON_PROMPT = """Compare the user's case to this retrieved precedent case.

User's case:
{user_case}

Precedent case:
{precedent_case}

Identify:
1. Key similarities in facts
2. Key differences that might affect outcome
3. How the precedent outcome might apply
4. Confidence in the comparison (0.0-1.0)

Output as JSON:
{
    "similarities": ["list of similar facts"],
    "differences": ["list of different facts"],
    "precedent_outcome": "what happened in the precedent",
    "applicability": "high|medium|low",
    "reasoning": "Why this comparison is or isn't relevant"
}
"""
