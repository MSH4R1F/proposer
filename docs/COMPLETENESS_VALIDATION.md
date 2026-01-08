# Completeness Validation - Required Field Enforcement

## Overview

This document explains the **strict completeness validation** system that ensures users provide ALL required information before generating predictions.

## Problem Statement (Before)

Previously, the system allowed predictions when completeness reached **70%**, which meant:
- ❌ Predictions could be generated with missing required fields
- ❌ Users weren't clearly told what information was still needed
- ❌ Prediction quality suffered from incomplete data
- ❌ The 70% threshold was arbitrary and included optional fields

## Solution (After)

Now the system enforces **100% of required fields** before enabling predictions:
- ✅ Predictions blocked until ALL required fields are present
- ✅ Clear visibility into exactly what's missing
- ✅ Agent proactively prompts for missing required fields
- ✅ Better prediction quality with complete data

---

## Required Fields

The system requires exactly **5 critical fields** before allowing predictions:

| Field | Example | Why Required |
|-------|---------|--------------|
| **Property Address** | "123 Main St, London" | Identifies property for case context |
| **Tenancy Start Date** | "2023-01-15" | Establishes timeline for dispute |
| **Deposit Amount** | £1500 | Core amount in dispute |
| **Dispute Issues** | ["cleaning", "damage"] | What is being disputed |
| **Deposit Protected?** | Yes/No | Critical legal requirement (Section 213) |

### Optional Fields (Improve Predictions but Not Required)

- Tenancy end date
- Property postcode
- Evidence items
- Claimed amounts
- Narrative descriptions

---

## Implementation Details

### 1. Backend: CaseFile Model (`case_file.py`)

Added three new methods for strict validation:

```python
def has_all_required_info(self) -> bool:
    """
    Check if ALL required fields are present.
    Returns True only if every required field has a value.
    """
    missing = self.get_missing_required_info()
    return len(missing) == 0

def is_ready_for_prediction(self) -> bool:
    """
    Determine if case file is ready for prediction generation.
    Requires ALL required fields to be present (100%).
    """
    return self.has_all_required_info()
```

**Before**: `completeness_score >= 0.7` → Could be 70% with missing required fields  
**After**: `has_all_required_info() == True` → Must have 100% of required fields

### 2. Backend: PredictionService (`prediction_service.py`)

Updated `check_case_ready()` to enforce strict validation:

```python
async def check_case_ready(self, case_id: str) -> Dict[str, Any]:
    """
    NOW ENFORCES: ALL required fields must be present (100% of required info).
    Predictions are blocked until every required field has a value.
    """
    case_file.calculate_completeness()
    missing = case_file.get_missing_required_info()
    
    # STRICT VALIDATION: Require ALL required fields (not just 70%)
    is_ready = case_file.has_all_required_info()
    
    return {
        "exists": True,
        "is_complete": is_ready,  # Only true if ALL required fields present
        "completeness": case_file.completeness_score,
        "missing_info": missing,
    }
```

### 3. Backend: IntakeService (`intake_service.py`)

Enhanced message processing to validate after each message:

```python
# Process the message through the agent
response, updated_conversation = await self.agent.process_message(
    conversation, message
)

# Update intake_complete flag based on ALL required fields being present
case_file = updated_conversation.case_file
case_file.calculate_completeness()
missing_required = case_file.get_missing_required_info()

# Mark as complete ONLY if ALL required fields are present
if case_file.has_all_required_info() and not case_file.intake_complete:
    case_file.intake_complete = True
    logger.info("intake_marked_complete_all_required_fields_present")
```

Updated suggested actions:

```python
def _get_suggested_actions(self, conversation: ConversationState) -> List[str]:
    """
    Only suggest prediction if ALL required fields are present.
    """
    if cf.has_all_required_info():
        actions.append("Generate prediction")
    else:
        missing = cf.get_missing_required_info()
        if missing:
            actions.append(f"Complete required info: {', '.join(missing)}")
    return actions
```

### 4. Backend: IntakeAgent (`intake_agent.py`)

Enhanced response context to proactively prompt for missing fields:

```python
def _build_response_context(self, conversation: ConversationState, stage_guidance: str) -> str:
    """Build context for response generation."""
    
    # Add missing required info with PRIORITY
    missing = cf.get_missing_required_info()
    if missing:
        context_parts.append(
            f"\n⚠️ REQUIRED INFO STILL MISSING (must collect before prediction): {', '.join(missing)}"
        )
        context_parts.append(
            "INSTRUCTION: Proactively ask for ONE of the missing required fields in your next question."
        )
    else:
        context_parts.append(
            "\n✓ ALL REQUIRED INFORMATION COLLECTED - User can now generate prediction!"
        )
    
    return "\n".join(context_parts)
```

