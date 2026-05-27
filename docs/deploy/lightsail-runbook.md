# Backend Deployment Runbook — AWS Lightsail

Operator guide for deploying the Proposer FastAPI backend to AWS Lightsail Container Service.
Design: `docs/superpowers/specs/2026-05-23-backend-deployment-lightsail-design.md`.
Plan: `docs/superpowers/plans/2026-05-23-backend-deployment-lightsail.md`.

> Build the image from a checkout that has `data/embeddings/` (the ~1.1GB deposit
> corpus is gitignored and not in any clone). `docker build` ignores `.git`.

## Prerequisites
- Docker installed and running.
- AWS CLI configured (`aws sts get-caller-identity` works).
- A Supabase project.
- `OPENAI_API_KEY`.

## 1. Supabase
1. Create a project (region near `eu-west-2`).
2. Project Settings → Database → Connection string → **Session pooler** (host `aws-0-<region>.pooler.supabase.com`, port `5432`, user `postgres.<ref>`). Do NOT use the transaction pooler (6543) — it breaks asyncpg prepared statements.
3. Build `DATABASE_URL`: `postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`
4. Verify TLS connectivity: `DATABASE_URL="..." venv/bin/python scripts/deploy/verify_supabase.py` → expect `connected: select1=1 ssl=on`.
5. Migrate: `DATABASE_URL="..." venv/bin/alembic -c alembic.ini upgrade head`.
6. Storage → create the evidence bucket the app expects (see `apps/api/src/services/storage_service.py`). Note `SUPABASE_URL` + the service-role key.

## 2. Lightsail service (one-time)
```bash
aws lightsail create-container-service --region eu-west-2 --service-name proposer-api --power small --scale 1
# wait for READY:
aws lightsail get-container-services --region eu-west-2 --service-name proposer-api --query 'containerServices[0].state' --output text
```
`small` = 2GB/1vCPU (~$20/mo). If the container OOMs loading the Chroma index, recreate at `--power medium` (4GB, ~$40/mo).

## 3. Deploy
```bash
cp deploy/.env.deploy.example deploy/.env.deploy   # then fill in (gitignored)
./scripts/deploy/lightsail_deploy.sh               # run from a checkout WITH data/embeddings
aws lightsail get-container-services --region eu-west-2 --service-name proposer-api \
  --query 'containerServices[0].{state:state,url:url}'   # wait for ACTIVE + note the url
```

## 4. Smoke test (BASE = the Lightsail url)
```bash
curl -s "$BASE/health"    # openai_configured:true
curl -s "$BASE/readyz"    # alembic_version:"0005"
curl -s "$BASE/domains"   # deposit "live"; others "coming_soon"
```
End-to-end (confirms the baked corpus loaded):
```bash
SID=$(curl -s -X POST "$BASE/chat/bulk-intake" -H 'Content-Type: application/json' \
  -d '{"role":"tenant","domain_id":"housing.deposit.v1","create_dispute":false,"case_text":"Deposit 1200 not protected; landlord withholding 800 for cleaning; no check-in inventory."}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['case_file']['case_id'])")
curl -s -m 180 -X POST "$BASE/predictions/generate" -H 'Content-Type: application/json' \
  -d "{\"case_id\":\"$SID\"}" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['overall_outcome'], d['total_cases_analyzed'])"
```
Expect a decisive outcome with `total_cases_analyzed > 0`. Logs: `aws lightsail get-container-log --region eu-west-2 --service-name proposer-api --container-name api`.

## 5. Frontend wiring
Deploy the Next.js frontend separately (Cloudflare Pages / Vercel) with `NEXT_PUBLIC_API_URL=<Lightsail url>`. Then add that frontend origin to `CORS_ORIGINS` in `deploy/.env.deploy` and re-run `./scripts/deploy/lightsail_deploy.sh`.

## Cost
~$20–40/mo (Lightsail) + Supabase free tier + OpenAI usage (pay-per-use).
