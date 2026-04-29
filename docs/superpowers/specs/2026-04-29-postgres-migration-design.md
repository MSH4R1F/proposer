# SHA-102: JSON → Postgres Storage Migration — Design

**Status:** Approved (2026-04-29)
**Owner:** Mohamed Sharif
**Linear:** [SHA-102](https://linear.app/sharifbuilders/issue/SHA-102/migrate-user-facing-storage-from-json-files-to-postgres)
**Branch:** `feature/sha-102-migrate-user-facing-storage-from-json-files-to-postgres`

## Context

User-facing persistence is currently file-per-entity JSON in `data/`. Six directories, ~330 entities, four concrete failure modes already present:

1. **Cross-entity queries are O(N).** Ablation harness (SHA-32) reads every prediction file. Tolerable now, untenable at 10K+.
2. **Non-atomic writes.** `json.dump` to the same file races; no concurrent-write safety.
3. **No transactions.** `MediationService.settle/escalate` already write to two files non-atomically; partial failure leaves inconsistent state.
4. **Glob-based listing** doesn't scale; ~330-file ceiling visible today.

ChromaDB and raw PDFs stay as-is — different access patterns, already appropriate storage.

The original ticket gates this work behind the thesis deadline (2026-05-20) and trigger conditions (100 paying users, beta launch, >3K entities, prod incident). **Decision (2026-04-29):** the user opted to execute now in parallel with thesis work, accepting the conflict with in-flight SHA-32/68/36 branches and the ~⅓-runway cost.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Stack: SQLAlchemy 2.0 async + Alembic + Pydantic DTOs** | The two hard parts of this migration — transaction boundaries and polymorphic KG nodes — both have first-class SQLA support (`AsyncSession.begin()`, `Mapped[dict]` JSONB). Alembic autogenerate keeps schema-evolution costs low. |
| 2 | **KG nodes: single table, typed columns + JSONB** | 7 polymorphic node types share 7 base fields; per-type fields are read-when-loading-the-graph but never filtered on. Hot fields (`event_date`, `amount`) become indexed columns; the rest goes in `node_data` JSONB. Future node-type evolution = JSONB shape change, no migration. |
| 3 | **Scope includes `evidence_metadata` (7th JSON store, missed by ticket)** | Same pattern, isomorphic to the others. Leaving it as JSON would violate the DoD's "no production code paths touch JSON" line and break FK coherence with KG `EvidenceNode`. |
| 4 | **`dispute_predictions/` becomes a column on `disputes`** | The directory holds 1:1 `{dispute_id, prediction_id}` pointers — a filesystem workaround for "no FKs." On Postgres it's `disputes.cached_prediction_id REFERENCES predictions(prediction_id)`. |
| 5 | **Cutover: hard, single PR (no dual-write feature flag)** | Solo dev, ~330 entities, no production traffic, no users to keep online. Dual-write's complexity buys nothing. JSON dirs renamed to `data/_archive_*` (not deleted) for trivial rollback. |
| 6 | **`CaseFile` and chat `messages` stay as JSONB on `intake_sessions`, not normalized** | KG already extracts CaseFile into structured nodes (Party/Property/Lease/Issue/Evidence/Event). Normalizing CaseFile too would double-store everything and balloon scope into a domain remodel. Chat messages are append-only; no cross-row queries. |
| 7 | **Repository layer between services and SQLA** | Repositories own all `AsyncSession` interaction and Pydantic↔SQLA mapping. Services orchestrate transactions across repositories. Public service APIs unchanged → SHA-32/68/36 callers unaffected. |

## Architecture

### Module layout

```
apps/api/src/
  db/
    __init__.py          # public: get_engine, get_sessionmaker, AsyncSession
    engine.py            # asyncpg pool + SQLAlchemy AsyncEngine
    base.py              # SQLAlchemy DeclarativeBase
    models/              # SQLA ORM models, one file per entity group
      sessions.py
      disputes.py
      predictions.py     # PredictionRow + IssuePredictionRow + ReasoningStepRow + CitationRow
      kg.py              # KnowledgeGraphRow + KGNodeRow + KGEdgeRow
      mediations.py      # MediationSessionRow + MediationMessageRow + StructuredOfferRow
      evidence.py
    repositories/        # async CRUD + Pydantic mapping, one per entity group
      sessions_repo.py
      disputes_repo.py
      predictions_repo.py
      kg_repo.py
      mediations_repo.py
      evidence_repo.py
  alembic/
    env.py               # async Alembic env using same engine
    versions/
      0001_initial_schema.py
```

Repositories are the only code that touches `AsyncSession`. Services consume repositories. Pydantic models stay in `packages/llm_orchestrator/models/` and `packages/kg_builder/models/` as canonical domain types.

### Lifespan wiring (`apps/api/src/main.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(
        config.database_url,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
    )
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    config.ensure_directories()
    yield
    await engine.dispose()
