"""
Fact extraction prompts.

Prompts for extracting structured facts from conversation text.
"""

FACT_EXTRACTION_PROMPT = """You are a legal information extraction system. Your task is to extract structured facts from a conversation about a tenancy deposit dispute.

Given a user message and the current case file state, extract any new information mentioned.

EXTRACTION RULES:
1. Only extract information explicitly stated or clearly implied
2. Assign confidence scores (0.0-1.0) based on how clearly stated the information is
3. Don't infer information that wasn't mentioned
4. If the user is uncertain about something, reflect that in the confidence score
5. Extract dates in YYYY-MM-DD format when possible
6. Extract monetary amounts as numbers without currency symbols

CATEGORIES TO EXTRACT:

**Property Details:**
- address: Full property address
- postcode: UK postcode
- property_type: flat, house, room, HMO
- num_bedrooms: Number of bedrooms
- furnished: Whether property was furnished

**Tenancy Details:**
- start_date: When tenancy began
- end_date: When tenancy ended/ends
- monthly_rent: Monthly rent amount
- tenancy_type: AST, periodic, etc.

**Deposit Details:**
- deposit_amount: Total deposit paid
- deposit_protected: true/false/unknown
- deposit_scheme: TDS, DPS, MyDeposits, or unknown
- protection_date: When deposit was protected
- prescribed_info_provided: true/false/unknown

**Issues:**
Extract each distinct issue as:
- issue_type: cleaning, damage, rent_arrears, deposit_protection, etc.
- description: Brief description of the issue
- disputed: Whether this is disputed

**Evidence:**
Extract mentioned evidence as:
- evidence_type: inventory_checkin, inventory_checkout, photos_before, photos_after, receipts, correspondence, tenancy_agreement
- description: What the evidence shows
- available: true/false

**Claims:**
Extract specific monetary claims:
- claimant: tenant or landlord
- issue: What the claim is for
- amount: Amount claimed

**Events:**
Extract key events with dates:
- event_type: inspection, damage_discovered, complaint_made, etc.
- date: When it happened (if known)
- description: What happened

OUTPUT FORMAT:
Return a JSON object with the extracted information. Only include fields where you found information.
Include a "confidence" field (0.0-1.0) for each extracted value.

Example output:
{
    "property": {
        "address": {"value": "123 Main Street, London", "confidence": 0.95},
        "postcode": {"value": "SW1A 1AA", "confidence": 0.9}
    },
    "tenancy": {
        "deposit_amount": {"value": 1200, "confidence": 1.0},
        "deposit_protected": {"value": false, "confidence": 0.8}
    },
    "issues": [
        {"issue_type": "cleaning", "description": "Professional cleaning charges", "confidence": 0.9}
    ],
    "no_new_info": false
}

If no new relevant information was found, return:
{"no_new_info": true}
"""


FACT_EXTRACTION_CONTEXT = """Current case file state:
{case_file_summary}

Current conversation stage: {current_stage}

User message to extract from:
"{user_message}"

Extract any NEW information from this message that isn't already in the case file.
Focus on information relevant to the current stage: {stage_focus}
"""


STAGE_EXTRACTION_FOCUS = {
    "greeting": "user's role (tenant/landlord) and initial description of the dispute",
    "basic_details": "property address, postcode, property type, move-in and move-out dates",
    "tenancy_details": "rent amount, tenancy type, written agreement status",
    "deposit_details": "deposit amount, protection scheme, protection date, prescribed information",
    "issue_identification": "specific dispute issues (cleaning, damage, etc.) and whether they're disputed",
    "evidence_collection": "types of evidence available (inventories, photos, receipts, correspondence)",
    "claim_amounts": "specific monetary amounts claimed by each party",
    "narrative": "additional context, timeline of events, communication history",
    "confirmation": "corrections or additions to previously collected information",
}


EXTRACTION_VALIDATION_PROMPT = """Validate the extracted information for consistency and completeness.

Extracted data:
{extracted_data}

Check for:
1. Logical consistency (e.g., end date after start date)
2. Reasonable values (e.g., deposit typically 4-6 weeks rent)
3. Missing critical information for the current stage
4. Contradictions with previously collected data

Return validation result:
{
    "is_valid": true/false,
    "issues": ["list of any issues found"],
    "suggestions": ["suggested follow-up questions"]
}
"""
