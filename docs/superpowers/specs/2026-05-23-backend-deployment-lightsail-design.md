# Backend Deployment — AWS Lightsail (thesis demo) — Design

**Date:** 2026-05-23
**Status:** Approved (brainstorming) — pending implementation plan
**Scope:** Deploy the **FastAPI backend** (`apps/api` + `packages/*`) to AWS for a low-traffic thesis demo. Frontend deployment is out of scope.

## Overview

The Proposer backend is a stateful Python service: FastAPI/uvicorn + Postgres (app state) + a ~1.1GB ChromaDB vector store (RAG) + OpenAI (LLM/embeddings) + optional Langfuse. It is **not** serverless-friendly, so it deploys as a **container with the vector corpus baked into the image** onto **AWS Lightsail Container Service**, backed by **Supabase Postgres** (and Supabase Storage for evidence files). Target: cheap (~$20–40/mo), simple, low-maintenance.

## Goals
- One reproducible container image that serves the API with the deposit corpus baked in.
- Managed Postgres (TLS) satisfying the app's `APP_ENV=production` guardrails.
- A documented one-command deploy + a one-time DB migration step.
- Live verification: health, readiness, `/domains`, and one intake→prediction smoke test.

## Non-Goals
- Frontend deployment (separate; Cloudflare Pages/Vercel).
- Autoscaling / HA / multi-region (single Lightsail instance is fine for a demo).
- A mutable/managed vector store (Pinecone, EFS) — corpus is baked, immutable; rebuild the image to update it.
- Enabling non-deposit domains (still gated "coming soon"; only `housing.deposit.v1` ships).
- Langfuse observability (omitted for the demo; can be added via env later).

## Background — current state
- No Dockerfile / deploy config exists; the API runs via `python scripts/api.py` (uvicorn `main:app`, host `0.0.0.0`, port 8000). `scripts/api.py` sets `sys.path` (project root, `packages/`, `apps/api/src`), `chdir`s to the project root, and `load_dotenv()`s.
- `apps/api/src/config.py` `APIConfig.from_env()` enforces, when `APP_ENV=production`: `DEBUG=false`; a non-local `DATABASE_URL`; and `sslmode in {require, verify-ca, verify-full}` present in the URL string. Reads `OPENAI_API_KEY`, `ENABLED_DOMAINS`, `DEFAULT_DOMAIN`, `DOMAIN_STRICT_EVAL_GATES`, `SUPABASE_URL`, `SUPABASE_KEY`, `HOST`, `PORT`.
- CORS `allowed_origins` is **hardcoded to localhost** (`main.py`) — must become env-driven for the deployed frontend.
- The corpus lives at `data/embeddings/` (chroma.sqlite3 + bm25_index.pkl + HNSW index, ~1.1GB) in the **main repo**; in this worktree it's a **symlink**.
- Evidence uploads go to `data/evidence_files/` with a Supabase Storage path when `SUPABASE_URL`/`SUPABASE_KEY` are set.

## Design

### 1. Container image (`Dockerfile` + `.dockerignore`)
Multi-stage:
- **builder:** `python:3.11-slim`; install build deps; `pip install -r requirements.txt` into `/opt/venv`.
- **runtime:** `python:3.11-slim`; copy `/opt/venv`; copy `apps/`, `packages/`, `scripts/`, `alembic.ini`; copy `data/embeddings/` (baked corpus). Non-root user. `EXPOSE 8000`. `CMD ["python", "scripts/api.py"]` (serves uvicorn on `0.0.0.0:8000`).

`.dockerignore` excludes `.git`, `apps/web/node_modules`, `venv`, `data/raw`, `data/indices`, `data/eval*`, `data/test-cases`, `data/processed`, `**/__pycache__`, `*.bak`, keeping the build context to code + `data/embeddings`.

**Build gotcha:** build from the **main repo root** (`/Users/.../legal-mediation-system`), where `data/embeddings` is a real directory. Docker `COPY` does not follow the worktree's symlink. Image ≈ 1.7GB (1.1GB corpus + ~0.5GB deps).

### 2. Compute — Lightsail Container Service
- Service "small" power (2 GB RAM, 1 vCPU, ~$20/mo). **Resize to "medium" (4 GB, ~$40/mo) if the container OOMs** loading the HNSW index — memory is the main risk; validate after first deploy.
- 1 node, scale 1. Public endpoint with built-in HTTPS + a `*.cs.amazonlightsail.com` URL (custom domain optional, out of scope).
- Container port 8000; Lightsail routes 443→8000.
- **Health check:** path `/health`, success codes 200. (`/readyz` is DB-dependent and would flap the LB; keep it for manual checks.)