**Impact**: The LLM agent now sees clear instructions to ask for missing required fields.

### 5. Frontend: IntakeSidebar Component (`IntakeSidebar.tsx`)

Added visual alert for missing required information:

```tsx
{/* Missing Required Information Alert */}
{caseFile?.missing_info && caseFile.missing_info.length > 0 && (
  <div className="px-3 pb-3">
    <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
      <div className="flex items-start gap-2">
        <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-amber-900">
            Required Information Missing
          </p>
          <ul className="text-[11px] text-amber-800 space-y-1">
            {caseFile.missing_info.map((item, index) => (
              <li key={index}>• {item}</li>
            ))}
          </ul>
          <p className="text-[10px] text-amber-700 mt-2 italic">
            Please provide this information to generate a prediction
          </p>
        </div>
      </div>
    </div>
  </div>
)}

{/* Success Message when all required fields collected */}
{caseFile?.missing_info && caseFile.missing_info.length === 0 && completeness >= 0.7 && (
  <div className="px-3 pb-3">
    <div className="p-2.5 rounded-lg bg-success/10 border border-success/20">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-success">
            All Required Info Collected!
          </p>
          <p className="text-[10px] text-muted-foreground">
            Ready to generate prediction
          </p>
        </div>
      </div>
    </div>
  </div>
)}
```

### 6. Frontend: useChat Hook (`useChat.ts`)

Updated completeness logic to use strict validation:

```typescript
// Check if ALL required fields are present (strict validation)
const hasAllRequiredInfo = state.caseFile?.missing_info 
  ? state.caseFile.missing_info.length === 0 
  : false;

return {
  ...state,
  // STRICT: Only complete if ALL required fields are present
  isComplete: hasAllRequiredInfo,
  // Can only generate prediction when ALL required info collected
  canGeneratePrediction: hasAllRequiredInfo && 
    (state.dispute === null || state.dispute.is_ready_for_prediction),
};
```

**Before**: `isComplete = stage === 'complete'` (based on conversation stage)  
**After**: `isComplete = missing_info.length === 0` (based on actual data completeness)

---

## User Experience Flow

### Scenario: User Missing Deposit Protection Status

#### 1. **User provides basic information**
```
Agent: "What's the property address?"
User: "123 Main St, London"
Agent: "When did the tenancy start?"
User: "January 15, 2023"
Agent: "What was the deposit amount?"
User: "£1500"
Agent: "What issues are you disputing?"
User: "Cleaning charges"
```

#### 2. **Sidebar shows missing information**
```
┌─────────────────────────────────┐
│ ⚠️ Required Information Missing │
│                                 │
│ • deposit protection status     │
│                                 │
│ Please provide this info to     │
│ generate a prediction           │
└─────────────────────────────────┘
```

#### 3. **Agent proactively asks**
```
Agent: "One last important question: Was your deposit protected 
in a government-approved scheme (like TDS, DPS, or MyDeposits)?"
```

#### 4. **User completes required info**
```
User: "No, it wasn't protected"
```

#### 5. **Sidebar shows success + Prediction button appears**
```
┌─────────────────────────────────┐
│ ✓ All Required Info Collected! │
│                                 │
│ Ready to generate prediction    │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ ✨ Generate Prediction →        │
└─────────────────────────────────┘
```

---

## API Changes

### Response Schema Updates

All chat endpoints now return `missing_info` in the case file:

```json
{
  "session_id": "abc123",
  "response": "What's the property address?",
  "stage": "basic_details",
  "completeness": 0.4,
  "is_complete": false,
  "case_file": {
    "case_id": "case_xyz",
    "missing_info": [
      "property address",
      "tenancy start date",
      "deposit amount",
      "dispute issues",
      "deposit protection status"
    ],
    "intake_complete": false,
    "completeness_score": 0.4
  }
}
```

### Prediction Generation Endpoint

`POST /predictions/generate` now returns HTTP 400 if required fields missing:

```json
{
  "detail": "Intake not complete. Completeness: 60%. Missing: property address, deposit protection status"
}
```

---

## Testing Scenarios

### ✅ Happy Path: Complete Information
```
1. User provides all 5 required fields
2. Sidebar shows "All Required Info Collected!"
3. Prediction button appears and is enabled
4. POST /predictions/generate succeeds
```

### ⚠️ Missing Fields: Property Address
```
1. User provides 4/5 fields (missing address)
2. Sidebar shows: "⚠️ Required Information Missing: • property address"
3. Agent asks: "What's the property address?"
4. Prediction button does NOT appear
5. POST /predictions/generate returns 400 error
```