```

### Dependency injection

Existing `get_*_service()` module-level singletons remain. Each service takes a `sessionmaker` injected lazily on first call. New `get_db_session()` FastAPI dependency yields one `AsyncSession` per request.

### Config (`apps/api/src/config.py`)

```python
database_url: str = field(default_factory=lambda: os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
))
```

## Schema

### Tables

13 tables, one Alembic initial migration: `intake_sessions`, `disputes`, `predictions`, `prediction_issues`, `prediction_reasoning_steps`, `prediction_citations`, `knowledge_graphs`, `kg_nodes`, `kg_edges`, `mediations`, `mediation_messages`, `structured_offers`, `evidence_metadata`. Polymorphic KG nodes use typed columns + JSONB; mediation messages, offers, prediction issues/reasoning/citations are normalized into child tables.

```
intake_sessions          ──┬──▶ disputes ──┬──▶ mediations ──┬──▶ mediation_messages
  session_id PK            │     dispute_id PK     │           └──▶ structured_offers
  case_id UNIQ             │     tenant_session_id │
  user_role                │     landlord_session_id
  current_stage            │     status            │
  stages_completed         │     property_*        │
  case_file JSONB          │     deposit_amount    │
  messages JSONB           │     cached_prediction_id ──┐
  started_at, updated_at   │                            │
                           │                            ▼
                           │                       predictions ──┬──▶ prediction_issues
                           │                         prediction_id PK    └──▶ prediction_reasoning_steps
                           │                         case_id IDX         └──▶ prediction_citations
                           │                         overall_outcome     (reasoning_step_id NULL
                           │                         overall_confidence   for top-level verified)
                           │                         pipeline_version
                           │                         pipeline_metadata JSONB
                           │
                           └──▶ evidence_metadata
                                  evidence_id PK
                                  case_id IDX
                                  evidence_type
                                  blob_url
                                  payload JSONB

knowledge_graphs ──┬──▶ kg_nodes (single table, polymorphic)
  case_id PK       │     node_id PK
  graph_id UNIQ    │     case_id FK
                   │     node_type ENUM        ← discriminator
                   │     confidence, source, source_text, created_at
                   │     event_date IDX        ← only EventNode (timeline)
                   │     amount IDX            ← only ClaimedAmountNode
                   │     node_data JSONB       ← type-specific fields
                   │     metadata JSONB
                   │
                   └──▶ kg_edges (uniform)
                         edge_id PK
                         case_id FK
                         edge_type ENUM
                         source_node_id FK
                         target_node_id FK
                         confidence, source, description
                         metadata JSONB
