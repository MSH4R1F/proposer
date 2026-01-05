# API Documentation

Base URL: `http://localhost:8000`

## Endpoints

### Chat

#### Start Session
```
POST /chat/start
```
**Request:**
```json
{"role": "tenant"}  // or "landlord"
```
**Response:**
```json
{
  "session_id": "abc123",
  "case_id": "case_xyz",
  "message": "Hello! I'll help you..."
}
```

#### Send Message
```
POST /chat/message
```
**Request:**
```json
{
  "session_id": "abc123",
  "message": "I'm disputing cleaning charges"
}
```
**Response:**
```json
{
  "message": "Can you tell me more about...",
  "stage": "issue_identification",
  "completeness": 0.45
}
```

#### Get Session
```
GET /chat/session/{session_id}
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
