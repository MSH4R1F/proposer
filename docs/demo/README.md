# Proposer demo walkthrough

End-to-end examples from **intake → prediction → mediation** for both **tenant** and **landlord** perspectives.

## Example cases

| File | Role | Scenario |
|------|------|----------|
| [tenant-deposit-cleaning-dispute.md](./example-cases/tenant-deposit-cleaning-dispute.md) | Tenant | No check-in inventory; cleaning/damage deductions |
| [landlord-deposit-damage-dispute.md](./example-cases/landlord-deposit-damage-dispute.md) | Landlord | Signed inventory; documented damage and rent arrears |

Copy the **Case text** section from either file into the app’s bulk-paste intake, or run the automation below.

## Prerequisites

- Backend: `python scripts/api.py` → http://localhost:8000
- Frontend: `cd apps/web && npm run dev` → http://localhost:3000
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `.env`
- Postgres running (`make db-up && make migrate` if needed)

## Run full API flow (both scenarios)

```bash
cd proposer
python scripts/demo/run_full_flow.py --scenario both
```

Writes `docs/demo/last-run.json` with dispute IDs, sessions, prediction summary, and deep links.

## Record walkthrough videos

```bash
cd proposer
npm init -y 2>/dev/null || true
npm install --no-save playwright@1.51.1
npx playwright install chromium
node scripts/demo/record_walkthrough.mjs
```

Outputs:

- `docs/demo/videos/proposer-walkthrough-tenant-led.webm`
- `docs/demo/videos/proposer-walkthrough-landlord-led.webm`

## Manual UI path

1. Open http://localhost:3000/chat
2. Choose **Housing deposit** → **Tenant** or **Landlord**
3. **Paste case** → paste example text → extract
4. **Get prediction** → review outcome, settlement range, citations
5. Share **invite code** with the other party (second browser/incognito)
6. **Proceed to mediation** → expectation screen → negotiation chat → offer → accept → settlement

## Scenarios

- **Tenant-led:** Tenant creates dispute and prediction; landlord joins with invite code; mediation runs from tenant session first.
- **Landlord-led:** Landlord creates dispute; tenant joins; same prediction/mediation chain with landlord-first framing.
