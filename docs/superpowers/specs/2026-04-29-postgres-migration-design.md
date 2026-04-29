# SHA-102: JSON -> Postgres Storage Migration - Design + Implementation Plan

**Status:** Approved conceptually; amended after multi-agent review (2026-04-29)
**Owner:** Mohamed Sharif
**Linear:** [SHA-102](https://linear.app/sharifbuilders/issue/SHA-102/migrate-user-facing-storage-from-json-files-to-postgres)
**Branch:** `feature/sha-102-migrate-user-facing-storage-from-json-files-to-postgres`

## Verdict

The migration is the right architectural direction, but the original plan was not safe to implement as written. The hard part is not "Postgres instead of JSON"; it is replacing file-backed service state with one clear transactional runtime boundary.

Implementation should proceed only with these amendments:

1. Use a real Unit of Work boundary, with one `AsyncSession` shared across all repositories participating in a business workflow.
2. Remove process-local persistence maps (`_sessions`, `_disputes`, `_mediations`) from production paths. Singleton LLM clients are fine; singleton mutable storage is not.
3. Store canonical aggregate payloads in `JSONB` plus indexed projection columns/child rows for query performance.
4. Run data audit and repository round-trip tests before service cutover.
5. Archive JSON dirs only after full verification and smoke tests.

## Context

User-facing persistence is currently file-per-entity JSON in `data/`. There are six existing user-facing directories in the checked-out data set:

- `sessions` - 240 files
- `predictions` - 42 files
- `knowledge_graphs` - 16 files
- `disputes` - 22 files
- `dispute_predictions` - 7 files
- `mediations` - 4 files

`evidence_metadata` is also a user-facing write path in `StorageService`, even if there are no current files in the checked-out data set. ChromaDB, BM25 indexes, raw PDFs, and local uploaded evidence files stay as files/object storage because their access pattern is not relational.

Current failure modes:

1. Cross-entity queries are O(N), especially prediction listing and admin-style scans.
2. File writes are not uniformly atomic; concurrent writes can lose data.
3. Multi-entity workflows have no transaction boundary.
4. In-memory service caches can diverge from disk and will diverge from Postgres unless removed.
5. Filesystem/object storage side effects cannot be made transactionally atomic with database rows, so evidence upload/delete needs compensation logic.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Stack: SQLAlchemy 2.0 async + asyncpg + Alembic + Pydantic DTOs** | Async SQLAlchemy gives explicit transaction control and integrates cleanly with FastAPI. Pydantic models remain the canonical domain contracts. |
| 2 | **Unit of Work owns sessions and transactions** | Repositories never commit. Services or workflow methods open one UoW and pass the same `AsyncSession` to every repository call in the workflow. |
| 3 | **Canonical `payload JSONB` per aggregate + projected columns/children** | Strict round-trip identity is realistic, while hot queries still get indexes and normalized child tables. |
| 4 | **KG nodes use composite identity `(case_id, node_id)`** | `GraphBuilder` emits deterministic node IDs such as `party_tenant`, `property_main`, `lease_main`, and `issue_{type}` that repeat across cases. `node_id` cannot be a global PK. |
| 5 | **No FK from prediction/KG `case_id` to `intake_sessions.case_id`** | Merged two-party predictions use synthetic IDs like `merged-...` that do not correspond to a single intake session. |
| 6 | **`dispute_predictions/` becomes `disputes.cached_prediction_id`** | The JSON directory is a 1:1 pointer workaround. Postgres should model it as a nullable FK to `predictions(prediction_id)`. |
| 7 | **`evidence_metadata` is in scope; evidence files are not** | Metadata is relational and user-facing. Uploaded blobs remain Supabase/local files with cleanup compensation. |
| 8 | **Hard cutover, no dual-write, but audit-first** | Solo dev, small data set, no production traffic. Dual-write is more complexity than value, but final archiving happens only after verification. |
| 9 | **SQLAlchemy models avoid reserved `metadata` attribute names** | Use `metadata_ = mapped_column("metadata", JSONB)` wherever a table has a `metadata` column. |

## Architecture

### Module Layout

```
apps/api/src/
  db/
    __init__.py
    engine.py              # AsyncEngine + async_sessionmaker
    base.py                # DeclarativeBase
    uow.py                 # UnitOfWork and UnitOfWorkFactory
    models/
      sessions.py
      disputes.py
      predictions.py
      kg.py
      mediations.py
      evidence.py
    repositories/
      sessions_repo.py
      disputes_repo.py
      predictions_repo.py
      kg_repo.py
      mediations_repo.py
      evidence_repo.py
  alembic/
    env.py
    versions/
      0001_initial_schema.py
alembic.ini
scripts/
  migrations/
    audit_json_stores.py
    backfill_json_to_postgres.py
    dump_postgres_to_json.py
```

### Runtime Boundary

One workflow gets one Unit of Work.

```python
class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.sessions = SessionsRepo(session)
        self.disputes = DisputesRepo(session)
        self.predictions = PredictionsRepo(session)
        self.kg = KnowledgeGraphRepo(session)
        self.mediations = MediationsRepo(session)
        self.evidence = EvidenceRepo(session)
```

Services should not call `get_*_service()` from inside transactional workflows. If a workflow needs session + dispute + prediction writes, the top-level method uses the same UoW and talks to the required repositories directly.

Allowed singleton state:

- LLM clients
- RAG pipeline instances
- deterministic builders/processors without mutable persistence state

Disallowed production state:

- `_sessions`
- `_disputes`
- `_invite_code_index`
- `_mediations`
- private `_save_*` methods used by other services or routers

### FastAPI Wiring

`create_app(settings)` must capture the provided settings in its lifespan factory. The current global `config` capture is not test-friendly.

```python
def create_lifespan(settings: APIConfig):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
        )
        app.state.engine = engine
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        settings.ensure_directories()
        yield
        await engine.dispose()

    return lifespan
```

`get_db_session(request)` reads `request.app.state.sessionmaker`. For business workflows, prefer a UoW factory over passing raw sessions through service internals.

### Config

Current config is a Pydantic `BaseModel`, so use `Field`, not dataclass `field`.

```python
database_url: str = Field(
    default_factory=lambda: os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
    )
)
```

## Schema

### Core Rule

Every migrated aggregate table stores the canonical Pydantic dump in `payload JSONB`. Projected columns and child rows exist for lookup, filtering, joins, and future analytics. Repositories must be able to reconstruct the Pydantic model from rows and also compare against `payload` in tests.

This keeps the system honest: exact rollback/round-trip remains possible, while the DB still solves the O(N), FK, and transaction problems.

### Tables

13 tables remain in scope:

- `intake_sessions`
- `disputes`
- `predictions`
- `prediction_issues`
- `prediction_reasoning_steps`
- `prediction_citations`
- `knowledge_graphs`
- `kg_nodes`
- `kg_edges`
- `mediations`
- `mediation_messages`
- `structured_offers`
- `evidence_metadata`

### Aggregate Columns

`intake_sessions`

- `session_id PK`
- `case_id UNIQUE`
- `user_role`
- `current_stage`
- `started_at TEXT`
- `updated_at TEXT`
- `payload JSONB NOT NULL`
- projected fields: `intake_complete`, `completeness_score`, `role_explicitly_set`

`disputes`

- `dispute_id PK`
- `invite_code UNIQUE NOT NULL`
- `status`
- `created_at TEXT`
- `updated_at TEXT`
- `created_by_role`
- `tenant_session_id` nullable FK to `intake_sessions(session_id)`
- `landlord_session_id` nullable FK to `intake_sessions(session_id)`
- `property_address`
- `property_postcode`
- `deposit_amount NUMERIC`
- `cached_prediction_id` nullable FK to `predictions(prediction_id)`
- `payload JSONB NOT NULL`

`predictions`

- `prediction_id PK`
- `case_id INDEX` but no FK to sessions
- `created_at TEXT` from `timestamp`
- `overall_outcome`
- `overall_confidence NUMERIC`
- `range_lo NUMERIC`
- `range_hi NUMERIC`
- `pipeline_version`
- `model_version`
- `retrieval_quality`
- `rag_confidence NUMERIC`
- `pipeline_metadata JSONB`
- `citation_verification JSONB`
- `metadata JSONB`
- `payload JSONB NOT NULL`

`prediction_issues`

- `id PK`
- `prediction_id FK`
- `ordinal INT NOT NULL`
- `issue_type`
- `issue_description`
- `outcome`
- `raw_confidence NUMERIC`
- `calibrated_confidence NUMERIC`
- `predicted_amount NUMERIC`
- `amount_range_lo NUMERIC`
- `amount_range_hi NUMERIC`
- `reasoning TEXT`
- `key_factors JSONB`
- `supporting_cases JSONB`
- `counterfactuals JSONB`
- `evidence_strength`
- `data_completeness_impact TEXT`
- `payload JSONB NOT NULL`

`prediction_reasoning_steps`

- `id PK`
- `prediction_id FK`
- `ordinal INT NOT NULL`
- `step_number INT`
- `category`
- `title`
- `content TEXT`
- `confidence NUMERIC`
- `payload JSONB NOT NULL`

`prediction_citations`

- `id PK`
- `prediction_id FK`
- `reasoning_step_id NULL FK`
- `citation_source` enum/text: `reasoning`, `issue_supporting_case`, `verified`, `removed`
- `ordinal INT NOT NULL`
- `case_reference`
- `year INT`
- `region`
- `paragraph`
- `quote TEXT`
- `relevance TEXT`
- `similarity_score NUMERIC`
- `verified BOOLEAN`
- `payload JSONB NOT NULL`

`knowledge_graphs`

- `case_id PK` but no FK to sessions
- `graph_id UNIQUE`
- `created_at TEXT`
- `updated_at TEXT`
- `validation_errors JSONB`
- `validation_warnings JSONB`
- `validation_info JSONB`
- `is_consistent BOOLEAN`
- `data_quality_tier`
- `metadata JSONB`
- `payload JSONB NOT NULL`

`kg_nodes`

- `case_id FK to knowledge_graphs(case_id)`
- `node_id`
- `node_type`
- `confidence NUMERIC`
- `source`
- `source_text TEXT`
- `created_at TEXT`
- `event_date DATE` nullable
- `amount NUMERIC` nullable
- `node_data JSONB NOT NULL`
- `metadata JSONB`
- `PRIMARY KEY (case_id, node_id)`

`kg_edges`

- `case_id FK to knowledge_graphs(case_id)`
- `edge_id`
- `edge_type`
- `source_node_id`
- `target_node_id`
- `confidence NUMERIC`
- `source`
- `description TEXT`
- `metadata JSONB`
- `payload JSONB NOT NULL`
- `PRIMARY KEY (case_id, edge_id)`
- composite FKs:
  - `(case_id, source_node_id)` -> `kg_nodes(case_id, node_id)`
  - `(case_id, target_node_id)` -> `kg_nodes(case_id, node_id)`

`mediations`

- `mediation_id PK`
- `dispute_id UNIQUE FK`
- `status`
- `started_at TEXT`
- `updated_at TEXT`
- `settled_at TEXT`
- `settlement_amount NUMERIC`
- `escalated_at TEXT`
- `payload JSONB NOT NULL`

`mediation_messages`

- `id PK`
- `mediation_id FK`
- `message_id`
- `ordinal INT NOT NULL`
- `sender_role`
- `content TEXT`
- `message_type`
- `timestamp TEXT`
- `offer_id` nullable
- `metadata JSONB`
- `payload JSONB NOT NULL`

`structured_offers`

- `id PK`
- `mediation_id FK`
- `offer_id`
- `ordinal INT NOT NULL`
- `amount NUMERIC`
- `proposed_by_role`
- `status`
- `proposed_at TEXT`
- `responded_at TEXT`
- `counter_amount NUMERIC`
- `payload JSONB NOT NULL`

`evidence_metadata`

- `evidence_id PK`
- `case_id INDEX`
- `evidence_type`
- `file_url`
- `file_name`
- `file_type`
- `description TEXT`
- `payload JSONB NOT NULL`

Use `TEXT` for current timestamp fields because the domain models store ISO strings. A later model cleanup can migrate to `datetime`/`TIMESTAMPTZ`; do not mix string timestamps with DB-returned `datetime` objects during this migration.

### Indexes

| Table | Index | Reason |
|---|---|---|
| `intake_sessions` | `(case_id)` UNIQUE | `get_case_file()` lookup |
| `intake_sessions` | `(user_role)`, `(current_stage)` | admin/debug scans |
| `disputes` | `(invite_code)` UNIQUE | invite join flow |
| `disputes` | `(tenant_session_id)`, `(landlord_session_id)` | reverse session lookup |
| `disputes` | `(cached_prediction_id)` | shared prediction lookup |
| `predictions` | `(case_id)`, `(created_at)`, `(pipeline_version)` | list-for-case, ablation, version filtering |
| `prediction_issues` | `(prediction_id, ordinal)`, `(issue_type)` | reconstruction and filtering |
| `prediction_reasoning_steps` | `(prediction_id, ordinal)` | stable trace reconstruction |
| `prediction_citations` | `(prediction_id)`, `(reasoning_step_id)`, `(citation_source)` | trace + verification lookup |
| `knowledge_graphs` | `(graph_id)` UNIQUE | graph lookup |
| `kg_nodes` | `(case_id, node_type)` | type filter |
| `kg_nodes` | `(case_id, event_date) WHERE node_type='event'` | timeline |
| `kg_nodes` | `(case_id, amount) WHERE node_type='claimed_amount'` | amount scans |
| `kg_edges` | `(case_id, source_node_id, edge_type)`, `(case_id, target_node_id, edge_type)` | traversal |
| `mediations` | `(dispute_id)` UNIQUE | 1:1 with dispute |
| `mediation_messages` | `(mediation_id, ordinal)`, `(mediation_id, timestamp)`, `(offer_id)` | thread fetch + offer reverse |
| `structured_offers` | `(mediation_id, ordinal)`, `(mediation_id, status)` | pending offer scan |
| `evidence_metadata` | `(case_id)`, `(evidence_type)` | per-case fan-out |

## Transactions

Postgres gives transactions, but only if the code stops splitting a workflow across file writes, singleton state, and private service calls.

### Transaction Rules

1. Do not hold a DB transaction open during LLM calls, PDF extraction, file upload, or RAG retrieval.
2. Perform external work first, then persist the resulting state in one short transaction.
3. Use row locks or optimistic versioning for read-modify-write flows that can be hit concurrently.
4. Repositories do not commit or rollback.
5. Tests must assert both the DB state and the absence of mutated in-memory state.

### Required Transaction Boundaries

| Workflow | Transaction contents |
|---|---|
| Chat start + create dispute | insert intake session + insert dispute |
| Chat start + join dispute | insert intake session + update dispute session link/status |
| Intake message processing | upsert session + sync dispute status/property/deposit fields |
| Bulk intake | insert session + create/join/sync dispute |
| Prediction generation | after KG build + LLM prediction, persist KG + prediction + update `disputes.cached_prediction_id` atomically |
| Cached dispute prediction lookup/update | lock dispute row or use idempotent uniqueness so two requests do not generate conflicting shared predictions |
| Start mediation | update dispute status + upsert mediation + insert opening message |
| Submit/reject/counter offer | update mediation aggregate + projected offers/messages |
| Accept offer | update offer + mediation settled state + dispute settled state |
| Escalate mediation | update mediation + dispute |
| Evidence upload metadata | upload/extract first; insert metadata in DB; if DB insert fails, attempt file cleanup and log orphan |
| Evidence delete | delete/mark metadata + delete file/object with compensation if object deletion fails |
| Dispute status fix endpoint | route must call a service/repo method, not mutate `_disputes` or `_save_dispute` directly |

### Prediction Generation Detail

Do not wrap retrieval and LLM calls in a transaction. The shape should be:

1. Load case/dispute data.
2. Build/merge `CaseFile`.
3. Build KG in memory.
4. Call prediction engine.
5. Open transaction.
6. Lock dispute row when there is a `dispute_id`.
7. Re-check `cached_prediction_id`.
8. Insert KG rows, prediction rows, and cache pointer.
9. Commit.

## Backfill

### Scripts

```bash
python scripts/migrations/audit_json_stores.py --data-dir ./data
python scripts/migrations/backfill_json_to_postgres.py --data-dir ./data --dry-run
python scripts/migrations/backfill_json_to_postgres.py --data-dir ./data --commit
python scripts/migrations/backfill_json_to_postgres.py --data-dir ./data --verify
python scripts/migrations/backfill_json_to_postgres.py --data-dir ./data --archive-json
```

### Correct Order

1. Audit all JSON stores and produce `data/_migration_audit_report.json`.
2. Create schema with Alembic.
3. Backfill into an empty Postgres DB without renaming source dirs.
4. Verify row counts, child counts, referential integrity, and round-trip identity.
5. Run API smoke tests against Postgres.
6. Archive JSON dirs as the final explicit step.

### FK-Aware Load Order

1. `intake_sessions`
2. `predictions` with children
3. `disputes` with `cached_prediction_id` populated where possible
4. `knowledge_graphs`, then `kg_nodes`, then `kg_edges`
5. `mediations`, then `structured_offers`, then `mediation_messages`
6. `evidence_metadata`

`predictions` loads before `disputes.cached_prediction_id` to avoid nullable second-pass work where possible. If there are orphan mapping files, the audit must report them and the backfill should leave `cached_prediction_id` null for those disputes.

### Audit Checks

- JSON validates with current Pydantic models.
- Duplicate primary keys.
- Duplicate invite codes.
- Dispute session refs that do not exist.
- Dispute prediction mappings with missing disputes or predictions.
- KG edges with missing source/target nodes.
- Prediction/KG synthetic `merged-...` case IDs.
- Enum values not accepted by current models.
- Evidence metadata directory absent or empty.
- Data counts by directory.

## Testing

### Dependency Additions

Add to `requirements.txt`:

- `sqlalchemy[asyncio]>=2.0`
- `asyncpg`
- `alembic`
- `pytest-postgresql`
- `psycopg[binary]`
- `httpx`
- `asgi-lifespan`

### DB Fixture Strategy

Use `pytest-postgresql` deliberately:

1. Create/migrate a template test DB once per test session.
2. Clone from the template per test or test module.
3. Build asyncpg URLs explicitly.
4. Use SQLAlchemy `NullPool` in tests.
5. Dispose engines after each test.
6. Override FastAPI DB/UoW dependencies for API tests.

The fixture must run Alembic before tests. A fixture that just opens an `AsyncSession` against an empty DB is not sufficient.

### Required Tests

| Test | Asserts |
|---|---|
| Data audit | reports current counts and invalid/orphan records without mutating data |
| Alembic upgrade/downgrade | `upgrade head` and `downgrade base` both work on a clean DB |
| Repository round-trip | each existing JSON entity loads into rows and reconstructs to the same normalized Pydantic dump |
| Raw API contract | key endpoint responses match current JSON-backed behavior |
| Concurrent dispute updates | two simultaneous status/session updates do not lose state |
| Concurrent prediction requests | duplicate shared predictions are not created for one dispute |
| Mid-transaction crash | every multi-write workflow rolls back fully when the second write fails |
| Evidence compensation | failed metadata insert after file upload attempts cleanup and records orphan failure |
| No production JSON writes | service tests fail if migrated workflows touch `data/sessions`, `data/disputes`, `data/predictions`, `data/dispute_predictions`, `data/knowledge_graphs`, `data/mediations`, or `data/evidence_metadata` |

## Implementation Phasing

Single feature branch, single PR, but ordered so schema errors surface before service rewrites.

| # | Title | Lands |
|---|---|---|
| 0 | audit: inventory JSON stores and model drift | `scripts/migrations/audit_json_stores.py`, audit report, no service changes |
| 1 | infra: deps, config, engine, Alembic shell | `requirements.txt`, `APIConfig.database_url`, `db/engine.py`, `db/base.py`, `alembic.ini`, `apps/api/src/alembic/env.py` |
| 2 | schema: initial migration | 13 tables, enums, indexes, composite KG keys, reserved-name-safe SQLA mappings |
| 3 | repos: ORM models and repositories | repo CRUD + Pydantic mapping tests, no service cutover |
| 4 | tooling: backfill and round-trip verification | backfill dry-run/commit/verify, no archive yet |
| 5 | runtime: Unit of Work and app wiring | lifespan captures settings, UoW factory, test DB dependency overrides |
| 6 | services: intake + disputes | remove session/dispute persistence maps from production paths, refactor chat create/join workflows |
| 7 | services: predictions + KG + cache | replace `JSONGraphStore` production path, persist prediction/KG/cache atomically |
| 8 | services: evidence metadata | DB metadata repo, upload/delete compensation logic |
| 9 | services: mediation | remove mediation persistence map, projected messages/offers, transaction tests |
| 10 | verification: concurrency, crash, API contracts | full pytest + DB integration + smoke tests |
| 11 | cutover: archive JSON and docs | `--archive-json`, rollback runbook, README/dev docs |

## Infra

### Docker Compose

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: proposer
      POSTGRES_PASSWORD: proposer-dev
      POSTGRES_DB: proposer
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - proposer_pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U proposer -d proposer"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  proposer_pg_data:
```

### Makefile

Avoid relying on host Postgres client tools when Docker is the expected path.

```make
.PHONY: db-up db-down db-reset migrate test test-db test-api

db-up:
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U proposer -d proposer >/dev/null 2>&1; do sleep 0.5; done

db-down:
	docker compose down

db-reset:
	docker compose down -v
	$(MAKE) db-up
	$(MAKE) migrate

migrate:
	alembic upgrade head

test-db: db-up migrate
	pytest apps/api/tests tests/integration

test-api:
	pytest apps/api/tests

test: test-api test-db
```

### CI

CI needs:

- Postgres service container.
- `DATABASE_URL=postgresql+asyncpg://...`
- `alembic upgrade head`.
- pytest with DB integration enabled.
- Optional Alembic drift check after models land.

## Rollback

Rollback order matters. Do not `git revert` before dumping new Postgres-only data, because the dump script may disappear.

1. Stop writes.
2. Run `python scripts/migrations/dump_postgres_to_json.py --out data/_rollback_dump`.
3. Verify dumped JSON validates with Pydantic.
4. Rename archived source dirs back only if needed.
5. Revert the merge commit.
6. Start the JSON-backed app.
7. Keep Postgres snapshot until manual verification is complete.

## Risks

| Risk | Mitigation |
|---|---|
| Schema misses fields in wide Pydantic aggregates | Canonical `payload JSONB` plus round-trip tests before service cutover |
| KG node ID collisions | Composite `(case_id, node_id)` PK and composite edge FKs |
| Lost updates despite Postgres | Row locks, optimistic versions, or atomic SQL updates for read-modify-write flows |
| Singleton caches diverge from DB | Remove persistence-bearing maps from production paths |
| Merged case IDs break FKs | Do not FK prediction/KG `case_id` to sessions |
| Evidence file/DB mismatch | Compensation logic and orphan report |
| Test DB missing schema | Alembic-migrated template DB fixture |
| Rollback loses Postgres-only writes | Dump Postgres before reverting code |
| Thesis runway pressure | Stop after phase 4 if schema/backfill is not clean; do not enter service cutover with unresolved round-trip failures |

## Definition of Done

- [ ] Audit script reports current data counts and invalid/orphan records.
- [ ] All 7 user-facing stores write metadata/state to Postgres in production paths.
- [ ] JSON source dirs are archived only after verification.
- [ ] Backfill is idempotent and supports dry-run, commit, verify, and archive modes.
- [ ] Round-trip tests pass for every existing session, dispute, prediction, KG, mediation, and evidence metadata file.
- [ ] Existing API endpoints preserve response contracts.
- [ ] No migrated production code path writes to JSON state dirs.
- [ ] Concurrent-write tests prove no lost dispute/mediation/prediction-cache updates.
- [ ] Mid-transaction crash tests prove no half-written state.
- [ ] Evidence upload/delete compensation is tested.
- [ ] Alembic upgrade/downgrade works on clean DB.
- [ ] Docker Compose, Makefile, and CI run the migrated tests.
- [ ] README and dev setup docs explain Postgres workflow and rollback.

## Out of Scope

- ChromaDB/vector store.
- BM25 pickle/index files.
- `data/raw/bailii/` PDFs.
- Local/Supabase evidence blobs, except metadata rows and cleanup compensation.
- Read replicas, sharding, managed Postgres deployment.
- New analytics/admin dashboard queries.
- Full CaseFile normalization beyond JSONB payload/projection columns.
- KG recursive `find_path()` SQL/CTE implementation unless SHA-15 makes it live.
