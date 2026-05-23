# Backend Deployment (AWS Lightsail) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Proposer FastAPI backend (deposit corpus baked into the image) to AWS Lightsail Container Service, backed by Supabase Postgres + Storage, for a low-traffic thesis demo.

**Architecture:** A multi-stage Docker image bundles the app + the ~1.1GB ChromaDB deposit corpus and runs `scripts/api.py` (uvicorn on `:8000`). Lightsail Container Service runs one instance with built-in HTTPS and a `/health` health check. App state is in Supabase Postgres (TLS); evidence files in Supabase Storage. Config/secrets are Lightsail container env vars; the deployed frontend origin is allowed via the existing `CORS_ORIGINS` env var.

**Tech Stack:** Docker, AWS Lightsail (+ AWS CLI), Supabase (Postgres + Storage), Python 3.11 / FastAPI / uvicorn / asyncpg / chromadb, alembic.

**Spec:** `docs/superpowers/specs/2026-05-23-backend-deployment-lightsail-design.md`

**Important environment facts (already true on `main`):**
- CORS is env-driven: `apps/api/src/config.py` `cors_origins` reads `CORS_ORIGINS` (comma-separated) with a localhost fallback; `main.py` uses `settings.cors_origins`. **No CORS code change is needed — just set `CORS_ORIGINS` in prod.**
- `APIConfig.from_env()` enforces, when `APP_ENV=production`: `DEBUG=false`; a non-local `DATABASE_URL`; `sslmode in {require,verify-ca,verify-full}` present in the URL **string**.
- `apps/api/src/db/engine.py:create_engine_from_url()` passes the URL straight to `create_async_engine` with **no** `connect_args` — asyncpg uses `ssl=`, not `sslmode=`, so TLS to Supabase must be verified (Task 3).
- Entrypoint `scripts/api.py`: `chdir`s to repo root, `load_dotenv()` (no-op without a `.env`), runs `uvicorn.run("main:app", host="0.0.0.0", port=8000)`.
- `alembic.ini`: `script_location=apps/api/src/alembic`, `prepend_sys_path=.`; `env.py` adds `packages/` to `sys.path` and runs migrations **async** (same asyncpg/TLS path as the app).
- The deposit corpus `data/embeddings/` (~1.1GB) is **gitignored** — it is not in any git clone. The image must be built from a working copy that has it (e.g. the main `~/Documents` checkout; `docker build` does not read `.git`, so that repo's git corruption is irrelevant to building).

**Conventions:** Region `eu-west-2` (London) — override via `AWS_REGION`. Lightsail service name `proposer-api` — override via `LIGHTSAIL_SERVICE`. Run all commits in a clean clone (per the git-corruption hazard), push to origin.

---

## File Structure
- Create: `Dockerfile` — multi-stage image; bakes app + corpus; runs the API.
- Create: `.dockerignore` — keep the build context to code + `data/embeddings`.
- Create: `scripts/deploy/lightsail_deploy.sh` — build → push → deploy (reads secrets from an untracked env file).
- Create: `scripts/deploy/verify_supabase.py` — one-off async TLS connection check.
- Create: `deploy/.env.deploy.example` — documents required deploy-time env vars (real `deploy/.env.deploy` is gitignored).
- Create: `docs/deploy/lightsail-runbook.md` — the operator runbook (Supabase + Lightsail one-time setup, deploy, smoke test, frontend wiring).
- Modify (only if Task 3 proves it necessary): `apps/api/src/db/engine.py` — add TLS `connect_args` for asyncpg.
- Modify: `.gitignore` — add `deploy/.env.deploy`.

---

## Task 1: `.dockerignore`

**Files:** Create `/.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**
```
.git
**/__pycache__/
**/*.pyc
venv/
.venv/
apps/web/node_modules/
apps/web/.next/
data/raw/
data/indices/
data/processed/
data/eval/
data/eval_artifacts/
data/regression/
data/test-cases/
data/sessions/
data/knowledge_graphs/
data/evidence_files/
*.bak
*.log
.env
.env.*
deploy/.env.deploy
docs/
```
(Note: `data/embeddings/` is intentionally NOT excluded — it must be in the build context. `docs/` is excluded to shrink context.)

- [ ] **Step 2: Verify it parses**
Run (from a checkout with the corpus): `docker build --no-cache -f Dockerfile . 2>&1 | head -1` — Expected: a build line, not a `.dockerignore` parse error. (Full build happens in Task 2.)

- [ ] **Step 3: Commit**
```bash
git add .dockerignore
git commit -m "build: add .dockerignore for the API image"
```

---

## Task 2: `Dockerfile`

**Files:** Create `/Dockerfile`

- [ ] **Step 1: Create the multi-stage Dockerfile**
```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
# libgomp1 is required by chromadb's onnxruntime dependency at import time.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 appuser
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DEBUG=false
COPY --from=builder /opt/venv /opt/venv
COPY apps/ ./apps/
COPY packages/ ./packages/
COPY scripts/ ./scripts/
COPY alembic.ini ./
COPY data/embeddings/ ./data/embeddings/
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "scripts/api.py"]
```

- [ ] **Step 2: Build the image (from a checkout WITH the corpus)**
Run from the main working copy that has `data/embeddings/` (e.g. `~/Documents/Projects/proposer/legal-mediation-system`):
```bash
docker build -t proposer-api:latest .
```
Expected: build succeeds; final image ~1.5–2GB (`docker images proposer-api`). If the build fails because `data/embeddings/` is missing, you are building from a clone without the corpus — build from the main checkout, or copy the corpus into the build context first: `cp -R <main>/data/embeddings ./data/embeddings`.

- [ ] **Step 3: Run it locally against a throwaway env, hit `/health`**
```bash
docker run --rm -p 8001:8000 \
  -e APP_ENV=local -e DEBUG=false \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e DATABASE_URL="postgresql+asyncpg://proposer:proposer-dev@host.docker.internal:5432/proposer" \
  proposer-api:latest &
sleep 8
curl -s -m 5 http://localhost:8001/health
```
Expected: `{"status":"healthy",..."openai_configured":true,...}`. (Use `APP_ENV=local` here so the prod DB guardrail doesn't reject the local DB URL; this only validates the image boots + the corpus is present. Stop the container afterward: `docker stop $(docker ps -q --filter ancestor=proposer-api:latest)`.)

- [ ] **Step 4: Confirm the baked corpus loaded (optional, needs OpenAI + a local Postgres)**
If a local migrated Postgres is reachable, `curl -s http://localhost:8001/domains` should list domains and a deposit prediction should report `total_cases_analyzed > 0`. Otherwise defer corpus verification to the live smoke test (Task 7).

- [ ] **Step 5: Commit**
```bash
git add Dockerfile
git commit -m "build: multi-stage Dockerfile baking the deposit corpus"
```

---

## Task 3: Supabase project + verify async TLS connection

**Files:** Create `scripts/deploy/verify_supabase.py`; Modify `apps/api/src/db/engine.py` only if the check fails.

- [ ] **Step 1: Create the Supabase project (manual, documented)**
In the Supabase dashboard: create a project (region near `eu-west-2`). From **Project Settings → Database → Connection string**, copy the **Session pooler** URI (host `aws-0-<region>.pooler.supabase.com`, port `5432`, user `postgres.<ref>`). Do NOT use the Transaction pooler (port 6543) — it breaks asyncpg prepared statements. Construct:
`postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`
Export it locally for this task: `export DATABASE_URL="<that url>"`.

- [ ] **Step 2: Write the connection verification script**
```python
# scripts/deploy/verify_supabase.py
"""One-off: verify the API's async engine can reach Supabase over TLS."""
import asyncio, os, sys
sys.path.insert(0, "."); sys.path.insert(0, "packages"); sys.path.insert(0, "apps/api/src")
from sqlalchemy import text
from apps.api.src.db.engine import create_engine_from_url


async def main() -> int:
    url = os.environ["DATABASE_URL"]
    engine = create_engine_from_url(url)
    try:
        async with engine.connect() as conn:
            (one,) = (await conn.execute(text("select 1"))).one()
            ssl_on = (await conn.execute(text("show ssl"))).scalar()
        print(f"connected: select1={one} ssl={ssl_on}")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 3: Run it**
Run: `DATABASE_URL="$DATABASE_URL" venv/bin/python scripts/deploy/verify_supabase.py`
Expected: `connected: select1=1 ssl=on`.

- [ ] **Step 4: If it fails, add TLS connect_args to the engine, then re-run**
If Step 3 raises (e.g. asyncpg rejects `sslmode`, or connects without TLS and Supabase refuses), modify `apps/api/src/db/engine.py` `create_engine_from_url` to strip `sslmode` from the URL and pass TLS via `connect_args`:
```python
def create_engine_from_url(url, *, pool_size=10, max_overflow=5, pool_timeout=10, pool_pre_ping=True):
    connect_args = {}
    if "sslmode=" in url:
        # asyncpg uses `ssl`, not libpq `sslmode`; honor require/verify-* as TLS-on.
        connect_args["ssl"] = True
        # keep the URL parseable for asyncpg by removing the unsupported query param
        import re
        url = re.sub(r"([?&])sslmode=[^&]*", lambda m: m.group(1), url).rstrip("?&").replace("&&", "&")
    return create_async_engine(url, pool_size=pool_size, max_overflow=max_overflow,
                               pool_timeout=pool_timeout, pool_pre_ping=pool_pre_ping,
                               connect_args=connect_args, future=True)
```
Re-run Step 3 until it prints `ssl=on`. (Note: `APIConfig` validates the *original* `DATABASE_URL` string for `sslmode=require`, so keep `sslmode=require` in the env var even though the engine strips it for asyncpg.)

- [ ] **Step 5: Commit (only if engine.py changed)**
```bash
git add apps/api/src/db/engine.py scripts/deploy/verify_supabase.py
git commit -m "fix(db): honor TLS for asyncpg (Supabase) + add connection verifier"
```
If `engine.py` was unchanged, commit just the verifier:
```bash
git add scripts/deploy/verify_supabase.py
git commit -m "chore(deploy): add Supabase async connection verifier"
```

---

## Task 4: Run migrations against Supabase

**Files:** none (operational).

- [ ] **Step 1: Apply the schema**
Run (from the repo root, with the working `DATABASE_URL` from Task 3): `DATABASE_URL="$DATABASE_URL" venv/bin/alembic -c alembic.ini upgrade head`
Expected: alembic logs `Running upgrade ... -> 0005` (or `0005 (head)` if already applied).

- [ ] **Step 2: Confirm**
Run: `DATABASE_URL="$DATABASE_URL" venv/bin/python -c "import asyncio,os; from sqlalchemy import text; from apps.api.src.db.engine import create_engine_from_url; import sys; sys.path[:0]=['.','packages','apps/api/src']; e=create_engine_from_url(os.environ['DATABASE_URL']); asyncio.run((lambda: None)())" 2>/dev/null; echo "use /readyz post-deploy to confirm alembic_version"`
Expected: no error. (Definitive confirmation is `/readyz` returning `alembic_version: 0005` after deploy, Task 7.)

- [ ] **Step 3: Create the Storage bucket (for evidence files)**
In Supabase → Storage, create the bucket the app expects (grep the code for the bucket name: `grep -rn "bucket" apps/api/src/services/storage_service.py packages/llm_orchestrator`); create that bucket. Note `SUPABASE_URL` and the **service role** key for the deploy env.

---

## Task 5: Create the Lightsail container service (one-time)

**Files:** none (operational). Prereq: AWS CLI configured (`aws sts get-caller-identity` works).

- [ ] **Step 1: Create the service**
```bash
aws lightsail create-container-service --region eu-west-2 \
  --service-name proposer-api --power small --scale 1
```
Expected: JSON with `"state": "PENDING"`. Poll until READY:
```bash
aws lightsail get-container-services --region eu-west-2 --service-name proposer-api \
  --query 'containerServices[0].state' --output text
```
Expected eventually: `READY`. (Power `small` = 2GB/1vCPU ~$20/mo. If Task 7 OOMs, recreate/update with `--power medium`.)

---

## Task 6: Deploy script + deploy-env scaffolding

**Files:** Create `scripts/deploy/lightsail_deploy.sh`, `deploy/.env.deploy.example`; Modify `.gitignore`.

- [ ] **Step 1: Add the gitignore entry**
Append to `.gitignore`:
```
deploy/.env.deploy
```

- [ ] **Step 2: Create `deploy/.env.deploy.example`**
```bash
# Copy to deploy/.env.deploy (gitignored) and fill in. Sourced by lightsail_deploy.sh.
export APP_ENV=production
export DEBUG=false
export OPENAI_API_KEY=sk-...
export DATABASE_URL="postgresql+asyncpg://postgres.<ref>:<pw>@aws-0-eu-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
export SUPABASE_URL=https://<ref>.supabase.co
export SUPABASE_KEY=<service-role-key>
export ENABLED_DOMAINS=housing.deposit.v1
export DEFAULT_DOMAIN=housing.deposit.v1
export DOMAIN_STRICT_EVAL_GATES=false
export LLM_PREDICTION_PROVIDER=openai
export LLM_MEDIATOR_PROVIDER=openai
export LLM_INTAKE_PROVIDER=openai
export LLM_EXTRACTION_PROVIDER=openai
export CORS_ORIGINS="https://<your-frontend-domain>"
```

- [ ] **Step 3: Create `scripts/deploy/lightsail_deploy.sh`**
```bash
#!/usr/bin/env bash
set -euo pipefail
REGION="${AWS_REGION:-eu-west-2}"
SERVICE="${LIGHTSAIL_SERVICE:-proposer-api}"
IMAGE_TAG="proposer-api:latest"
ENV_FILE="${DEPLOY_ENV_FILE:-deploy/.env.deploy}"

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (copy from deploy/.env.deploy.example)"; exit 1; }
# shellcheck disable=SC1090
source "$ENV_FILE"

echo "==> building image (requires data/embeddings present)"
[ -d data/embeddings ] || { echo "data/embeddings missing — build from the checkout that has the corpus"; exit 1; }
docker build -t "$IMAGE_TAG" .

echo "==> pushing image to Lightsail"
REF=$(aws lightsail push-container-image --region "$REGION" --service-name "$SERVICE" \
       --label api --image "$IMAGE_TAG" --output json | python3 -c "import sys,json;print(json.load(sys.stdin)['image'])")
echo "    pushed ref: $REF"

echo "==> building deployment json"
ENV_JSON=$(python3 - <<'PY'
import json, os
keys = ["APP_ENV","DEBUG","OPENAI_API_KEY","DATABASE_URL","SUPABASE_URL","SUPABASE_KEY",
        "ENABLED_DOMAINS","DEFAULT_DOMAIN","DOMAIN_STRICT_EVAL_GATES",
        "LLM_PREDICTION_PROVIDER","LLM_MEDIATOR_PROVIDER","LLM_INTAKE_PROVIDER",
        "LLM_EXTRACTION_PROVIDER","CORS_ORIGINS"]
print(json.dumps({k: os.environ[k] for k in keys if os.environ.get(k) is not None}))
PY
)
CONTAINERS=$(REF="$REF" ENV_JSON="$ENV_JSON" python3 - <<'PY'
import json, os
print(json.dumps({"api": {"image": os.environ["REF"], "ports": {"8000": "HTTP"},
                          "environment": json.loads(os.environ["ENV_JSON"])}}))
PY
)
ENDPOINT='{"containerName":"api","containerPort":8000,"healthCheck":{"path":"/health","successCodes":"200","intervalSeconds":15,"timeoutSeconds":5,"healthyThreshold":2,"unhealthyThreshold":3}}'

echo "==> deploying"
aws lightsail create-container-service-deployment --region "$REGION" --service-name "$SERVICE" \
  --containers "$CONTAINERS" --public-endpoint "$ENDPOINT"
echo "==> deployment created; watch state with:"
echo "    aws lightsail get-container-services --region $REGION --service-name $SERVICE --query 'containerServices[0].{state:state,url:url}'"
```

- [ ] **Step 4: Make it executable + commit**
```bash
chmod +x scripts/deploy/lightsail_deploy.sh
git add scripts/deploy/lightsail_deploy.sh deploy/.env.deploy.example .gitignore
git commit -m "feat(deploy): Lightsail deploy script + deploy-env scaffold"
```

---

## Task 7: First deploy + smoke test

**Files:** none (operational).

- [ ] **Step 1: Fill `deploy/.env.deploy`** from the example (Tasks 3–4 values + your frontend origin in `CORS_ORIGINS`).

- [ ] **Step 2: Deploy** (from the checkout WITH the corpus):
```bash
./scripts/deploy/lightsail_deploy.sh
```
Watch until ACTIVE:
```bash
aws lightsail get-container-services --region eu-west-2 --service-name proposer-api \
  --query 'containerServices[0].{state:state,url:url}'
```
Expected: `state: ACTIVE` and a `url` like `https://proposer-api.<id>.eu-west-2.cs.amazonlightsail.com/`.

- [ ] **Step 3: Smoke test the live URL** (set `BASE=<that url>`):
```bash
curl -s -m 10 "$BASE/health"   # {"status":"healthy",...,"openai_configured":true}
curl -s -m 10 "$BASE/readyz"   # {"status":"ready","alembic_version":"0005"}
curl -s -m 10 "$BASE/domains" | python3 -m json.tool | head   # deposit "live", others "coming_soon"
```
Then an end-to-end check (intake → prediction) confirming the baked corpus loaded:
```bash
SID=$(curl -s -X POST "$BASE/chat/bulk-intake" -H 'Content-Type: application/json' \
  -d '{"role":"tenant","domain_id":"housing.deposit.v1","create_dispute":false,
       "case_text":"Deposit 1200 not protected, landlord withholding 800 for cleaning, no check-in inventory."}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['case_file']['case_id'])")
curl -s -m 180 -X POST "$BASE/predictions/generate" -H 'Content-Type: application/json' \
  -d "{\"case_id\":\"$SID\"}" | python3 -c "import sys,json;d=json.load(sys.stdin);print('outcome',d['overall_outcome'],'cases',d['total_cases_analyzed'])"
```
Expected: an outcome with `total_cases_analyzed > 0`.

- [ ] **Step 4: If the container is unhealthy / OOMs** (check `aws lightsail get-container-log --region eu-west-2 --service-name proposer-api --container-name api`): recreate the service at `--power medium` (4GB) and redeploy.

---

## Task 8: Frontend wiring + runbook doc

**Files:** Create `docs/deploy/lightsail-runbook.md`.

- [ ] **Step 1: Write the runbook** capturing, end-to-end: AWS CLI + Supabase prerequisites; the one-time service create (Task 5); the connection verify + migration (Tasks 3–4); the `deploy/.env.deploy` fields; `./scripts/deploy/lightsail_deploy.sh`; the smoke tests (Task 7); resize-if-OOM; and the **frontend wiring**: deploy the Next.js app (Cloudflare Pages/Vercel) with `NEXT_PUBLIC_API_URL=<Lightsail url>`, and add that frontend origin to `CORS_ORIGINS` in `deploy/.env.deploy` then redeploy. Include the cost note (~$20–40/mo Lightsail + Supabase free + OpenAI usage).

- [ ] **Step 2: Commit**
```bash
git add docs/deploy/lightsail-runbook.md
git commit -m "docs(deploy): Lightsail deployment runbook"
```

---

## Self-Review notes (author)
- **Spec coverage:** Dockerfile+corpus (T2), Lightsail compute + `/health` (T5,T7), Supabase Postgres + TLS caveat (T3) + migrations (T4), Supabase Storage (T4.3), secrets + env (T6), CORS — already env-driven, set via `CORS_ORIGINS` (T6,T8), deploy script (T6), verification (T7), frontend out-of-scope wiring note (T8). All spec sections mapped.
- **Spec drift fixed:** the spec's "CORS code change" is unnecessary on `main` (already env-driven) — T6/T8 just set the env var.
- **Placeholder scan:** credential placeholders (`<ref>`, `<pw>`, `<your-frontend-domain>`, `$BASE`) are operator-supplied values, not plan gaps. No TBD/TODO.
- **Consistency:** service name `proposer-api`, region `eu-west-2`, container port `8000`, env file `deploy/.env.deploy`, and the `DATABASE_URL` (with `sslmode=require` kept for the guardrail while the engine strips it for asyncpg) are used consistently across T3–T8.
- **Build caveat repeated where it matters (T2, T6):** the corpus is gitignored, so build from the checkout that has `data/embeddings`.
