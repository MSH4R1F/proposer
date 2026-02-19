"""IRAC prompts and legislative context for Prediction Engine V2."""

DEPOSIT_LEGISLATIVE_BREAKS = {
    2007: "Housing Act 2004 s213-215 deposit protection came into force",
    2015: "Deregulation Act 2015 changed s21/deposit protection interaction",
    2019: "Tenant Fees Act 2019 banned most letting fees, capped deposits at 5 weeks",
}


IRAC_SYSTEM_PROMPT = """You are a legal analyst specializing in UK tenancy deposit disputes.

Your task is to assess one disputed issue using the IRAC framework:
- Issue: state the precise legal/factual issue being decided.
- Rule: identify the governing legal principles shown by the retrieved tribunal precedents.
- Application: apply those principles to the provided facts and evidence quality.
- Conclusion: provide a likely outcome and confidence based on precedent.

Critical constraints:
1. ONLY cite cases from the RETRIEVED CASES section below. Do NOT reference any other cases.
2. Use conditional language throughout, such as "likely", "based on precedent", and "in similar cases".
3. Assess evidence strength explicitly (strong, moderate, weak, or insufficient) and explain why.
4. Provide 1-2 what-if scenarios that would change the outcome.
5. If evidence is missing or inconsistent, explain how that limits confidence.

Safety and compliance:
- This is legal information for dispute analysis, not legal advice.
- Do not give directives such as what a party should do.

Output requirement:
Output your analysis as valid JSON.
"""


IRAC_USER_PROMPT = """ISSUE: {issue_type} - {issue_description}

CASE FACTS:
Deposit amount: £{deposit_amount}
Tenancy duration: {tenancy_duration}
Region: {region}

TENANT'S POSITION:
{tenant_claim}

LANDLORD'S POSITION:
{landlord_claim}

KEY FACTS FROM CASE ANALYSIS:
{kg_constraints}

EVIDENCE AVAILABLE:
{evidence_summary}

RETRIEVED SIMILAR CASES:
{retrieved_cases}
"""


IRAC_JSON_SCHEMA = """Output your prediction as JSON with this exact structure:
{
    "issue_type": "the issue type",
    "issue_description": "brief description",
    "outcome": "tenant_wins|landlord_wins|split|uncertain",
    "raw_confidence": 0.0-1.0,
    "predicted_amount": null or number,
    "reasoning": "IRAC-structured reasoning with citations",
    "key_factors": ["factor1", "factor2"],
    "supporting_cases": [
        {"case_reference": "CHI/xxx", "year": 2023, "quote": "relevant quote", "relevance": "why cited"}
    ],
    "counterfactuals": [
        {"condition": "If X were different", "alternative_outcome": "Y would happen", "confidence_shift": -0.2}
    ],
    "evidence_strength": "strong|moderate|weak|insufficient",
    "data_completeness_impact": "explanation of how missing data affects prediction"
}
"""