```

### Postgres enums (~14)

`user_role`, `intake_stage`, `dispute_status`, `outcome_type`, `issue_outcome`, `issue_type`, `evidence_strength`, `evidence_type`, `mediation_status`, `message_type`, `offer_status`, `node_type`, `edge_type`, `party_role`. Self-documenting and rejects bad writes at the DB layer.

### Indexes

| Table | Index | Reason |
|---|---|---|
| `intake_sessions` | `(case_id)` UNIQUE | `get_case_file()` lookup |
| `disputes` | `(invite_code)` UNIQUE, `(tenant_session_id)`, `(landlord_session_id)` | invite-join flow + reverse session lookup |
| `predictions` | `(case_id)`, `(created_at)`, `(pipeline_version)` | ablation harness, list-for-case, version filtering |
| `prediction_issues` | `(prediction_id)`, `(issue_type)` | per-prediction fan-out |
| `prediction_citations` | `(prediction_id)`, `(reasoning_step_id)` | trace reconstruction |
| `kg_nodes` | `(case_id, node_type)`, `(case_id, event_date) WHERE node_type='event'` | type filter + timeline |
| `kg_edges` | `(source_node_id, target_node_id, edge_type)`, `(case_id, edge_type)` | traversal + type filter |
| `mediations` | `(dispute_id)` UNIQUE | 1:1 with dispute |
| `mediation_messages` | `(mediation_id, created_at)`, `(offer_id)` | thread fetch + offer reverse |
| `structured_offers` | `(mediation_id)`, `(status)` | pending-offer scan |
| `evidence_metadata` | `(case_id)`, `(evidence_type)` | per-case fan-out |

### Decisions worth flagging

1. **`mediation_messages.offer_id`** is a real FK column (not buried in JSONB) — enables "messages referencing accepted offers" queries.
2. **`prediction_citations`** unifies `reasoning_trace[].citations` and `citation_verification.verified_citations[]` via nullable `reasoning_step_id`. Single table, single query path.
3. **`predicted_settlement_range`** stored as `range_lo` / `range_hi` numerics, not `int4range`. Simpler ORM, no range queries planned.
4. **`disputes.cached_prediction_id`** has no `ON DELETE CASCADE` — clearing a prediction shouldn't nuke the dispute.
5. **No `users` / `auth` tables.** Auth is Supabase per CLAUDE.md.

## Transactions

The four atomicity hazards become four transaction blocks. Services own the transaction; repositories never commit.

| Operation | Current shape | New shape |
|---|---|---|
| `MediationService.start_mediation()` (mediation_service.py:228–229) | dispute write + mediation write, two files | `async with session.begin():` → update dispute, insert mediation |
| `MediationService.respond_to_offer → accept → settle` (m_s.py:415, 495–499) | offer + mediation + dispute, three files | `async with session.begin():` → update offer, mediation, dispute |
| `MediationService.escalate()` (m_s.py:523–526) | session + dispute, two files | `async with session.begin():` → update mediation, dispute |
| `IntakeService.process_message → DisputeService.update_dispute_from_session` (i_s.py:203–220) | session save + dispute sync, two files | `async with session.begin():` → upsert session, dispute |

Each transaction gets an integration test that monkeypatches the second repository call to raise, asserts no half-written state.

## Backfill

### Script

`scripts/migrations/backfill_json_to_postgres.py` — idempotent, dry-run-first.

```bash
python scripts/migrations/backfill_json_to_postgres.py --data-dir ./data --dry-run
python scripts/migrations/backfill_json_to_postgres.py --data-dir ./data --commit
```

Order (FK-dependency-driven):

1. `intake_sessions` (no FKs out)
2. `disputes` (FK to sessions; `cached_prediction_id` left NULL on first pass)
3. `predictions` + `prediction_issues` + `prediction_reasoning_steps` + `prediction_citations`
4. `dispute_predictions` JSON files → `UPDATE disputes SET cached_prediction_id = ?`
5. `knowledge_graphs` + `kg_nodes` + `kg_edges`
6. `mediations` + `mediation_messages` + `structured_offers`
7. `evidence_metadata`

Each stage:
- Reads JSON files, validates against existing Pydantic models (catches stale-disk drift before insert).
- Skips entities that already exist (idempotent re-runs).
- Logs counts + skipped/failed records to `data/_backfill_report.jsonl`.
- After commit, renames source dir to `data/_archive_<dir>` to prevent old code paths from re-using it.

### Round-trip identity test (DoD)

`tests/integration/test_roundtrip.py` — runs after backfill in CI.

```python
@pytest.mark.parametrize("entity_type", ["session", "dispute", "prediction", "kg", "mediation", "evidence"])
async def test_roundtrip_identity(entity_type, postgres_session, source_archive_dir):
    for json_path in source_archive_dir.glob(f"{entity_type}_*.json"):
        original = load_json(json_path)
        reloaded = await load_via_repo(entity_type, original["id"], postgres_session)
        assert reloaded.model_dump(mode="json") == OriginalModel.model_validate(original).model_dump(mode="json")
