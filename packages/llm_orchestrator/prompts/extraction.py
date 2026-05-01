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
- deposit_received_date: When the landlord or agent received the deposit
- deposit_protected: true/false/unknown
- deposit_scheme: TDS, DPS, MyDeposits, or unknown
- protection_date: When deposit was protected
- prescribed_info_provided: true/false/unknown

**Issues:**
Extract each distinct issue as:
- issue_type: cleaning, damage, rent_arrears, deposit_protection, inventory, garden, redecoration, keys, utilities, fair_wear_and_tear, missing_items, other
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


BULK_EXTRACTION_PROMPT = """You are a legal information extraction system specialising in UK tenancy deposit disputes.

You will receive a COMPLETE case description pasted by a {role}. Your job is to extract ALL structured facts from this text in a single pass.

EXTRACTION RULES:
1. Extract every piece of relevant information — property, tenancy, deposit, issues, evidence, claims, events, narrative
2. Assign confidence scores (0.0-1.0) based on how clearly stated each piece of information is
3. Only extract information explicitly stated or clearly implied — do NOT infer or fabricate
4. Extract dates in YYYY-MM-DD format when possible (convert UK date formats like "1st March 2023" to "2023-03-01")
5. Extract monetary amounts as numbers without currency symbols
6. If the user mentions evidence they have (photos, inventory, emails), extract those as evidence items
7. Preserve the user's full narrative as well as extracting structured fields

CATEGORIES TO EXTRACT:

**Property Details:**
- address: Full property address
- postcode: UK postcode
- property_type: flat, house, room, HMO
- num_bedrooms: Number of bedrooms
- furnished: Whether property was furnished (true/false)

**Tenancy & Deposit Details:**
- start_date: When tenancy began (YYYY-MM-DD)
- end_date: When tenancy ended/ends (YYYY-MM-DD)
- monthly_rent: Monthly rent amount (number)
- tenancy_type: AST, periodic, etc.
- deposit_amount: Total deposit paid (number)
- deposit_received_date: When the landlord or agent received the deposit (YYYY-MM-DD)
- deposit_protected: true/false/null (null if not mentioned)
- deposit_scheme: TDS, DPS, MyDeposits, or null
- protection_date: When deposit was protected (YYYY-MM-DD)
- prescribed_info_provided: true/false/null
- prescribed_info_date: When prescribed information was provided (YYYY-MM-DD)

**Issues** (list of all disputed items):
- issue_type: One of: cleaning, damage, rent_arrears, deposit_protection, inventory, garden, redecoration, keys, utilities, fair_wear_and_tear, missing_items, other
- description: Brief description of the issue
- confidence: How clearly this was stated (0.0-1.0)

**Evidence** (any evidence the user mentions having):
- evidence_type: One of: inventory_checkin, inventory_checkout, photos_before, photos_after, receipts, invoices, correspondence, tenancy_agreement, deposit_certificate, witness_statement, other
- description: What the evidence shows
- confidence: How clearly this was stated (0.0-1.0)

**Claims** (specific monetary amounts):
- claimant: tenant or landlord
- issue: What the claim is for (use issue_type values)
- amount: Amount claimed (number)
- description: Brief description

**Events** (key events with dates):
- event_type: inspection, damage_discovered, complaint_made, deposit_lodged, etc.
- date: When it happened (YYYY-MM-DD, null if unknown)
- description: What happened

**Narrative:**
- A brief summary of the dispute in the user's own words (preserve their perspective)

**Names:**
- tenant_name: Name of the tenant (if mentioned)
- landlord_name: Name of the landlord (if mentioned)
- agent_name: Name of the letting agent (if mentioned)

OUTPUT FORMAT:
Return ONLY a JSON object (no markdown, no explanation). Include all categories where you found information.

Example:
{{
    "property": {{
        "address": {{"value": "42 Oak Lane, London", "confidence": 0.95}},
        "postcode": {{"value": "E1 6BT", "confidence": 0.9}},
        "property_type": {{"value": "flat", "confidence": 0.85}},
        "furnished": {{"value": true, "confidence": 0.7}}
    }},
    "tenancy": {{
        "start_date": {{"value": "2022-06-01", "confidence": 0.9}},
        "end_date": {{"value": "2023-05-31", "confidence": 0.9}},
        "monthly_rent": {{"value": 1500, "confidence": 1.0}},
        "deposit_amount": {{"value": 1500, "confidence": 1.0}},
        "deposit_protected": {{"value": true, "confidence": 0.8}},
        "deposit_scheme": {{"value": "DPS", "confidence": 0.7}}
    }},
    "issues": [
        {{"issue_type": "cleaning", "description": "Landlord deducted £300 for professional cleaning despite property being left clean", "confidence": 0.95}},
        {{"issue_type": "damage", "description": "Scratches on kitchen floor claimed by landlord", "confidence": 0.8}}
    ],
    "evidence": [
        {{"evidence_type": "photos_after", "description": "Photos taken at move-out showing clean property", "confidence": 0.9}},
        {{"evidence_type": "correspondence", "description": "Emails with landlord about deposit deductions", "confidence": 0.85}}
    ],
    "claims": [
        {{"claimant": "landlord", "issue": "cleaning", "amount": 300, "description": "Professional cleaning fee"}},
        {{"claimant": "landlord", "issue": "damage", "amount": 200, "description": "Kitchen floor repair"}}
    ],
    "events": [
        {{"event_type": "tenancy_end", "date": "2023-05-31", "description": "Moved out of property"}},
        {{"event_type": "complaint_made", "date": "2023-06-15", "description": "Received deposit deduction letter"}}
    ],
    "narrative": "Tenant moved out after 1 year, left property clean. Landlord deducted £500 for cleaning and floor damage. Tenant disputes both deductions.",
    "tenant_name": "John Smith",
    "landlord_name": "Mrs. Patel",
    "no_new_info": false
}}
"""


BULK_EXTRACTION_CONTEXT = """The user is a {role} describing their tenancy deposit dispute.

Full case description:
\"\"\"{case_text}\"\"\"

Extract ALL relevant information from this text. Be thorough — this is the user's complete case description provided in one go.
"""


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
