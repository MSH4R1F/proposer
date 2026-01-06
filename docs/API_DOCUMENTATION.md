# API Documentation

Base URL: `http://localhost:8000`

## Endpoints

### Chat

The chat flow follows this sequence:
1. `POST /chat/start` - Get session ID and greeting
2. `POST /chat/set-role` - Set tenant/landlord role (required before messaging)
3. `POST /chat/message` - Continue the conversation

#### Start Session
```
POST /chat/start
```
Starts a new intake conversation. Role is NOT set here - it must be set via `/chat/set-role` after the user selects their role in the UI.

**Request:**
```json
{}
```

**Response:**
```json
{
  "session_id": "abc123def4",
  "greeting": "Hello! I'm here to help you with your tenancy deposit dispute...",
  "stage": "greeting"
}
```

#### Set Role
```
POST /chat/set-role
```
Sets the user's role (tenant or landlord). Must be called after starting a session and before sending messages.

**Request:**
```json
{
  "session_id": "abc123def4",
  "role": "tenant"
}
```

**Response:**
```json
{
  "session_id": "abc123def4",
  "response": "Thank you. Let's start by getting some basic information...",
  "stage": "basic_details",
  "completeness": 0.1,
  "is_complete": false,
  "case_file": {...},
  "role_set": true
}
```

#### Send Message
```
POST /chat/message
```
Send a message in the intake conversation. Role must be set first.

**Request:**
```json
{
  "session_id": "abc123def4",
  "message": "I'm disputing cleaning charges of £200"
}
```

**Response:**
```json
{
  "session_id": "abc123def4",
  "response": "I understand. Can you tell me more about the cleaning issues?",
  "stage": "issue_identification",
  "completeness": 0.45,
  "is_complete": false,
  "case_file": {...},
  "suggested_actions": ["Upload evidence", "Describe the condition"]
}
```

#### Get Session
```
GET /chat/session/{session_id}
```
Get the current state of a chat session, including full message history.

**Response:**
```json
{
  "session_id": "abc123def4",
  "stage": "basic_details",
  "completeness": 0.25,
  "is_complete": false,
  "message_count": 4,
  "case_file": {...},
  "messages": [
    {
      "role": "assistant",
      "content": "Hello! I'm here to help...",
      "timestamp": "2026-01-06T10:00:00"
    },
    {
      "role": "user",
      "content": "I'm a tenant",
      "timestamp": "2026-01-06T10:01:00"
    }
  ]
}
```

#### Delete Session
```
DELETE /chat/session/{session_id}
```

**Response:**
```json
{
  "message": "Session abc123def4 deleted"
}
```

#### List Sessions
```
GET /chat/sessions
```

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "abc123def4",
      "case_id": "case_xyz",
      "stage": "basic_details",
      "is_complete": false
    }
  ]
}
```

---

### Evidence

#### Upload
```
POST /evidence/upload/{case_id}
```
**Form Data:**
- `file`: PDF or image file
- `evidence_type`: `document`, `photo`, `statement`
- `description`: Brief description

**Response:**
```json
{
  "evidence_id": "ev123",
  "file_url": "https://...",
  "extracted_text": "..."
}
```

#### List Evidence
```
GET /evidence/{case_id}
```

---

### Predictions

#### Generate
```
POST /predictions/generate
```
**Request:**
```json
{"case_id": "case_xyz"}
```
**Response:**
```json
{
  "prediction_id": "pred123",
  "overall_outcome": "tenant_likely_wins",
  "overall_confidence": 0.75,
  "issue_predictions": [...],
  "reasoning_trace": [...],
  "disclaimer": "This is not legal advice..."
}
```

#### Get Prediction
```
GET /predictions/{prediction_id}
```

---

### Cases

#### Get Case
```
GET /cases/{case_id}
```

#### List Cases
```
GET /cases
```

---

### Health

```
GET /health
```
**Response:**
```json
{"status": "healthy", "rag_loaded": true}
```

---

## Error Responses

```json
{
  "detail": "Error message here"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request |
| 404 | Not found |
| 500 | Server error |