```

The firewall against schema-design errors. If it passes for every entity in `data/_archive_*` (audit count: 240 sessions, 42 predictions, 16 KGs, 22 disputes, 4 mediations, plus existing evidence-metadata files — count established by the backfill `--dry-run` pass), the schema is right.

### Reverse-backfill (rollback insurance)

`scripts/migrations/dump_postgres_to_json.py` — 50-line companion. Written even if never used.

## Testing

### Fixture swap: `pytest-postgresql`

Chosen over testcontainers because:
- Local Postgres binary already required (and brought up by `make db-up`); no Docker dependency for unit tests.
- 5–10× faster startup per session than container spin-up.

```python
# apps/api/tests/conftest.py
@pytest_asyncio.fixture
async def db_session(postgresql):
    engine = create_async_engine(make_async_url(postgresql))
    async with engine.connect() as conn:
        async with conn.begin() as tx:
            session = AsyncSession(bind=conn)
            yield session
            await tx.rollback()  # transactional rollback per test, no truncate needed
    await engine.dispose()
```

Existing fixtures (`mediation_service`, `temp_data_dir`, etc.) get rewritten to take `db_session` instead of `tmp_path`. Test bodies stay identical — that's the payoff for the repository abstraction.

### New integration tests (DoD requirements)

| Test | Location | Asserts |
|---|---|---|
| Round-trip identity | `tests/integration/test_roundtrip.py` | every backed-up JSON entity reloads identically |
| Concurrent writes | `tests/integration/test_concurrent_writes.py` | two simultaneous dispute updates don't lose data (currently fails on JSON) |
| Mid-transaction crash | `tests/integration/test_atomicity.py` | each of the 4 transaction boundaries leaves no half-written state when the second repo call raises |

## Phasing

Single feature branch `feature/sha-102-postgres-migration`, single PR at the end. Internal commit order for reviewer step-through:

| # | Title | Lands |
|---|---|---|
| 1 | infra: add asyncpg/sqlalchemy/alembic deps + DATABASE_URL config | `requirements.txt`, `config.py`, `apps/api/src/db/engine.py`, `db/base.py`, lifespan wiring |
| 2 | schema: initial Alembic migration covering 13 tables + enums | `alembic/env.py` async, `alembic/versions/0001_initial_schema.py` |
| 3 | repos: SQLAlchemy models + repositories for all 7 entities | `apps/api/src/db/models/`, `apps/api/src/db/repositories/`; repo unit tests |
| 4 | services: swap IntakeService + DisputeService to repos | service files modified, public APIs unchanged; existing tests rewritten on `db_session` fixture |
| 5 | services: swap PredictionService + dispute_predictions cache column | predictions service refactor; roundtrip test for predictions |
| 6 | services: swap KG (delete `JSONGraphStore`) + StorageService evidence metadata | KG repo, evidence repo; KG roundtrip + polymorphic node read/write tests |
| 7 | services: swap MediationService + add transaction boundaries | mediation service + atomicity test cases; concurrent-write test |
| 8 | tooling: backfill script + roundtrip integration test | `scripts/migrations/backfill_json_to_postgres.py`, `tests/integration/test_roundtrip.py`; dry-run on real `data/` |
| 9 | infra: docker-compose Postgres + Makefile + CI workflow | `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml` |
| 10 | docs: README setup, dev-onboarding update, archive rename | README, `docs/ORCHESTRATION.md` note |

## Infra

### `docker-compose.yml` (new, sibling of existing `docker-compose.langfuse.yml`)

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: proposer
      POSTGRES_PASSWORD: proposer-dev
      POSTGRES_DB: proposer
    ports: ["5432:5432"]
    volumes: [proposer_pg_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U proposer"]
      interval: 5s
      timeout: 3s
      retries: 5
volumes:
  proposer_pg_data:
```

