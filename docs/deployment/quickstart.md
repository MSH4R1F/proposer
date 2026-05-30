# Clean-environment quickstart (examiner reproduction)

This guide takes a **fresh `git clone` on a clean machine** to a working
end-to-end run of Proposer: **intake → prediction → mediation → settlement**,
served on `localhost`.

Two API keys (Anthropic + OpenAI) are required. Postgres runs in Docker; the
API and web app run on the host. Allow **~45–90 minutes** end to end, most of it
spent scraping the corpus and building the vector index in step 5.

---

## 0. What a fresh clone does and does **not** contain

A `git clone` gives you all the **code**, database migrations, evaluation
artifacts, and the demo case files. It deliberately does **not** include:

| Not in the clone | Why | How you get it |
|------------------|-----|----------------|
| `.env` (API keys, secrets) | gitignored | Copy `.env.example` → `.env` and fill in (step 3) |
| Raw corpus PDFs (`data/raw/**`) | gitignored; redistribution-restricted (see the `SOURCE_RIGHTS.md` files) | Scrape from source (step 5) |
| Vector index (`data/embeddings/chroma.sqlite3`, `bm25_index.pkl`, ~860 MB) | gitignored; large and rebuildable | Rebuild by ingesting the scraped corpus (step 5) |

Because the corpus and index are rebuilt rather than shipped, RAG retrieval
results are **not bit-for-bit reproducible** — they depend on what the source
sites serve at scrape time. The *system behaviour* (cited prediction →
mediation → settlement) reproduces; the exact precedents cited may differ.

---

## 1. Prerequisites

Install on the clean machine:

- **Git**
- **Python 3.11+** — the system `python3` on macOS is often 3.9, which is too
  old. Verify with `python3.11 --version` (or your 3.11+ interpreter).
- **Node.js 18+** and **npm 9+**
- **Docker Desktop** (for Postgres)
- **~2 GB free disk** for the rebuilt index
- **API keys** (both required):
  - `ANTHROPIC_API_KEY` — Claude, used for intake/prediction/mediation reasoning
  - `OPENAI_API_KEY` — embeddings, used during corpus ingest **and** every query

---

## 2. Clone and install

```bash
git clone git@github.com:MSH4R1F/proposer.git
cd proposer

# Python environment (3.11+)
python3.11 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# Frontend
cd apps/web && npm install && cd ../..
```

All `python`/`pip` commands below assume the venv is **activated**.

---

## 3. Environment variables

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
```

The defaults already in `.env.example` work for local reproduction:

- `APP_ENV=local`
- `DATABASE_URL=postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer`
  (matches the Docker Compose Postgres in step 4)
- `DATA_DIR=./data`, `CHROMA_PERSIST_DIR=./data/embeddings`

`SUPABASE_*` are optional — evidence storage falls back to local disk without
them. Keep `DOMAIN_STRICT_EVAL_GATES` unset/false for local dev (the demo runs
on `housing.deposit.v1`).

---

## 4. Database (Docker Compose)

Compose runs **Postgres only**; the API and web app run on the host.

```bash
make db-up      # starts Postgres 16 in Docker and waits until ready
make migrate    # alembic upgrade head
```

To start over later: `make db-reset` (local-only; drops the volume and
re-migrates).

---

## 5. Build the RAG index (scrape → ingest)

This is the longest step. Prediction returns cited precedent only once the
vector index exists, so it must be built before the demo.

```bash
# OPENAI_API_KEY must be set (it's read from .env, or export it explicitly)

# 5a. Preview what the scraper would fetch (no downloads)
python -m scripts.scrapers.bailii_scraper --dry-run --years 2024

# 5b. Scrape the corpus (network + time heavy; resumable)
python -m scripts.scrapers.bailii_scraper --year-range 2020-2025
#   --resume    continue an interrupted scrape
#   --stats     show progress / counts
# PDFs land under data/raw/bailii/{deposit-cases,adjacent-cases,other-cases}/

# 5c. Ingest the PDFs into the vector index (chunk → embed → Chroma + BM25)
python scripts/rag.py ingest --pdf-dir data/raw/bailii

# 5d. Verify the index is populated
python scripts/rag.py stats
python scripts/rag.py query "tenant deposit not protected within 30 days"
```

Notes:
- Ingest calls the OpenAI embeddings API and is the main driver of build time
  and cost.
- A larger corpus yields better-grounded predictions. The minimum for a
  meaningful demo is enough deposit/adjacent cases that `rag.py query` returns
  relevant precedent.
- If the index ever looks corrupted, `python scripts/rag.py clear` then re-run
  5c, or `python scripts/rebuild_bm25.py` to rebuild just the BM25 side.

---

## 6. Run the app

Two terminals, both with the venv activated and from the repo root.

```bash
# Terminal A — API
python scripts/api.py
# → http://localhost:8000   (Swagger: http://localhost:8000/docs)

# Terminal B — Web
cd apps/web && npm run dev
# → http://localhost:3000
```

---

## 7. Verify end to end

The fastest check runs the whole flow through the API (no browser):

```bash
python scripts/demo/run_full_flow.py --scenario both
```

This performs bulk intake, generates a prediction, has the second party join
via invite code, starts mediation, exchanges an offer, and settles — for both
the tenant-led and landlord-led scenarios. It writes
`docs/demo/last-run.json` with the dispute/session IDs, predicted outcome and
settlement range, and deep links such as:

```
http://localhost:3000/prediction/{caseId}?session={sessionId}&dispute={disputeId}
```

Open that prediction URL in the browser to see the cited reasoning trace, then
follow the mediation links to the settlement.

For the **manual UI walkthrough**, copy-paste case texts, and per-endpoint
`curl` examples, see [`../demo/RUNBOOK.md`](../demo/RUNBOOK.md). The sample
cases live in [`../demo/example-cases/`](../demo/example-cases/).

---

## 8. Smoke checks

```bash
curl http://localhost:8000/docs            # API is up
curl -X POST http://localhost:8000/chat/start \
  -H 'Content-Type: application/json' -d '{"role": "tenant"}'
```

---

## 9. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `command not found: python` / wrong version | Activate the venv (`source venv/bin/activate`); the interpreter must be **3.11+**, not the system 3.9 |
| `ModuleNotFoundError: No module named 'aiolimiter'` (or other scraper dep) | `pip install -r requirements.txt` — it now declares the scraper deps. On an older clone: `pip install aiolimiter` |
| Postgres connection refused | `make db-up` (waits for readiness); confirm `docker ps` shows the `postgres` container |
| Prediction returns empty / "uncertain" / abstains | Index not built or empty — run step 5c again and confirm `python scripts/rag.py stats` shows documents |
| OpenAI 401 during ingest or query | `OPENAI_API_KEY` missing/invalid in `.env` |
| Anthropic 401 during prediction/mediation | `ANTHROPIC_API_KEY` missing/invalid in `.env` |
| Port 8000 already in use | `python scripts/api.py --port 8080` (update the web client base URL accordingly) |
| Cannot send mediation chat messages in the UI | Add `?role=tenant` or `?role=landlord` to the mediation chat URL (see RUNBOOK) |

---

## Definition of Done (SHA-73)

- **Demo video published** — see `docs/demo/videos/`.
- **Deployment guide validated by a fresh `git clone`** — this document; the
  scrape-then-ingest path in step 5 rebuilds the corpus and index that the
  clone omits, and step 7 confirms the full intake → prediction → mediation →
  settlement flow.