### 3. Postgres — Supabase
- A Supabase project's managed Postgres. **Use the IPv4-compatible Supavisor *session-mode* pooler** connection string (`postgresql+asyncpg://postgres.[ref]:[pw]@aws-0-[region].pooler.supabase.com:5432/postgres`), not the transaction pooler (6543) — the transaction pooler breaks asyncpg prepared statements. Append `sslmode=require` to satisfy the config guardrail.
- **Known integration point (verify first in the plan):** the app validates the string `sslmode=require`, but **asyncpg ignores `sslmode`** (it uses `ssl=`). Verify `create_engine_from_url` actually negotiates TLS to Supabase — likely needs `connect_args={"ssl": True}` (or `?ssl=require`) while keeping `sslmode=require` in the string for the guardrail. Resolve in the plan's first task with a real connection test; if asyncpg also chokes on prepared-statement caching via the pooler, set `statement_cache_size=0`.
- **Migrations:** one-time `DATABASE_URL=<supabase> alembic -c alembic.ini upgrade head` (run locally against Supabase, or as a release step), repeated on schema changes. `/readyz` reads `alembic_version` to confirm.

### 4. Evidence file storage — Supabase Storage
Set `SUPABASE_URL` + `SUPABASE_KEY` (service role) so evidence uploads persist in Supabase Storage (the app already supports this with a local fallback). Create the storage bucket the app expects.

### 5. Config / secrets (Lightsail container env vars)
`APP_ENV=production`, `DEBUG=false`, `OPENAI_API_KEY`, `DATABASE_URL` (Supabase session pooler, `sslmode=require`), `SUPABASE_URL`, `SUPABASE_KEY`, `ENABLED_DOMAINS=housing.deposit.v1`, `DEFAULT_DOMAIN=housing.deposit.v1`, `DOMAIN_STRICT_EVAL_GATES=false`, `LLM_*_PROVIDER=openai`, `CORS_ALLOWED_ORIGINS=<frontend origin>`. No `.env` baked into the image. Langfuse vars omitted.

### 6. CORS (code change)
Make `main.py` read `CORS_ALLOWED_ORIGINS` (comma-separated) and merge with the existing localhost defaults, instead of the hardcoded list. Contained change in `config.py` (add the field) + `main.py` (use it). Default (unset) keeps current localhost behavior, so dev is unaffected.

### 7. Deploy mechanism
A documented script `scripts/deploy/lightsail_deploy.sh` (+ a `make deploy` target), using the AWS CLI:
1. `docker build` (from main repo root) → tag.
2. `aws lightsail push-container-image --service-name proposer-api --label api --image proposer-api:latest`.
3. `aws lightsail create-container-service-deployment` with the container (image ref from step 2), port 8000, the env vars (secrets passed at deploy time, not committed), and the `/health` health check.
Prereqs documented: AWS CLI configured, the Lightsail container service created once (`create-container-service --power small --scale 1`). A GitHub Actions deploy workflow is a noted optional follow-up; manual script ships first.

### 8. Verification (post-deploy)
Against the Lightsail HTTPS URL: `GET /health` → 200 (anthropic false/openai true expected); `GET /readyz` → 200 with `alembic_version`; `GET /domains` → catalog (deposit `live`, 4 `coming_soon`); `POST /chat/bulk-intake` (deposit, tenant) then `POST /predictions/generate` → a real prediction with cited cases (confirms the baked corpus loaded).

## Risks & mitigations
1. **Memory** — the Chroma HNSW index + runtime may exceed 2 GB. Mitigation: start "small", resize to "medium" if it OOMs (validate in deploy).
2. **Supabase asyncpg TLS / pooler** — `sslmode` vs `ssl=`, and pooler/prepared-statement caveats (§3). Mitigation: a connection-test task first; use the session pooler + `connect_args`/`statement_cache_size=0` as needed.
3. **Image size / push time** — ~1.7GB image is slow to build/push. Acceptable for infrequent demo deploys; `.dockerignore` keeps the context minimal.
4. **Corpus build source** — must build from the main repo (real `data/embeddings`), not the symlinked worktree.
5. **First-request latency** — Chroma/BM25 load lazily on the first prediction; expect a slow first prediction after deploy.

## Rollout
1. CORS env change (code) → 2. Dockerfile + .dockerignore → 3. Supabase project + connection test + migrations → 4. Lightsail service + first deploy (resize if OOM) → 5. smoke test → 6. point the (separately deployed) frontend's `NEXT_PUBLIC_API_URL` at the Lightsail URL and add its origin to `CORS_ALLOWED_ORIGINS`.

**Cost:** Lightsail ~$20–40/mo + Supabase free tier + OpenAI usage (pay-per-use).