### `Makefile` (new — none exists today)

```make
.PHONY: db-up db-down db-reset migrate test eval

db-up:
	docker compose up -d postgres
	@until pg_isready -h localhost -U proposer -q; do sleep 0.5; done

db-down:
	docker compose down

db-reset: db-down
	docker compose rm -fv postgres
	$(MAKE) db-up
	$(MAKE) migrate

migrate:
	alembic upgrade head

test: db-up migrate
	pytest

eval: db-up migrate
	python scripts/eval/run_eval.py
```

### CI workflow (new — `.github/workflows/` does not exist today)

`.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_USER: proposer, POSTGRES_PASSWORD: proposer-dev, POSTGRES_DB: proposer }
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-timeout 3s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: alembic upgrade head
        env: { DATABASE_URL: postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer }
      - run: pytest
        env: { DATABASE_URL: postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer }
```

## Rollback

JSON files are renamed to `data/_archive_<dir>` rather than deleted. To roll back:

1. `git revert <merge_commit>` — service code returns to JSON layer.
2. Rename `data/_archive_*` back to `data/<dir>`.
3. `data/_backfill_report.jsonl` shows what was migrated; any new entities written to Postgres after cutover are recovered with `scripts/migrations/dump_postgres_to_json.py`.

## Risks

| Risk | Mitigation |
|---|---|
| In-flight branches (SHA-32/68/36) conflict on services | Land migration as commits 1–10 in deterministic order; rebase those branches onto the merged result. Rebase notes in PR description. |
| Pydantic ↔ SQLAlchemy drift over time | CI step `python scripts/check_model_alignment.py` walks each repo class and asserts every `Mapped[...]` column has a matching Pydantic field of compatible type. Fails CI on drift. |
| Local-dev friction from new Postgres dep | `make db-up` is one command; pattern already exists in `docker-compose.langfuse.yml`. README onboarding updated. |
| KG `find_path()` BFS multi-hop traversal not ported | Currently dead code (zero call sites in repo). Deferred. If SHA-15 (KG Activation) wakes it up, it gets a recursive-CTE port at that time. |
| Schema migration discovers shape errors mid-stream | Round-trip test on real `data/` runs in commit 8 — before any service swap is merged. Catches schema errors before they hit production paths. |
| Thesis runway pressure (user accepted this trade-off) | Public service APIs unchanged → SHA-32/68/36 keep working. If migration slips past ~10 days of effort, halt and re-evaluate. |

## Definition of Done (from ticket, restated against this design)

- [x] All 7 user-facing stores write to Postgres; JSON files no longer touched in production code paths *(7th = `evidence_metadata` added to scope)*
- [x] Backfill script runs idempotently against a stale JSON checkout
- [x] Round-trip test asserts dump→reload identity for every existing entity in `data/`
- [x] All existing tests pass against `pytest-postgresql` fixture
- [x] `docker-compose up` brings up Postgres locally; `make test` runs against it
- [x] CI green on the new test job
- [x] Concurrent-write integration test: two simulated requests touching the same dispute don't lose data
- [x] Transaction integration test: mid-transaction crash leaves no half-written state
- [x] README + dev setup docs updated
- [x] All 6 source dirs (+ `evidence_metadata`) removed from production write paths (kept as `data/_archive_*` until Phase 4 stable)
- [x] No regression in existing API contracts (intake / prediction / mediation endpoints respond identically)

## Out of scope (carved out)

- ChromaDB (vector store) — different access pattern, already a real DB.
- `data/raw/bailii/` PDFs — files-on-disk are correct storage for source documents.
- KG `find_path()` recursive-CTE port — dead code today, deferred to SHA-15.
- Read-replica / sharding / managed-Postgres deployment — single-instance is enough until 1k+ paying users.
- New analytical queries / admin dashboard — separate ticket once schema lands.
- Normalizing `CaseFile` and chat `messages` out of JSONB into structured tables — would balloon scope into a domain remodel; KG already covers the structured-query view of CaseFile.
