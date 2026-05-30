# Proposer demo runbook (do it yourself)

Everything you need to run **tenant-led** and **landlord-led** demos: case text, scripts, manual UI steps, and API commands.

---

## Prerequisites

```bash
cd proposer

# Terminal 1 — API
python3 scripts/api.py
# → http://localhost:8000

# Terminal 2 — Web
cd apps/web && npm run dev
# → http://localhost:3000

# Database (if needed)
make db-up && make migrate
```

Ensure `.env` has `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.

---

## Files in this demo pack

| Path | Purpose |
|------|---------|
| `docs/demo/example-cases/tenant-deposit-cleaning-dispute.md` | Tenant case (copy-paste text) |
| `docs/demo/example-cases/landlord-deposit-damage-dispute.md` | Landlord case (copy-paste text) |
| `scripts/demo/run_full_flow.py` | API-only: intake → prediction → join → mediation → settle |
| `scripts/demo/record_walkthrough.mjs` | Record `.webm` videos (Playwright) |
| `docs/demo/last-run.json` | Output from last `run_full_flow.py` (IDs + URLs) |
| `docs/demo/videos/*.webm` | Recorded walkthroughs |

---

## Scenario A — Tenant-led (tenant creates dispute)

**Who does what**

1. **Tenant** — bulk intake, creates dispute, gets invite code, runs prediction, starts mediation.
2. **Landlord** — joins with invite code (second browser / incognito), pastes landlord case.

### Tenant case text (bulk paste)

```
I am the tenant. I rented a 2-bedroom flat at 14 Maple Court, London E14 9QT from 1 March 2023 to 28 February 2024. Monthly rent was £1,450 and I paid a deposit of £1,450.

The deposit was protected with the Tenancy Deposit Scheme (TDS). I received the prescribed information within 30 days of paying the deposit.

When I moved in, the landlord did not provide a check-in inventory or condition report. I took dated photos on move-in day showing the carpets and kitchen in reasonable condition.

I left the property clean on 28 February 2024 and returned all keys. The landlord has not returned my deposit. They are claiming £400 for professional cleaning and £250 for scratches on the kitchen laminate, which I believe is fair wear and tear.

I have move-out photos, email threads asking for the deposit back, and the tenancy agreement. I want the full deposit returned, or at least £1,000 after any fair deductions.
```

### Landlord case text (when joining with invite)

```
I am the landlord. I let a 1-bedroom flat at 8 Riverside Walk, Bristol BS1 5TY to one tenant from 15 June 2022 to 14 June 2023. Rent was £950 per month and the deposit was £950.

The deposit was protected with MyDeposits within the legal time limit. I provided a check-in inventory signed by the tenant on 20 June 2022, noting scuff marks on the bedroom wall and a stained cooker hood.

The tenant left owing £190 in rent for the final week. After checkout on 14 June 2023, I found a burn mark on the kitchen worktop (not on the inventory), broken blinds in the living room, and the property needed professional cleaning beyond fair wear and tear.

I am claiming £350 for worktop repair, £120 for blind replacement, £180 for cleaning, and £190 rent arrears from the deposit — total £840. I want to return £110 to the tenant if that is fair, or defend keeping most of the deposit.

I have the signed inventory, checkout photos, contractor quotes, and rent ledger.
```

### Manual UI — tenant-led

| Step | Actor | Action |
|------|--------|--------|
| 1 | Tenant | http://localhost:3000/chat → **Start New Dispute** → **Deposit** → **I'm the tenant** |
| 2 | Tenant | **Paste All Details** → paste tenant case → **Submit** |
| 3 | Tenant | **Get prediction** → scroll results → note invite code on session |
| 4 | Landlord | New incognito window → **Join Existing Dispute** → invite code → **I'm the landlord** → paste landlord case |
| 5 | Tenant | Prediction page → **Proceed to Mediation** → expectation → **Start Mediation** / **Open Chat** |
| 6 | Both | Chat: messages, **Make an Offer**, counter, accept (`?session=...&role=tenant` or `role=landlord`) |

---

## Scenario B — Landlord-led (landlord creates dispute)

Swap roles: landlord uses **landlord case** in step 1–2; tenant joins with **tenant case**.

| Step | Actor | Action |
|------|--------|--------|
| 1 | Landlord | **Start New Dispute** → **Deposit** → **I'm the landlord** → paste landlord case |
| 2 | Landlord | Get prediction → share invite code |
| 3 | Tenant | Join dispute → **I'm the tenant** → paste tenant case |
| 4 | Landlord | Mediation from landlord session (`role=landlord` in chat URL) |

---

## Automated scripts

### 1) Full API flow (no browser)

```bash
cd proposer

# Tenant-led only
python3 scripts/demo/run_full_flow.py --scenario tenant-led

# Landlord-led only
python3 scripts/demo/run_full_flow.py --scenario landlord-led

# Both
python3 scripts/demo/run_full_flow.py --scenario both
```

Writes **`docs/demo/last-run.json`** with `dispute_id`, `invite_code`, `session_id`, prediction outcome, and URLs like:

`http://localhost:3000/prediction/{caseId}?session={sessionId}&dispute={disputeId}`

### 2) Record walkthrough videos

```bash
cd proposer
npm install --no-save playwright@1.51.1
npx playwright install chromium

# Both videos
node scripts/demo/record_walkthrough.mjs

# One scenario only
node scripts/demo/record_walkthrough.mjs --scenario tenant-led
node scripts/demo/record_walkthrough.mjs --scenario landlord-led
```

Outputs:

- `docs/demo/videos/proposer-walkthrough-tenant-led.webm`
- `docs/demo/videos/proposer-walkthrough-landlord-led.webm`

---

## API commands (curl) — tenant-led example

Replace `CASE_TEXT` with the tenant paragraph (escaped for JSON).

### Tenant bulk intake + dispute

```bash
curl -s -X POST http://localhost:8000/chat/bulk-intake \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "tenant",
    "domain_id": "housing.deposit.v1",
    "create_dispute": true,
    "case_text": "I am the tenant. I rented a 2-bedroom flat at 14 Maple Court..."
  }' | python3 -m json.tool
```

Save: `session_id`, `case_file.case_id`, `dispute.dispute_id`, `dispute.invite_code`.

### Generate prediction

```bash
curl -s -X POST http://localhost:8000/predictions/generate \
  -H 'Content-Type: application/json' \
  -d '{"case_id": "YOUR_CASE_ID", "domain_id": "housing.deposit.v1"}' \
  | python3 -m json.tool
```

### Landlord joins (invite code)

```bash
curl -s -X POST http://localhost:8000/chat/bulk-intake \
  -H 'Content-Type: application/json' \
  -d '{
    "role": "landlord",
    "domain_id": "housing.deposit.v1",
    "create_dispute": false,
    "invite_code": "YOUR-INVITE-CODE",
    "case_text": "I am the landlord. I let a 1-bedroom flat..."
  }' | python3 -m json.tool
```

### Expectation data (per party)

```bash
curl -s "http://localhost:8000/mediation/DISP_ID/expectation/TENANT_SESSION_ID" | python3 -m json.tool
curl -s "http://localhost:8000/mediation/DISP_ID/expectation/LANDLORD_SESSION_ID" | python3 -m json.tool
```

### Start mediation + dialogue

```bash
# Start
curl -s -X POST "http://localhost:8000/mediation/DISP_ID/start" \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "TENANT_SESSION_ID"}'

# Tenant message
curl -s -X POST "http://localhost:8000/mediation/DISP_ID/message" \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "TENANT_SESSION_ID", "content": "I believe I should receive at least £1,100 back..."}'

# Landlord message
curl -s -X POST "http://localhost:8000/mediation/DISP_ID/message" \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "LANDLORD_SESSION_ID", "content": "The checkout report shows damage beyond wear and tear..."}'

# Tenant offer
curl -s -X POST "http://localhost:8000/mediation/DISP_ID/offer" \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "TENANT_SESSION_ID", "amount": 950}'

# Landlord counter (use offer_id from response)
curl -s -X POST "http://localhost:8000/mediation/DISP_ID/respond" \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "LANDLORD_SESSION_ID", "offer_id": "OFFER_ID", "action": "counter", "counter_amount": 720}'

# Accept (use pending offer_id from GET messages)
curl -s "http://localhost:8000/mediation/DISP_ID/messages" | python3 -m json.tool
curl -s -X POST "http://localhost:8000/mediation/DISP_ID/respond" \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "TENANT_SESSION_ID", "offer_id": "PENDING_OFFER_ID", "action": "accept"}'
```

---

## Deep links (after you have IDs)

| Screen | URL pattern |
|--------|-------------|
| Prediction | `http://localhost:3000/prediction/{caseId}?session={sessionId}&dispute={disputeId}` |
| Expectation | `http://localhost:3000/mediation/{disputeId}/expectation?session={sessionId}` |
| Mediation chat | `http://localhost:3000/mediation/{disputeId}/chat?session={sessionId}&role=tenant` or `role=landlord` |
| Chat session | `http://localhost:3000/chat/{sessionId}` |

**Important:** Mediation chat needs `role=tenant` or `role=landlord` in the query string so you can send messages and offers.

---

## Sample negotiation lines (mediation chat)

**Tenant**

- “I believe I should receive at least £1,100 back. There was no check-in inventory.”
- Offer: **£950** (adjust toward ZOPA centre)

**Landlord**

- “The checkout report shows cleaning and worktop damage. I cannot return more than £400.”
- Counter: **£720** → accept near **£835** midpoint

**Landlord-led** — reverse who opens; landlord might offer **£250** retention, tenant counters.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| “No expectation data found” | Generate prediction first; refresh after frontend fix in `lib/api/mediation.ts` |
| Prediction keeps loading | Wait ~60–90s; or reload — page should load existing prediction from DB |
| Cannot send chat messages | Add `?role=tenant` or `?role=landlord` to mediation chat URL |
| 404 on expectation | `session_id` must belong to that `dispute_id` |

---

## Quick reference — which case when

| You are… | Creating dispute? | Paste this case |
|----------|-------------------|-----------------|
| Tenant | Yes (tenant-led) | Tenant case |
| Landlord | Joining tenant dispute | Landlord case |
| Landlord | Yes (landlord-led) | Landlord case |
| Tenant | Joining landlord dispute | Tenant case |