### ⚠️ Partial Information: Multiple Missing
```
1. User provides 2/5 fields
2. Sidebar shows all missing fields in bullet list
3. Agent proactively asks for one missing field at a time
4. Prediction button remains hidden
5. As each field is provided, it's removed from missing list
```

### ✅ Multi-Party Dispute
```
1. Tenant completes all 5 required fields
2. Tenant's sidebar shows "All Required Info Collected!"
3. Landlord completes all 5 required fields
4. Both parties see "Both Parties Complete!" message
5. Prediction button appears for both parties
```

---

## Benefits

### 1. **Data Quality**
- Predictions always have complete required context
- No more "garbage in, garbage out" scenarios
- RAG retrieval gets better queries with complete information

### 2. **User Clarity**
- Users know exactly what's needed
- No confusion about why prediction button is disabled
- Clear progress toward goal

### 3. **Legal Defensibility**
- Every prediction backed by complete case facts
- Required fields align with tribunal requirements
- Audit trail shows when information was collected

### 4. **Agent Behavior**
- LLM agent proactively collects missing required fields
- Prioritizes required fields over optional ones
- Structured conversation flow with clear goals

### 5. **Developer Experience**
- Single source of truth: `has_all_required_info()`
- Easy to add/remove required fields in one place
- Clear separation between required and optional fields

---

## Future Enhancements

### 1. **Dynamic Required Fields**
Based on case type, adjust required fields:
```python
# For deposit protection disputes
REQUIRED_FIELDS = [...base_fields, "protection_date", "prescribed_info_provided"]

# For cleaning/damage disputes
REQUIRED_FIELDS = [...base_fields, "inventory_checkin", "inventory_checkout"]
```

### 2. **Progressive Disclosure**
Show required fields in stages to avoid overwhelming users:
```
Stage 1 (Basic): Address, Start Date
Stage 2 (Financial): Deposit Amount, Protected?
Stage 3 (Dispute): Issues
```

### 3. **Smart Defaults**
For some fields, offer intelligent defaults:
```
Agent: "Was the deposit protected? (Most landlords use TDS, DPS, or MyDeposits)"
User: "I'm not sure"
Agent: "No problem - did you receive a certificate with scheme details within 30 days?"
```

### 4. **Evidence-Based Inference**
If user uploads deposit protection certificate, auto-fill:
- `deposit_protected = True`
- `deposit_scheme = "TDS"` (from document)
- `protection_date = "2023-01-20"` (from document)

---

## Rollback Plan (If Needed)

If strict validation causes issues, can temporarily revert by changing one line in `PredictionService`:

```python
# Revert to 70% threshold (NOT RECOMMENDED)
"is_complete": case_file.completeness_score >= 0.7,

# Strict validation (CURRENT - RECOMMENDED)
"is_complete": case_file.has_all_required_info(),
```

However, **this is NOT recommended** as it defeats the purpose of ensuring prediction quality.

---

## Monitoring & Metrics

### Key Metrics to Track

1. **Intake Completion Rate**: % of users who reach "all required info collected"
2. **Time to Completion**: How long to collect all 5 required fields
3. **Abandonment by Field**: Which required field causes most dropoffs
4. **Agent Effectiveness**: How many prompts needed per missing field
5. **Prediction Quality**: Accuracy improvement with complete vs. incomplete data

### Logging

All validation checks are logged:

```python
logger.debug("intake_validation",
    session_id=session_id,
    has_all_required=case_file.has_all_required_info(),
    missing_required=missing_required,
    intake_complete=case_file.intake_complete)
```

Look for these log events:
- `intake_marked_complete_all_required_fields_present`: Success ✅
- `case_incomplete_for_prediction`: User tried to predict too early ⚠️

---

## Questions & Answers

**Q: Why not make ALL fields required?**  
A: Some fields (evidence, narratives) are valuable but not essential for basic prediction. We want quality without creating friction.

**Q: What if a user genuinely doesn't know a required field?**  
A: The agent can guide them. For example, "Not sure if deposit protected? Check if you received a certificate from TDS, DPS, or MyDeposits within 30 days."

**Q: Can users skip required fields temporarily?**  
A: Yes, the conversation can move forward, but prediction button won't appear until all 5 fields are provided. They can return to complete it later.

**Q: Does this work with multi-party disputes?**  
A: Yes! Each party must complete their own required fields. The system merges both case files for joint prediction.

**Q: How do I add a new required field?**  
A: Update `get_missing_required_info()` in `case_file.py`. The rest of the system will automatically enforce it.

---

## Summary

This implementation ensures that **every prediction is backed by complete, high-quality data**. Users get clear guidance on what's needed, agents proactively collect missing information, and the system prevents incomplete predictions.

**Result**: Better prediction accuracy, clearer user experience, and legal defensibility.

