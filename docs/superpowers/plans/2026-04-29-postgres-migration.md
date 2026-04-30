# SHA-102 Postgres Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate user-facing storage (sessions, disputes, predictions, KG, mediations, evidence metadata, dispute→prediction cache) from per-entity JSON files in `data/` to a Postgres database, behind a Unit-of-Work-managed SQLAlchemy 2.0 async repository layer, without breaking existing API contracts.

**Architecture:** Pydantic domain models stay canonical. SQLAlchemy ORM rows store one `payload JSONB` (full Pydantic dump for round-trip identity) plus projection columns and child tables for indexed queries. A `UnitOfWork` class wraps one `AsyncSession` and exposes every repository; services own transaction boundaries via `async with uow:` blocks. Process-local mutable persistence caches (`_sessions`, `_disputes`, `_invite_code_index`, `_mediations`) are removed from production paths.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, asyncpg, Alembic, pytest-postgresql, Postgres 16, Docker Compose.

**Spec:** [docs/superpowers/specs/2026-04-29-postgres-migration-design.md](../specs/2026-04-29-postgres-migration-design.md)

**Linear:** [SHA-102](https://linear.app/sharifbuilders/issue/SHA-102)

**Branch:** `feature/sha-102-migrate-user-facing-storage-from-json-files-to-postgres`

**Revision status:** Amended after multi-agent review on 2026-04-29. The plan is executable only after the safety gates below are implemented and passing.

---

## Conventions

- All commands assume CWD = repo root: `/Users/msharif/Documents/Projects/proposer/legal-mediation-system`.
- Every code task is TDD: write the failing test, run it red, write the minimal code, run it green, commit. Each commit is one task. The conventional-commit prefix matches the spec's phase (`infra`, `feat`, `refactor`, `test`, `docs`).
- `make db-up` and `alembic upgrade head` are prereqs for any test that hits the DB. Local dev DB URL: `postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer`.
- Test DB is provided by `pytest-postgresql` via the `db_session` fixture defined in Phase 3, Task 3.0. The fixture must create isolated databases from `postgresql_proc`; do not drop or recreate a DB that an active `postgresql` fixture is connected to.
- Production must never fall back to the local dev database URL. `APP_ENV=production` requires an explicit secret-managed `DATABASE_URL`, a non-localhost host, no dev password, and SSL/TLS-capable connection settings.
- Migration artifacts that may contain PII (`data/_migration_audit_report.json`, backfill reports, golden API responses, JSON snapshots) must either be redacted/synthetic before commit or kept out of git.

## Safety Gates Added By Review

These gates must be completed before service cutover begins:

- Enum alignment: DB enum values are generated from, or tested against, the canonical Python enums in `packages/llm_orchestrator/models` and `packages/kg_builder/models`.
- Import smoke test: every migration script imports its Pydantic models from the real package paths.
- Data integrity: validation errors, FK orphans, enum drift, duplicate IDs, and unhandled KG/evidence shapes fail the migration unless listed in an explicit quarantine file with a remediation note.
- Projection parity: every JSONB payload field projected into SQL columns is checked against the stored projection after repository save and after backfill.
- Lost-update prevention: hot read-modify-write aggregates use optimistic `version` columns, or a row lock when the transaction is short enough to avoid holding it across LLM/blob work.
- KG polymorphism: KG serialization/deserialization preserves node subclass fields such as party role, property address, event dates, and claimed amounts.
- Evidence metadata: audit, backfill, verify, and rollback handle the current nested shape `data/evidence_metadata/<case_id>/<evidence_id>.json`.
- API contract: existing case-id-only prediction generation, two-party merged prediction caching, and legal disclaimer/citation behavior remain unchanged.
- Cutover runbook: write freeze, JSON snapshot, DB snapshot/PITR note, staging rehearsal, verification, rollback drill, and post-cutover reconciliation are explicit stop/go gates.

## Foundation Hardening Addendum - 2026-04-29

The Phase 1-4 implementation was hardened before starting Phase 5-9 runtime cutover work. The foundation now includes:

- Migration CLIs run from a clean shell with direct script execution: `backfill_json_to_postgres.py`, `audit_json_stores.py`, and `dump_postgres_to_json.py`.
- Backfill is fail-closed: it refuses invalid JSON, FK-orphaned dispute prediction mappings, duplicate source IDs, non-empty target DBs unless `--force-overwrite` is explicit, and writes reports only after commit succeeds.
- Verify is stronger than payload round-trip: it detects extra DB rows, missing rows, dispute prediction cache drift, prediction cache key drift, and normalized prediction child-table projection drift.
- Rollback dump writes JSON-store-compatible filenames (`session_*`, `dispute_*`, `prediction_*`, `mediation_<dispute_id>`, `kg_*`) and refuses unsafe path components or non-empty output dirs unless forced.
- Prediction, KG, mediation, evidence, and dispute-cache projections have schema constraints, FK checks, ordinal preservation, and targeted repository tests.
- App bootstrap now has a request-scoped `UnitOfWork`, DB-aware `/readyz`, production DB/debug config guards, and a deterministic pytest-postgresql fixture.
- Frontend prediction display accepts backend `tenant_win`/`landlord_win` outcome aliases everywhere touched by the prediction UI.

Current verification baseline after hardening:

```bash
make test-api
make test-db
python3 -m compileall apps/api/src scripts/migrations packages/llm_orchestrator packages/kg_builder -q
npm --prefix apps/web run build
python3 scripts/migrations/backfill_json_to_postgres.py --help
python3 scripts/migrations/audit_json_stores.py --help
python3 scripts/migrations/dump_postgres_to_json.py --help
git diff --check
```

---

## File Layout (locked in this plan)

```
apps/api/src/
  config.py                              ← MODIFY (DATABASE_URL, Field not field)
  main.py                                ← MODIFY (create_lifespan factory)
  dependencies.py                        ← MODIFY (get_db_session, get_uow)
  db/                                    ← NEW package
    __init__.py
    engine.py
    base.py
    uow.py
    models/
      __init__.py
      sessions.py
      disputes.py
      predictions.py
      kg.py
      mediations.py
      evidence.py
    repositories/
      __init__.py
      sessions_repo.py
      disputes_repo.py
      predictions_repo.py
      kg_repo.py
      mediations_repo.py
      evidence_repo.py
  alembic/                               ← NEW (Alembic env)
    env.py
    script.py.mako
    versions/
      0001_initial_schema.py
  services/
    intake_service.py                    ← MODIFY (remove _sessions; use UoW)
    dispute_service.py                   ← MODIFY (remove _disputes/_invite_code_index)
    prediction_service.py                ← MODIFY (drop JSONGraphStore; UoW workflow)
    mediation_service.py                 ← MODIFY (remove _mediations; UoW)
    storage_service.py                   ← MODIFY (DB metadata; compensation logic)

apps/api/tests/
  conftest.py                            ← MODIFY (db_session, uow_factory fixtures)
  db/                                    ← NEW
    test_engine.py
    test_uow.py
    repositories/
      test_sessions_repo.py
      test_disputes_repo.py
      test_predictions_repo.py
      test_kg_repo.py
      test_mediations_repo.py
      test_evidence_repo.py
  integration/                           ← NEW
    test_roundtrip.py
    test_concurrent_writes.py
    test_atomicity.py
    test_api_contract.py
    test_no_json_writes.py

scripts/migrations/                      ← NEW
  audit_json_stores.py
  backfill_json_to_postgres.py
  dump_postgres_to_json.py
  check_model_alignment.py
  print_db_target.py                     ← NEW safe cutover preflight, prints host/db/user without password
  quarantine.yml                         ← NEW optional allowlist for signed-off bad source records

alembic.ini                              ← NEW (root)
docker-compose.yml                       ← NEW (root, sibling of langfuse compose)
Makefile                                 ← NEW (root)
.github/workflows/ci.yml                 ← NEW
requirements.txt                         ← MODIFY (asyncpg, sqlalchemy, alembic, pytest-postgresql, psycopg[binary], httpx, asgi-lifespan)
README.md                                ← MODIFY (Postgres setup, rollback)
```

---

## Phase 0 — Audit

Goal: produce `data/_migration_audit_report.json` describing every JSON file's validity, FK integrity, enum drift, and merged-case-id orphans. No service changes; no schema changes.

### Task 0.1 — Audit script skeleton + counts

**Files:**
- Create: `scripts/migrations/__init__.py`
- Create: `scripts/migrations/audit_json_stores.py`
- Test: `scripts/migrations/tests/test_audit_json_stores.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/migrations/tests/test_audit_json_stores.py
import json
from pathlib import Path

from scripts.migrations.audit_json_stores import audit


def test_audit_counts_files_per_dir(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_a.json").write_text("{}")
    (tmp_path / "sessions" / "session_b.json").write_text("{}")
    (tmp_path / "disputes").mkdir()
    (tmp_path / "disputes" / "dispute_x.json").write_text("{}")

    report = audit(tmp_path)

    assert report["counts"]["sessions"] == 2
    assert report["counts"]["disputes"] == 1
    assert report["counts"].get("predictions", 0) == 0
```

- [ ] **Step 2: Run the test and verify it fails**

```
pytest scripts/migrations/tests/test_audit_json_stores.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `scripts.migrations.audit_json_stores`.

- [ ] **Step 3: Write the minimal implementation**

```python
# scripts/migrations/audit_json_stores.py
"""Audit JSON storage directories before migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIRS: tuple[str, ...] = (
    "sessions",
    "disputes",
    "predictions",
    "dispute_predictions",
    "knowledge_graphs",
    "mediations",
    "evidence_metadata",
)


def audit(data_dir: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for d in DIRS:
        sub = data_dir / d
        if not sub.exists() or not sub.is_dir():
            counts[d] = 0
        elif d == "evidence_metadata":
            counts[d] = len(list(sub.rglob("*.json")))
        else:
            counts[d] = len(list(sub.glob("*.json")))
    return {"counts": counts}


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    report = audit(args.data_dir)
    out = args.out or (args.data_dir / "_migration_audit_report.json")
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test and verify it passes**

```
pytest scripts/migrations/tests/test_audit_json_stores.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/__init__.py scripts/migrations/audit_json_stores.py scripts/migrations/tests/test_audit_json_stores.py
git commit -m "feat(audit): scaffold audit_json_stores with per-dir counts"
```

### Task 0.2 — Validate against Pydantic models

**Files:**
- Modify: `scripts/migrations/audit_json_stores.py`
- Modify: `scripts/migrations/tests/test_audit_json_stores.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to scripts/migrations/tests/test_audit_json_stores.py
def test_audit_reports_pydantic_validation_errors(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_bad.json").write_text(
        '{"session_id": "x"}'  # missing required fields
    )

    report = audit(tmp_path)

    assert any(
        e["dir"] == "sessions" and e["file"].endswith("session_bad.json")
        for e in report["validation_errors"]
    )
```

- [ ] **Step 2: Run the test and verify it fails**

```
pytest scripts/migrations/tests/test_audit_json_stores.py::test_audit_reports_pydantic_validation_errors -v
```

Expected: `KeyError: 'validation_errors'` or AssertionError.

- [ ] **Step 3: Implement validation**

```python
# scripts/migrations/audit_json_stores.py — replace audit()
from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult
from packages.kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
)

MODEL_FOR_DIR = {
    "sessions": ConversationState,
    "disputes": DisputeCase,
    "predictions": PredictionResult,
    "mediations": MediationSession,
}


def _validate_kg_payload(data: dict[str, Any]) -> None:
    kg = deserialize_knowledge_graph(data)
    serialized = serialize_knowledge_graph(kg)
    if len(serialized.get("nodes", [])) != len(data.get("nodes", [])):
        raise ValueError("KG node count changed during polymorphic round-trip")


def audit(data_dir: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    validation_errors: list[dict[str, Any]] = []

    for d in DIRS:
        sub = data_dir / d
        if not sub.exists() or not sub.is_dir():
            counts[d] = 0
            continue
        files = sorted(sub.rglob("*.json") if d == "evidence_metadata" else sub.glob("*.json"))
        counts[d] = len(files)

        model = MODEL_FOR_DIR.get(d)
        if model is None and d != "knowledge_graphs":
            continue
        for f in files:
            try:
                data = json.loads(f.read_text())
                if d == "knowledge_graphs":
                    _validate_kg_payload(data)
                else:
                    model.model_validate(data)
            except Exception as exc:
                validation_errors.append(
                    {"dir": d, "file": str(f), "error": repr(exc)[:500]}
                )
    return {"counts": counts, "validation_errors": validation_errors}
```

- [ ] **Step 4: Run the test and verify it passes**

```
pytest scripts/migrations/tests/test_audit_json_stores.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/audit_json_stores.py scripts/migrations/tests/test_audit_json_stores.py
git commit -m "feat(audit): validate JSON files against current Pydantic models"
```

### Task 0.3 — FK and orphan checks

**Files:**
- Modify: `scripts/migrations/audit_json_stores.py`
- Modify: `scripts/migrations/tests/test_audit_json_stores.py`

- [ ] **Step 1: Write the failing test**

```python
def test_audit_detects_dispute_session_ref_orphans(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "disputes").mkdir()
    (tmp_path / "disputes" / "dispute_x.json").write_text(json.dumps({
        "dispute_id": "DISP-X",
        "invite_code": "ABC123",
        "status": "waiting_for_landlord",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by_role": "tenant",
        "tenant_session_id": "missing-session",
        "landlord_session_id": None,
        "property_address": None,
        "property_postcode": None,
        "deposit_amount": None,
    }))

    report = audit(tmp_path)
    orphans = report["orphans"]

    assert any(
        o["kind"] == "dispute_tenant_session_missing"
        and o["dispute_id"] == "DISP-X"
        for o in orphans
    )


def test_audit_detects_dispute_prediction_mapping_orphans(tmp_path: Path) -> None:
    (tmp_path / "predictions").mkdir()
    (tmp_path / "dispute_predictions").mkdir()
    (tmp_path / "dispute_predictions" / "DISP-Y.json").write_text(json.dumps({
        "dispute_id": "DISP-Y", "prediction_id": "missing-pred",
    }))

    report = audit(tmp_path)
    assert any(
        o["kind"] == "dispute_prediction_missing" and o["prediction_id"] == "missing-pred"
        for o in report["orphans"]
    )


def test_audit_flags_kg_edges_with_missing_nodes(tmp_path: Path) -> None:
    (tmp_path / "knowledge_graphs").mkdir()
    (tmp_path / "knowledge_graphs" / "kg_case1.json").write_text(json.dumps({
        "graph_id": "g1", "case_id": "case1",
        "created_at": "2026-01-01T00:00:00",
        "nodes": [
            {"node_id": "n1", "node_type": "party", "_node_class": "PartyNode",
             "confidence": 1.0, "source": "user_input", "role": "tenant"}
        ],
        "edges": [
            {"edge_id": "e1", "edge_type": "party_owns",
             "source_node_id": "n1", "target_node_id": "MISSING",
             "confidence": 1.0, "source": "user_input", "description": "x"}
        ],
    }))

    report = audit(tmp_path)
    assert any(
        o["kind"] == "kg_edge_missing_target" and o["case_id"] == "case1"
        for o in report["orphans"]
    )


def test_audit_flags_synthetic_merged_case_ids(tmp_path: Path) -> None:
    (tmp_path / "predictions").mkdir()
    (tmp_path / "predictions" / "prediction_x.json").write_text(json.dumps({
        "case_id": "merged-AAA-BBB",
        "prediction_id": "p1",
        # ... minimum to validate-or-fail; we only check the case_id substring
    }))

    report = audit(tmp_path)
    assert any(
        n["case_id"] == "merged-AAA-BBB" for n in report["synthetic_case_ids"]
    )
```

- [ ] **Step 2: Run and verify failures**

```
pytest scripts/migrations/tests/test_audit_json_stores.py -v
```

Expected: 4 FAIL (`KeyError: 'orphans'`, `KeyError: 'synthetic_case_ids'`).

- [ ] **Step 3: Implement orphan and synthetic-id detection**

```python
# scripts/migrations/audit_json_stores.py — extend audit()
def audit(data_dir: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    validation_errors: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    synthetic_case_ids: list[dict[str, Any]] = []

    # collect ids per directory first
    session_ids: set[str] = set()
    prediction_ids: set[str] = set()
    raw_disputes: list[dict[str, Any]] = []

    def _read_json(p: Path) -> dict[str, Any] | None:
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def _json_files(dirname: str) -> list[Path]:
        sub = data_dir / dirname
        if not sub.is_dir():
            return []
        if dirname == "evidence_metadata":
            return sorted(sub.rglob("*.json"))
        return sorted(sub.glob("*.json"))

    for d in DIRS:
        counts[d] = len(_json_files(d))

    sessions_dir = data_dir / "sessions"
    if sessions_dir.is_dir():
        for f in sessions_dir.glob("*.json"):
            data = _read_json(f)
            if data and "session_id" in data:
                session_ids.add(data["session_id"])

    predictions_dir = data_dir / "predictions"
    if predictions_dir.is_dir():
        for f in predictions_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            if "prediction_id" in data:
                prediction_ids.add(data["prediction_id"])
            cid = data.get("case_id", "")
            if isinstance(cid, str) and cid.startswith("merged-"):
                synthetic_case_ids.append({"file": str(f), "case_id": cid})

    disputes_dir = data_dir / "disputes"
    if disputes_dir.is_dir():
        for f in disputes_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            raw_disputes.append({"file": str(f), "data": data})
            ts = data.get("tenant_session_id")
            ls = data.get("landlord_session_id")
            if ts and ts not in session_ids:
                orphans.append({
                    "kind": "dispute_tenant_session_missing",
                    "dispute_id": data.get("dispute_id"),
                    "tenant_session_id": ts,
                })
            if ls and ls not in session_ids:
                orphans.append({
                    "kind": "dispute_landlord_session_missing",
                    "dispute_id": data.get("dispute_id"),
                    "landlord_session_id": ls,
                })

    dp_dir = data_dir / "dispute_predictions"
    if dp_dir.is_dir():
        dispute_ids = {d["data"].get("dispute_id") for d in raw_disputes}
        for f in dp_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            did = data.get("dispute_id")
            pid = data.get("prediction_id")
            if did not in dispute_ids:
                orphans.append({"kind": "dispute_prediction_dispute_missing",
                                "file": str(f), "dispute_id": did})
            if pid not in prediction_ids:
                orphans.append({"kind": "dispute_prediction_missing",
                                "file": str(f), "prediction_id": pid})

    kg_dir = data_dir / "knowledge_graphs"
    if kg_dir.is_dir():
        for f in kg_dir.glob("*.json"):
            data = _read_json(f)
            if not data:
                continue
            node_ids = {n.get("node_id") for n in data.get("nodes", [])}
            for e in data.get("edges", []):
                if e.get("source_node_id") not in node_ids:
                    orphans.append({
                        "kind": "kg_edge_missing_source",
                        "case_id": data.get("case_id"), "edge_id": e.get("edge_id"),
                        "missing": e.get("source_node_id"),
                    })
                if e.get("target_node_id") not in node_ids:
                    orphans.append({
                        "kind": "kg_edge_missing_target",
                        "case_id": data.get("case_id"), "edge_id": e.get("edge_id"),
                        "missing": e.get("target_node_id"),
                    })

    # validation pass — same as before
    for d in DIRS:
        sub = data_dir / d
        if not sub.is_dir():
            continue
        model = MODEL_FOR_DIR.get(d)
        if model is None and d != "knowledge_graphs":
            continue
        for f in _json_files(d):
            data = _read_json(f)
            if data is None:
                validation_errors.append({"dir": d, "file": str(f), "error": "unreadable"})
                continue
            try:
                if d == "knowledge_graphs":
                    _validate_kg_payload(data)
                else:
                    model.model_validate(data)
            except Exception as exc:
                validation_errors.append({"dir": d, "file": str(f), "error": repr(exc)[:500]})

    return {
        "counts": counts,
        "validation_errors": validation_errors,
        "orphans": orphans,
        "synthetic_case_ids": synthetic_case_ids,
    }
```

- [ ] **Step 4: Run and verify all PASS**

```
pytest scripts/migrations/tests/test_audit_json_stores.py -v
```

Expected: all 4 new tests + previous 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/audit_json_stores.py scripts/migrations/tests/test_audit_json_stores.py
git commit -m "feat(audit): detect FK orphans and synthetic merged case IDs"
```

### Task 0.4 — Run audit on real data

- [ ] **Step 1: Execute the audit**

```bash
python -m scripts.migrations.audit_json_stores --data-dir ./data --out data/_migration_audit_report.json
cat data/_migration_audit_report.json
```

- [ ] **Step 2: Eyeball the report**

Confirm counts match the spec audit table (240 sessions, 42 predictions, 16 KGs, 22 disputes, 4 mediations, 7 dispute_predictions). Note any orphans, validation errors, or merged case IDs in the commit message.

- [ ] **Step 3: Commit the report only if redacted**

```bash
git add data/_migration_audit_report.json
git commit -m "chore(audit): capture pre-migration JSON store audit report"
```

The report must not contain raw addresses, names, messages, evidence descriptions, or other PII. If it does, commit only a redacted/synthetic summary and keep the full report local.

If the report shows validation errors, FK orphans, enum drift, duplicate IDs, synthetic-case surprises, or unhandled evidence/KG shapes, stop and either fix the source data or add an explicit entry to `scripts/migrations/quarantine.yml` with the file path, reason, impact, and planned remediation. Backfill fails closed by default; no skip-with-warning cutover.

---

## Phase 1 — Infra: deps, config, engine, Alembic shell

### Task 1.1 — Add database dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add deps**

Append to `requirements.txt`:

```
sqlalchemy[asyncio]>=2.0,<3.0
asyncpg>=0.29
alembic>=1.13
psycopg[binary]>=3.1
pytest-postgresql>=6.0
asgi-lifespan>=2.1
httpx>=0.27
```

- [ ] **Step 2: Install**

```bash
pip install -r requirements.txt
```

Expected: clean install, no resolver conflicts.

- [ ] **Step 3: Smoke import**

```bash
python -c "import sqlalchemy, asyncpg, alembic, psycopg, pytest_postgresql, asgi_lifespan, httpx; print('ok')"
```

Expected output: `ok`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "infra(deps): add sqlalchemy/asyncpg/alembic and test deps"
```

### Task 1.2 — Add `DATABASE_URL` to APIConfig

**Files:**
- Modify: `apps/api/src/config.py`
- Test: `apps/api/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_config.py — add test
import os

import pytest

from apps.api.src.config import APIConfig


def test_database_url_defaults_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.database_url == (
        "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer"
    )


def test_database_url_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:1/d")
    cfg = APIConfig.from_env()
    assert cfg.database_url == "postgresql+asyncpg://u:p@h:1/d"


def test_production_requires_explicit_non_dev_database_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        APIConfig.from_env()


def test_production_rejects_local_dev_database_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
    )

    with pytest.raises(ValueError, match="dev database"):
        APIConfig.from_env()


def test_production_requires_tls_database_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://u:p@db.example.com:5432/proposer",
    )

    with pytest.raises(ValueError, match="sslmode"):
        APIConfig.from_env()
```

- [ ] **Step 2: Run and verify failure**

```
pytest apps/api/tests/test_config.py -v
```

Expected: `AttributeError: 'APIConfig' object has no attribute 'database_url'`.

- [ ] **Step 3: Add the field (Pydantic `Field`, NOT dataclass `field`)**

```python
# apps/api/src/config.py — inside APIConfig
from pydantic import BaseModel, Field, model_validator
import os
from urllib.parse import parse_qs, urlparse

class APIConfig(BaseModel):
    # ... existing fields ...
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
        )
    )

    @model_validator(mode="after")
    def validate_database_url_for_environment(self) -> "APIConfig":
        if self.app_env != "production":
            return self
        raw = os.getenv("DATABASE_URL")
        if not raw:
            raise ValueError("DATABASE_URL is required in production")
        host = (urlparse(raw).hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or "proposer-dev" in raw:
            raise ValueError("production must not use the local dev database")
        qs = parse_qs(urlparse(raw).query)
        sslmode = (qs.get("sslmode") or [""])[0]
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("production DATABASE_URL must set sslmode=require or stronger")
        return self
```

- [ ] **Step 4: Run and verify pass**

```
pytest apps/api/tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/config.py apps/api/tests/test_config.py
git commit -m "infra(config): add DATABASE_URL with production safety gate"
```

### Task 1.3 — `db.base` and `db.engine`

**Files:**
- Create: `apps/api/src/db/__init__.py`
- Create: `apps/api/src/db/base.py`
- Create: `apps/api/src/db/engine.py`
- Test: `apps/api/tests/db/test_engine.py`
- Create: `apps/api/tests/db/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/db/test_engine.py
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.src.db.engine import create_engine_from_url, make_sessionmaker


@pytest.mark.asyncio
async def test_create_engine_returns_async_engine() -> None:
    engine = create_engine_from_url("postgresql+asyncpg://x:y@localhost:5432/z")
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_make_sessionmaker_returns_async_sessionmaker() -> None:
    engine = create_engine_from_url("postgresql+asyncpg://x:y@localhost:5432/z")
    sm = make_sessionmaker(engine)
    assert isinstance(sm, async_sessionmaker)
    # session() returns an AsyncSession even if we don't connect
    session = sm()
    assert isinstance(session, AsyncSession)
    await session.close()
    await engine.dispose()
```

- [ ] **Step 2: Run and verify failure**

```
pytest apps/api/tests/db/test_engine.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `base.py`**

```python
# apps/api/src/db/base.py
"""SQLAlchemy declarative base for the proposer DB."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide DeclarativeBase. All ORM models inherit from this."""
```

- [ ] **Step 4: Create `engine.py`**

```python
# apps/api/src/db/engine.py
"""AsyncEngine + sessionmaker factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine_from_url(
    url: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 5,
    pool_timeout: int = 10,
    pool_pre_ping: bool = True,
) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=pool_pre_ping,
        future=True,
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
```

- [ ] **Step 5: Create `__init__.py`s**

```python
# apps/api/src/db/__init__.py
from apps.api.src.db.base import Base
from apps.api.src.db.engine import create_engine_from_url, make_sessionmaker

__all__ = ["Base", "create_engine_from_url", "make_sessionmaker"]
```

```python
# apps/api/tests/db/__init__.py
```

- [ ] **Step 6: Run and verify pass**

```
pytest apps/api/tests/db/test_engine.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/db/ apps/api/tests/db/
git commit -m "infra(db): add AsyncEngine factory and DeclarativeBase"
```

### Task 1.4 — Alembic shell

**Files:**
- Create: `alembic.ini`
- Create: `apps/api/src/alembic/env.py`
- Create: `apps/api/src/alembic/script.py.mako`
- Create: `apps/api/src/alembic/versions/.gitkeep`

- [ ] **Step 1: Initialize Alembic structure manually**

Create `alembic.ini` at repo root:

```ini
[alembic]
script_location = apps/api/src/alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
qualname =
[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = INFO
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 2: Create the async env**

```python
# apps/api/src/alembic/env.py
"""Async Alembic env that imports project models for autogenerate."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from apps.api.src.db.base import Base
from apps.api.src.db.engine import create_engine_from_url

# Import models so Base.metadata is populated. Models added in Phase 2.
import apps.api.src.db.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

URL = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine_from_url(URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: Add the script template**

```python
# apps/api/src/alembic/script.py.mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create empty package and version dir**

```bash
touch apps/api/src/alembic/versions/.gitkeep
echo "" > apps/api/src/alembic/__init__.py
```

Then create `apps/api/src/db/models/__init__.py` (empty for now, populated in Phase 2):

```python
# apps/api/src/db/models/__init__.py
```

- [ ] **Step 5: Verify alembic CLI sees the env**

```bash
alembic -c alembic.ini current
```

Expected: prints nothing (no migrations yet); does NOT crash. If it errors with "DB unavailable," that's fine — we just need the env to import successfully.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini apps/api/src/alembic/ apps/api/src/db/models/
git commit -m "infra(alembic): add async Alembic env wired to project Base.metadata"
```

### Task 1.5 — Docker Compose Postgres

**Files:**
- Create: `docker-compose.yml` (root, sibling of `docker-compose.langfuse.yml`)

- [ ] **Step 1: Write the compose file**

```yaml
# docker-compose.yml
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

- [ ] **Step 2: Bring up Postgres**

```bash
docker compose up -d postgres
```

- [ ] **Step 3: Verify ready**

```bash
docker compose exec -T postgres pg_isready -U proposer -d proposer
```

Expected: `accepting connections`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "infra(docker): add Postgres compose service"
```

### Task 1.6 — Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Write the Makefile**

```make
# Makefile
.PHONY: db-up db-down db-reset migrate test test-api test-db eval

db-up:
	docker compose up -d postgres
	@until docker compose exec -T postgres pg_isready -U proposer -d proposer >/dev/null 2>&1; do sleep 0.5; done

db-down:
	docker compose down

db-reset:
	@test "$${APP_ENV:-local}" = "local" || (echo "db-reset is local-only; refusing for APP_ENV=$${APP_ENV}" && exit 1)
	docker compose down -v
	$(MAKE) db-up
	$(MAKE) migrate

migrate:
	alembic -c alembic.ini upgrade head

test-api:
	pytest apps/api/tests

test-db: db-up migrate
	pytest apps/api/tests/db apps/api/tests/integration

test: test-api test-db

eval: db-up migrate
	python scripts/eval/run_eval.py
```

- [ ] **Step 2: Verify**

```bash
make db-up
make migrate
```

Expected: `make db-up` brings Postgres up; `make migrate` runs `alembic upgrade head` cleanly (no migrations yet → no-op).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "infra(make): add db-up/down/reset, migrate, test-api/db targets"
```

---

## Phase 2 — Schema (initial migration)

Goal: define all 13 SQLAlchemy ORM models and produce the first Alembic migration. No services touched.

For each entity, the model includes:
- Primary key + projection columns from spec §"Aggregate Columns"
- `payload: Mapped[dict[str, Any]]` JSONB for round-trip identity
- The reserved-name-safe alias when a Pydantic field is named `metadata`: `metadata_ = mapped_column("metadata", JSONB)`
- Composite PKs and composite FKs where the spec requires (KG nodes, KG edges)

### Task 2.1 — Postgres enums module

**Files:**
- Create: `apps/api/src/db/models/_enums.py`

- [ ] **Step 1: Define every enum**

```python
# apps/api/src/db/models/_enums.py
"""All Postgres enums used by ORM models. One file so migrations stay clean."""

from sqlalchemy.dialects.postgresql import ENUM

# Names match the Python enum string values from packages/llm_orchestrator/models
# and packages/kg_builder/models. Keep these in sync with the Pydantic enums.

user_role_enum = ENUM("tenant", "landlord", name="user_role", create_type=False)
intake_stage_enum = ENUM(
    "greeting", "role_identification", "basic_details", "tenancy_details",
    "deposit_details", "issue_identification", "evidence_collection",
    "claim_amounts", "narrative", "confirmation", "complete",
    name="intake_stage", create_type=False,
)
dispute_status_enum = ENUM(
    "waiting_for_tenant", "waiting_for_landlord",
    "tenant_in_progress", "landlord_in_progress", "both_in_progress",
    "tenant_complete", "landlord_complete", "both_complete",
    "ready_for_mediation", "in_mediation", "settled", "closed",
    name="dispute_status", create_type=False,
)
party_role_enum = ENUM("tenant", "landlord", name="party_role", create_type=False)
outcome_type_enum = ENUM(
    "tenant_win", "landlord_win", "split", "uncertain",
    name="outcome_type", create_type=False,
)
issue_outcome_enum = ENUM(
    "tenant_wins", "landlord_wins", "split", "uncertain",
    name="issue_outcome", create_type=False,
)
issue_type_enum = ENUM(
    "cleaning", "damage", "rent_arrears", "deposit_protection", "inventory",
    "garden", "redecoration", "keys", "fair_wear_and_tear", "missing_items",
    "utilities", "other",
    name="issue_type", create_type=False,
)
evidence_strength_enum = ENUM(
    "strong", "moderate", "weak", "insufficient",
    name="evidence_strength", create_type=False,
)
evidence_type_enum = ENUM(
    "inventory_checkin", "inventory_checkout", "photos_before", "photos_after",
    "receipts", "invoices", "correspondence", "tenancy_agreement",
    "deposit_certificate", "witness_statement", "other",
    name="evidence_type", create_type=False,
)
mediation_status_enum = ENUM(
    "expectation_adjustment", "active_negotiation", "settled", "escalated",
    name="mediation_status", create_type=False,
)
message_type_enum = ENUM(
    "text", "offer", "system", "ai_mediator",
    name="message_type", create_type=False,
)
offer_status_enum = ENUM(
    "pending", "accepted", "rejected", "countered", "expired",
    name="offer_status", create_type=False,
)
node_type_enum = ENUM(
    "party", "property", "lease", "evidence", "event", "issue", "claimed_amount",
    name="node_type", create_type=False,
)
edge_type_enum = ENUM(
    "evidence_supports", "evidence_refutes", "evidence_relates_to",
    "event_before", "event_after", "event_during",
    "party_owns", "party_rents", "party_manages", "party_claims",
    "claim_relates_to", "issue_involves", "issue_caused_by",
    "lease_for", "deposit_protected_by",
    name="edge_type", create_type=False,
)
citation_source_enum = ENUM(
    "reasoning", "issue_supporting_case", "verified", "removed",
    name="citation_source", create_type=False,
)

ALL_ENUMS = (
    user_role_enum, intake_stage_enum, dispute_status_enum, party_role_enum,
    outcome_type_enum, issue_outcome_enum, issue_type_enum,
    evidence_strength_enum, evidence_type_enum,
    mediation_status_enum, message_type_enum, offer_status_enum,
    node_type_enum, edge_type_enum, citation_source_enum,
)
```

> Note: every enum uses `create_type=False`. The Alembic migration explicitly creates the types once (Task 2.8) so models attaching to columns won't try to create-then-fail.

- [ ] **Step 2: Smoke import**

```bash
python -c "from apps.api.src.db.models._enums import ALL_ENUMS; print(len(ALL_ENUMS))"
```

Expected: `15`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/db/models/_enums.py
git commit -m "feat(db): define Postgres enums for all domain types"
```

### Task 2.1a — Enum alignment safety test

**Files:**
- Create: `apps/api/tests/db/test_enum_alignment.py`

- [ ] **Step 1: Add a failing alignment test**

The test imports `ALL_ENUMS` from `apps.api.src.db.models._enums` and compares each enum's value set with the canonical Python enums:

- `PartyRole`
- `IntakeStage`
- `DisputeStatus`
- `OutcomeType`
- `IssueOutcome`
- `DisputeIssue` / `IssueType`
- `EvidenceStrength`
- `EvidenceType`
- `MediationStatus`
- `MessageType`
- `OfferStatus`
- `NodeType`
- `EdgeType`

`sender_role` for mediation messages is intentionally `String`, not `party_role_enum`, because current messages may use `ai_mediator`. The test must also compare the Alembic migration's `ENUMS` dict against `apps.api.src.db.models._enums.ALL_ENUMS`, so the ORM enum file and hand-written migration cannot drift independently.

- [ ] **Step 2: Run**

```
pytest apps/api/tests/db/test_enum_alignment.py -v
```

Expected: PASS before writing the migration. Any enum mismatch is a blocker.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/db/test_enum_alignment.py
git commit -m "test(db): assert postgres enums match canonical pydantic enums"
```

### Task 2.2 — `intake_sessions` model

**Files:**
- Create: `apps/api/src/db/models/sessions.py`
- Modify: `apps/api/src/db/models/__init__.py`

- [ ] **Step 1: Write the model**

```python
# apps/api/src/db/models/sessions.py
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import intake_stage_enum, user_role_enum


class IntakeSessionRow(Base):
    __tablename__ = "intake_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    user_role: Mapped[str | None] = mapped_column(user_role_enum, nullable=True)
    current_stage: Mapped[str] = mapped_column(intake_stage_enum, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    intake_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completeness_score: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    role_explicitly_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Re-export**

```python
# apps/api/src/db/models/__init__.py
from apps.api.src.db.models.sessions import IntakeSessionRow

__all__ = ["IntakeSessionRow"]
```

- [ ] **Step 3: Smoke import**

```bash
python -c "from apps.api.src.db.models import IntakeSessionRow; print(IntakeSessionRow.__tablename__)"
```

Expected: `intake_sessions`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/db/models/sessions.py apps/api/src/db/models/__init__.py
git commit -m "feat(db): add IntakeSessionRow model"
```

### Task 2.3 — `disputes` model

**Files:**
- Create: `apps/api/src/db/models/disputes.py`
- Modify: `apps/api/src/db/models/__init__.py`

- [ ] **Step 1: Write the model**

```python
# apps/api/src/db/models/disputes.py
from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import dispute_status_enum, party_role_enum


class DisputeRow(Base):
    __tablename__ = "disputes"

    dispute_id: Mapped[str] = mapped_column(String, primary_key=True)
    invite_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(dispute_status_enum, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_role: Mapped[str | None] = mapped_column(party_role_enum, nullable=True)
    tenant_session_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True,
    )
    landlord_session_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True,
    )
    property_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    property_postcode: Mapped[str | None] = mapped_column(String, nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    cached_prediction_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="SET NULL"), nullable=True,
    )
    prediction_cache_key: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Re-export**

Append to `apps/api/src/db/models/__init__.py`:

```python
from apps.api.src.db.models.disputes import DisputeRow

__all__ += ["DisputeRow"]
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/db/models/disputes.py apps/api/src/db/models/__init__.py
git commit -m "feat(db): add DisputeRow model with cached_prediction_id FK"
```

### Task 2.4 — `predictions` + children models

**Files:**
- Create: `apps/api/src/db/models/predictions.py`
- Modify: `apps/api/src/db/models/__init__.py`

- [ ] **Step 1: Write the four classes in one file**

```python
# apps/api/src/db/models/predictions.py
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import (
    citation_source_enum, evidence_strength_enum, issue_outcome_enum,
    issue_type_enum, outcome_type_enum,
)


class PredictionRow(Base):
    __tablename__ = "predictions"

    prediction_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    overall_outcome: Mapped[str] = mapped_column(outcome_type_enum, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    range_lo: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    range_hi: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    retrieval_quality: Mapped[str | None] = mapped_column(String, nullable=True)
    rag_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    pipeline_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    citation_verification: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PredictionIssueRow(Base):
    __tablename__ = "prediction_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_type: Mapped[str] = mapped_column(issue_type_enum, nullable=False)
    issue_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(issue_outcome_enum, nullable=False)
    raw_confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    calibrated_confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    predicted_amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    amount_range_lo: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    amount_range_hi: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_factors: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    supporting_cases: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    counterfactuals: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    evidence_strength: Mapped[str | None] = mapped_column(evidence_strength_enum, nullable=True)
    data_completeness_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PredictionReasoningStepRow(Base):
    __tablename__ = "prediction_reasoning_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    step_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PredictionCitationRow(Base):
    __tablename__ = "prediction_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(
        String, ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False,
    )
    reasoning_step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("prediction_reasoning_steps.id", ondelete="CASCADE"), nullable=True,
    )
    citation_source: Mapped[str] = mapped_column(citation_source_enum, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    case_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    paragraph: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Re-export**

```python
# apps/api/src/db/models/__init__.py — append
from apps.api.src.db.models.predictions import (
    PredictionRow, PredictionIssueRow, PredictionReasoningStepRow, PredictionCitationRow,
)
__all__ += ["PredictionRow", "PredictionIssueRow", "PredictionReasoningStepRow", "PredictionCitationRow"]
```

- [ ] **Step 3: Smoke import**

```bash
python -c "from apps.api.src.db.models import PredictionRow, PredictionIssueRow, PredictionReasoningStepRow, PredictionCitationRow; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/db/models/predictions.py apps/api/src/db/models/__init__.py
git commit -m "feat(db): add PredictionRow + issues/reasoning/citations children"
```

### Task 2.5 — KG models with composite identity

**Files:**
- Create: `apps/api/src/db/models/kg.py`
- Modify: `apps/api/src/db/models/__init__.py`

- [ ] **Step 1: Write the model**

```python
# apps/api/src/db/models/kg.py
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Date, ForeignKeyConstraint, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import edge_type_enum, node_type_enum


class KnowledgeGraphRow(Base):
    __tablename__ = "knowledge_graphs"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    graph_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_errors: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    validation_warnings: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    validation_info: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    is_consistent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    data_quality_tier: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class KGNodeRow(Base):
    __tablename__ = "kg_nodes"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    node_type: Mapped[str] = mapped_column(node_type_enum, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    node_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["case_id"], ["knowledge_graphs.case_id"], ondelete="CASCADE"),
    )


class KGEdgeRow(Base):
    __tablename__ = "kg_edges"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    edge_id: Mapped[str] = mapped_column(String, primary_key=True)
    edge_type: Mapped[str] = mapped_column(edge_type_enum, nullable=False)
    source_node_id: Mapped[str] = mapped_column(String, nullable=False)
    target_node_id: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "source_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["case_id", "target_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
    )
```

- [ ] **Step 2: Re-export**

Append to `apps/api/src/db/models/__init__.py`:

```python
from apps.api.src.db.models.kg import KnowledgeGraphRow, KGNodeRow, KGEdgeRow
__all__ += ["KnowledgeGraphRow", "KGNodeRow", "KGEdgeRow"]
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/db/models/kg.py apps/api/src/db/models/__init__.py
git commit -m "feat(db): add KG models with composite (case_id,node_id) identity"
```

### Task 2.6 — Mediation models

**Files:**
- Create: `apps/api/src/db/models/mediations.py`
- Modify: `apps/api/src/db/models/__init__.py`

- [ ] **Step 1: Write the file**

```python
# apps/api/src/db/models/mediations.py
from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import (
    mediation_status_enum, message_type_enum, offer_status_enum, party_role_enum,
)


class MediationSessionRow(Base):
    __tablename__ = "mediations"

    mediation_id: Mapped[str] = mapped_column(String, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(
        String, ForeignKey("disputes.dispute_id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    status: Mapped[str] = mapped_column(mediation_status_enum, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    settled_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    settlement_amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    escalated_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class MediationMessageRow(Base):
    __tablename__ = "mediation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mediation_id: Mapped[str] = mapped_column(
        String, ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False,
    )
    message_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # May be "tenant", "landlord", or "ai_mediator"; keep as String, not party_role_enum.
    sender_role: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_type: Mapped[str] = mapped_column(message_type_enum, nullable=False)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False)
    offer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class StructuredOfferRow(Base):
    __tablename__ = "structured_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mediation_id: Mapped[str] = mapped_column(
        String, ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False,
    )
    offer_id: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    proposed_by_role: Mapped[str] = mapped_column(party_role_enum, nullable=False)
    status: Mapped[str] = mapped_column(offer_status_enum, nullable=False)
    proposed_at: Mapped[str] = mapped_column(Text, nullable=False)
    responded_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    counter_amount: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Re-export**

Append to `apps/api/src/db/models/__init__.py`:

```python
from apps.api.src.db.models.mediations import (
    MediationSessionRow, MediationMessageRow, StructuredOfferRow,
)
__all__ += ["MediationSessionRow", "MediationMessageRow", "StructuredOfferRow"]
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/db/models/mediations.py apps/api/src/db/models/__init__.py
git commit -m "feat(db): add mediation, mediation_messages, structured_offers models"
```

### Task 2.7 — Evidence metadata model

**Files:**
- Create: `apps/api/src/db/models/evidence.py`
- Modify: `apps/api/src/db/models/__init__.py`

- [ ] **Step 1: Write the file**

```python
# apps/api/src/db/models/evidence.py
from __future__ import annotations

from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.src.db.base import Base
from apps.api.src.db.models._enums import evidence_type_enum


class EvidenceMetadataRow(Base):
    __tablename__ = "evidence_metadata"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_type: Mapped[str] = mapped_column(evidence_type_enum, nullable=False)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Re-export**

Append to `apps/api/src/db/models/__init__.py`:

```python
from apps.api.src.db.models.evidence import EvidenceMetadataRow
__all__ += ["EvidenceMetadataRow"]
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/db/models/evidence.py apps/api/src/db/models/__init__.py
git commit -m "feat(db): add EvidenceMetadataRow model"
```

### Task 2.8 — Hand-write the initial Alembic migration

Autogenerate is fragile with our enum + composite-FK setup. Hand-write the migration so it's auditable.

**Files:**
- Create: `apps/api/src/alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Write the migration**

```python
# apps/api/src/alembic/versions/0001_initial_schema.py
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


ENUMS = {
    "user_role": ("tenant", "landlord"),
    "intake_stage": (
        "greeting", "role_identification", "basic_details", "tenancy_details",
        "deposit_details", "issue_identification", "evidence_collection",
        "claim_amounts", "narrative", "confirmation", "complete",
    ),
    "dispute_status": (
        "waiting_for_tenant", "waiting_for_landlord",
        "tenant_in_progress", "landlord_in_progress", "both_in_progress",
        "tenant_complete", "landlord_complete", "both_complete",
        "ready_for_mediation", "in_mediation", "settled", "closed",
    ),
    "party_role": ("tenant", "landlord"),
    "outcome_type": ("tenant_win", "landlord_win", "split", "uncertain"),
    "issue_outcome": ("tenant_wins", "landlord_wins", "split", "uncertain"),
    "issue_type": (
        "cleaning", "damage", "rent_arrears", "deposit_protection", "inventory",
        "garden", "redecoration", "keys", "fair_wear_and_tear", "missing_items",
        "utilities", "other",
    ),
    "evidence_strength": ("strong", "moderate", "weak", "insufficient"),
    "evidence_type": (
        "inventory_checkin", "inventory_checkout", "photos_before", "photos_after",
        "receipts", "invoices", "correspondence", "tenancy_agreement",
        "deposit_certificate", "witness_statement", "other",
    ),
    "mediation_status": ("expectation_adjustment", "active_negotiation", "settled", "escalated"),
    "message_type": ("text", "offer", "system", "ai_mediator"),
    "offer_status": ("pending", "accepted", "rejected", "countered", "expired"),
    "node_type": ("party", "property", "lease", "evidence", "event", "issue", "claimed_amount"),
    "edge_type": (
        "evidence_supports", "evidence_refutes", "evidence_relates_to",
        "event_before", "event_after", "event_during",
        "party_owns", "party_rents", "party_manages", "party_claims",
        "claim_relates_to", "issue_involves", "issue_caused_by",
        "lease_for", "deposit_protected_by",
    ),
    "citation_source": ("reasoning", "issue_supporting_case", "verified", "removed"),
}


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        sa.Enum(*values, name=name).create(bind, checkfirst=False)

    op.create_table(
        "intake_sessions",
        sa.Column("session_id", sa.String, primary_key=True),
        sa.Column("case_id", sa.String, nullable=False, unique=True),
        sa.Column("user_role", sa.Enum(name="user_role", create_type=False), nullable=True),
        sa.Column("current_stage", sa.Enum(name="intake_stage", create_type=False), nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("intake_complete", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("completeness_score", sa.Numeric, nullable=False, server_default="0"),
        sa.Column("role_explicitly_set", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_intake_sessions_user_role", "intake_sessions", ["user_role"])
    op.create_index("ix_intake_sessions_current_stage", "intake_sessions", ["current_stage"])

    op.create_table(
        "predictions",
        sa.Column("prediction_id", sa.String, primary_key=True),
        sa.Column("case_id", sa.String, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("overall_outcome", sa.Enum(name="outcome_type", create_type=False), nullable=False),
        sa.Column("overall_confidence", sa.Numeric, nullable=False),
        sa.Column("range_lo", sa.Numeric, nullable=True),
        sa.Column("range_hi", sa.Numeric, nullable=True),
        sa.Column("pipeline_version", sa.String, nullable=True),
        sa.Column("model_version", sa.String, nullable=True),
        sa.Column("retrieval_quality", sa.String, nullable=True),
        sa.Column("rag_confidence", sa.Numeric, nullable=True),
        sa.Column("pipeline_metadata", JSONB, nullable=True),
        sa.Column("citation_verification", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.CheckConstraint("overall_confidence >= 0 AND overall_confidence <= 1",
                           name="ck_predictions_overall_confidence_range"),
    )
    op.create_index("ix_predictions_case_id", "predictions", ["case_id"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])
    op.create_index("ix_predictions_pipeline_version", "predictions", ["pipeline_version"])

    op.create_table(
        "disputes",
        sa.Column("dispute_id", sa.String, primary_key=True),
        sa.Column("invite_code", sa.String, nullable=False, unique=True),
        sa.Column("status", sa.Enum(name="dispute_status", create_type=False), nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("created_by_role", sa.Enum(name="party_role", create_type=False), nullable=True),
        sa.Column("tenant_session_id", sa.String,
                  sa.ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True),
        sa.Column("landlord_session_id", sa.String,
                  sa.ForeignKey("intake_sessions.session_id", ondelete="SET NULL"), nullable=True),
        sa.Column("property_address", sa.Text, nullable=True),
        sa.Column("property_postcode", sa.String, nullable=True),
        sa.Column("deposit_amount", sa.Numeric, nullable=True),
        sa.Column("cached_prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="SET NULL"), nullable=True),
        sa.Column("prediction_cache_key", sa.String, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
        sa.CheckConstraint("deposit_amount IS NULL OR deposit_amount >= 0",
                           name="ck_disputes_deposit_amount_nonnegative"),
    )
    op.create_index("ix_disputes_tenant_session_id", "disputes", ["tenant_session_id"])
    op.create_index("ix_disputes_landlord_session_id", "disputes", ["landlord_session_id"])
    op.create_index("ix_disputes_cached_prediction_id", "disputes", ["cached_prediction_id"])

    op.create_table(
        "prediction_issues",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("issue_type", sa.Enum(name="issue_type", create_type=False), nullable=False),
        sa.Column("issue_description", sa.Text, nullable=True),
        sa.Column("outcome", sa.Enum(name="issue_outcome", create_type=False), nullable=False),
        sa.Column("raw_confidence", sa.Numeric, nullable=False),
        sa.Column("calibrated_confidence", sa.Numeric, nullable=True),
        sa.Column("predicted_amount", sa.Numeric, nullable=True),
        sa.Column("amount_range_lo", sa.Numeric, nullable=True),
        sa.Column("amount_range_hi", sa.Numeric, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("key_factors", JSONB, nullable=True),
        sa.Column("supporting_cases", JSONB, nullable=True),
        sa.Column("counterfactuals", JSONB, nullable=True),
        sa.Column("evidence_strength", sa.Enum(name="evidence_strength", create_type=False), nullable=True),
        sa.Column("data_completeness_impact", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("prediction_id", "ordinal", name="uq_prediction_issues_pred_ordinal"),
        sa.CheckConstraint("raw_confidence >= 0 AND raw_confidence <= 1",
                           name="ck_prediction_issues_raw_confidence_range"),
    )
    op.create_index("ix_prediction_issues_pred_ordinal", "prediction_issues", ["prediction_id", "ordinal"])
    op.create_index("ix_prediction_issues_issue_type", "prediction_issues", ["issue_type"])

    op.create_table(
        "prediction_reasoning_steps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("step_number", sa.Integer, nullable=True),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("confidence", sa.Numeric, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("prediction_id", "ordinal", name="uq_prediction_reasoning_pred_ordinal"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="ck_prediction_reasoning_confidence_range"),
    )
    op.create_index("ix_prediction_reasoning_pred_ordinal",
                    "prediction_reasoning_steps", ["prediction_id", "ordinal"])

    op.create_table(
        "prediction_citations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.String,
                  sa.ForeignKey("predictions.prediction_id", ondelete="CASCADE"), nullable=False),
        sa.Column("reasoning_step_id", sa.Integer,
                  sa.ForeignKey("prediction_reasoning_steps.id", ondelete="CASCADE"), nullable=True),
        sa.Column("citation_source", sa.Enum(name="citation_source", create_type=False), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("case_reference", sa.Text, nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("region", sa.String, nullable=True),
        sa.Column("paragraph", sa.Text, nullable=True),
        sa.Column("quote", sa.Text, nullable=True),
        sa.Column("relevance", sa.Text, nullable=True),
        sa.Column("similarity_score", sa.Numeric, nullable=True),
        sa.Column("verified", sa.Boolean, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_prediction_citations_pred", "prediction_citations", ["prediction_id"])
    op.create_index("ix_prediction_citations_step", "prediction_citations", ["reasoning_step_id"])
    op.create_index("ix_prediction_citations_source", "prediction_citations", ["citation_source"])

    op.create_table(
        "knowledge_graphs",
        sa.Column("case_id", sa.String, primary_key=True),
        sa.Column("graph_id", sa.String, nullable=False, unique=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=True),
        sa.Column("validation_errors", JSONB, nullable=True),
        sa.Column("validation_warnings", JSONB, nullable=True),
        sa.Column("validation_info", JSONB, nullable=True),
        sa.Column("is_consistent", sa.Boolean, nullable=True),
        sa.Column("data_quality_tier", sa.String, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )

    op.create_table(
        "kg_nodes",
        sa.Column("case_id", sa.String,
                  sa.ForeignKey("knowledge_graphs.case_id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("node_id", sa.String, primary_key=True),
        sa.Column("node_type", sa.Enum(name="node_type", create_type=False), nullable=False),
        sa.Column("confidence", sa.Numeric, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("event_date", sa.Date, nullable=True),
        sa.Column("amount", sa.Numeric, nullable=True),
        sa.Column("node_data", JSONB, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1",
                           name="ck_kg_nodes_confidence_range"),
    )
    op.create_index("ix_kg_nodes_case_type", "kg_nodes", ["case_id", "node_type"])
    op.execute(
        "CREATE INDEX ix_kg_nodes_event_timeline ON kg_nodes(case_id, event_date) "
        "WHERE node_type = 'event'"
    )
    op.execute(
        "CREATE INDEX ix_kg_nodes_claim_amount ON kg_nodes(case_id, amount) "
        "WHERE node_type = 'claimed_amount'"
    )

    op.create_table(
        "kg_edges",
        sa.Column("case_id", sa.String, primary_key=True),
        sa.Column("edge_id", sa.String, primary_key=True),
        sa.Column("edge_type", sa.Enum(name="edge_type", create_type=False), nullable=False),
        sa.Column("source_node_id", sa.String, nullable=False),
        sa.Column("target_node_id", sa.String, nullable=False),
        sa.Column("confidence", sa.Numeric, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id", "source_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "target_node_id"],
            ["kg_nodes.case_id", "kg_nodes.node_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1",
                           name="ck_kg_edges_confidence_range"),
    )
    op.create_index("ix_kg_edges_src", "kg_edges", ["case_id", "source_node_id", "edge_type"])
    op.create_index("ix_kg_edges_tgt", "kg_edges", ["case_id", "target_node_id", "edge_type"])

    op.create_table(
        "mediations",
        sa.Column("mediation_id", sa.String, primary_key=True),
        sa.Column("dispute_id", sa.String,
                  sa.ForeignKey("disputes.dispute_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", sa.Enum(name="mediation_status", create_type=False), nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=True),
        sa.Column("settled_at", sa.Text, nullable=True),
        sa.Column("settlement_amount", sa.Numeric, nullable=True),
        sa.Column("escalated_at", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload", JSONB, nullable=False),
    )

    op.create_table(
        "mediation_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("mediation_id", sa.String,
                  sa.ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        # May be "tenant", "landlord", or "ai_mediator"; keep as String, not party_role enum.
        sa.Column("sender_role", sa.String, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("message_type", sa.Enum(name="message_type", create_type=False), nullable=False),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("offer_id", sa.String, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("mediation_id", "message_id", name="uq_mediation_messages_message_id"),
        sa.UniqueConstraint("mediation_id", "ordinal", name="uq_mediation_messages_med_ordinal"),
    )
    op.create_index("ix_mediation_messages_med_ordinal", "mediation_messages", ["mediation_id", "ordinal"])
    op.create_index("ix_mediation_messages_med_ts", "mediation_messages", ["mediation_id", "timestamp"])
    op.create_index("ix_mediation_messages_offer", "mediation_messages", ["offer_id"])

    op.create_table(
        "structured_offers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("mediation_id", sa.String,
                  sa.ForeignKey("mediations.mediation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_id", sa.String, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("amount", sa.Numeric, nullable=False),
        sa.Column("proposed_by_role", sa.Enum(name="party_role", create_type=False), nullable=False),
        sa.Column("status", sa.Enum(name="offer_status", create_type=False), nullable=False),
        sa.Column("proposed_at", sa.Text, nullable=False),
        sa.Column("responded_at", sa.Text, nullable=True),
        sa.Column("counter_amount", sa.Numeric, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("mediation_id", "offer_id", name="uq_structured_offers_offer_id"),
        sa.UniqueConstraint("mediation_id", "ordinal", name="uq_structured_offers_med_ordinal"),
        sa.CheckConstraint("amount >= 0", name="ck_structured_offers_amount_nonnegative"),
    )
    op.create_index("ix_offers_med_ordinal", "structured_offers", ["mediation_id", "ordinal"])
    op.create_index("ix_offers_med_status", "structured_offers", ["mediation_id", "status"])

    op.create_table(
        "evidence_metadata",
        sa.Column("case_id", sa.String, primary_key=True),
        sa.Column("evidence_id", sa.String, primary_key=True),
        sa.Column("evidence_type", sa.Enum(name="evidence_type", create_type=False), nullable=False),
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("file_name", sa.Text, nullable=True),
        sa.Column("file_type", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("image_description", sa.Text, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_evidence_metadata_case_id", "evidence_metadata", ["case_id"])
    op.create_index("ix_evidence_metadata_type", "evidence_metadata", ["evidence_type"])


def downgrade() -> None:
    op.drop_table("evidence_metadata")
    op.drop_table("structured_offers")
    op.drop_table("mediation_messages")
    op.drop_table("mediations")
    op.drop_table("kg_edges")
    op.drop_table("kg_nodes")
    op.drop_table("knowledge_graphs")
    op.drop_table("prediction_citations")
    op.drop_table("prediction_reasoning_steps")
    op.drop_table("prediction_issues")
    op.drop_table("disputes")
    op.drop_table("predictions")
    op.drop_table("intake_sessions")

    bind = op.get_bind()
    for name in reversed(list(ENUMS.keys())):
        sa.Enum(name=name).drop(bind, checkfirst=False)
```

- [ ] **Step 2: Run upgrade**

```bash
make db-reset
```

Expected: clean migration; `psql` shows 13 tables.

- [ ] **Step 3: Verify**

```bash
docker compose exec -T postgres psql -U proposer -d proposer -c "\dt"
```

Expected: lists `intake_sessions`, `disputes`, `predictions`, `prediction_issues`, `prediction_reasoning_steps`, `prediction_citations`, `knowledge_graphs`, `kg_nodes`, `kg_edges`, `mediations`, `mediation_messages`, `structured_offers`, `evidence_metadata`, plus `alembic_version`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/alembic/versions/0001_initial_schema.py
git commit -m "feat(db): initial Alembic migration covering 13 tables and enums"
```

### Task 2.9 — Migration round-trip test

**Files:**
- Create: `apps/api/tests/db/test_migration_roundtrip.py`

- [ ] **Step 1: Write the test**

```python
# apps/api/tests/db/test_migration_roundtrip.py
"""Verifies upgrade head + downgrade base both succeed cleanly on an ephemeral DB."""

import os
import subprocess
import uuid
from pathlib import Path

from pytest_postgresql import factories

postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")


def _admin_url(postgresql_proc) -> str:
    return (
        f"postgresql://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/postgres"
    )


def _async_url_for_db(postgresql_proc, db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/{db_name}"
    )


def test_alembic_upgrade_then_downgrade_is_clean(postgresql_proc) -> None:
    import psycopg

    db_name = f"proposer_migration_{uuid.uuid4().hex[:12]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {db_name}")

    env = {**os.environ, "DATABASE_URL": _async_url_for_db(postgresql_proc, db_name)}
    cwd = Path(__file__).resolve().parents[3]
    try:
        subprocess.run(["alembic", "-c", "alembic.ini", "upgrade", "head"],
                       check=True, env=env, cwd=cwd)
        with psycopg.connect(admin_url.replace("/postgres", f"/{db_name}")) as conn:
            constraint = conn.execute(
                "SELECT conname FROM pg_constraint WHERE conname = 'ck_kg_nodes_confidence_range'"
            ).fetchone()
            assert constraint is not None
        subprocess.run(["alembic", "-c", "alembic.ini", "downgrade", "base"],
                       check=True, env=env, cwd=cwd)
        subprocess.run(["alembic", "-c", "alembic.ini", "upgrade", "head"],
                       check=True, env=env, cwd=cwd)
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
```

- [ ] **Step 2: Run**

```
pytest apps/api/tests/db/test_migration_roundtrip.py -v
```

Expected: PASS (no exceptions, exit code 0 from each alembic call).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/db/test_migration_roundtrip.py
git commit -m "test(db): assert alembic upgrade↔downgrade round-trip"
```

---

## Phase 3 — Repositories

Goal: every repository converts between Pydantic domain models and ORM rows. Repositories never commit. Each gets a focused unit test.

### Task 3.0 — `pytest-postgresql` fixture (template + clone-per-test)

**Files:**
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Replace conftest's DB fixtures**

Append to `apps/api/tests/conftest.py`:

```python
import subprocess
import os
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from pytest_postgresql import factories
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Use a session-scoped Postgres process started by pytest-postgresql.
postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")


def _admin_url(postgresql_proc) -> str:
    return (
        f"postgresql://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/postgres"
    )


def _async_url_for_db(postgresql_proc, db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/{db_name}"
    )


@pytest.fixture(scope="session")
def _migrated_template(postgresql_proc):
    """Create a template DB and run Alembic against it once per session."""
    import psycopg

    template_name = f"proposer_template_{uuid.uuid4().hex[:8]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name}")
        conn.execute(f"CREATE DATABASE {template_name}")

    template_url = _async_url_for_db(postgresql_proc, template_name)
    env = {**os.environ, "DATABASE_URL": template_url}
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        check=True, env=env, cwd=Path(__file__).resolve().parents[3],
    )
    yield template_name
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {template_name} WITH (FORCE)")


@pytest_asyncio.fixture
async def db_sessionmaker(postgresql_proc, _migrated_template):
    """One isolated migrated database/sessionmaker per test."""
    import psycopg

    db_name = f"proposer_test_{uuid.uuid4().hex[:12]}"
    admin_url = _admin_url(postgresql_proc)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {db_name} TEMPLATE {_migrated_template}")

    url = _async_url_for_db(postgresql_proc, db_name)
    engine = create_async_engine(url, poolclass=NullPool, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield sm
    await engine.dispose()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest_asyncio.fixture
async def db_session(db_sessionmaker) -> AsyncIterator[AsyncSession]:
    """One AsyncSession from the per-test DB."""
    async with db_sessionmaker() as session:
        yield session
        await session.rollback()
```

> The fixture trades a tiny per-test cost (copy from template) for clean isolation and Alembic-tested schema. `uow_factory` derives from `db_sessionmaker`, so API tests can seed/assert through the same database that the route dependency override uses. If startup time becomes a problem, switch to a session-scoped engine + truncate-tables per test in a follow-up.

- [ ] **Step 2: Sanity-check the fixture**

```python
# Inline ad-hoc sanity test in apps/api/tests/db/test_fixture.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_db_session_can_query(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT COUNT(*) FROM intake_sessions"))
    assert result.scalar_one() == 0
```

- [ ] **Step 3: Run**

```
pytest apps/api/tests/db/test_fixture.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/conftest.py apps/api/tests/db/test_fixture.py
git commit -m "test(db): add db_session fixture cloned from migrated template"
```

### Task 3.1 — `SessionsRepo` (template repository — full TDD walkthrough)

**Files:**
- Create: `apps/api/src/db/repositories/__init__.py`
- Create: `apps/api/src/db/repositories/sessions_repo.py`
- Create: `apps/api/tests/db/repositories/__init__.py`
- Create: `apps/api/tests/db/repositories/test_sessions_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/db/repositories/test_sessions_repo.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.sessions_repo import SessionsRepo
from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
from packages.llm_orchestrator.models.conversation import (
    ConversationState, IntakeStage,
)


def _make_state(session_id: str = "sess-1", case_id: str = "case-1") -> ConversationState:
    return ConversationState(
        session_id=session_id,
        case_file=CaseFile(case_id=case_id, user_role=PartyRole.TENANT),
        messages=[],
        current_stage=IntakeStage.GREETING,
        started_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        stages_completed=[],
        current_stage_attempts=0,
        last_extraction_successful=True,
        extraction_errors=[],
        role_explicitly_set=False,
    )


@pytest.mark.asyncio
async def test_save_then_get_returns_identical_state(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    original = _make_state()
    await repo.save(original)
    await db_session.commit()

    loaded = await repo.get(original.session_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == original.model_dump(mode="json")


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    assert await repo.get("nope") is None


@pytest.mark.asyncio
async def test_save_is_upsert(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    state = _make_state()
    await repo.save(state)
    await db_session.commit()

    state.current_stage = IntakeStage.BASIC_DETAILS
    await repo.save(state)
    await db_session.commit()

    loaded = await repo.get(state.session_id)
    assert loaded is not None
    assert loaded.current_stage == IntakeStage.BASIC_DETAILS


@pytest.mark.asyncio
async def test_get_by_case_id(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    state = _make_state(session_id="sess-2", case_id="case-2")
    await repo.save(state)
    await db_session.commit()

    loaded = await repo.get_by_case_id("case-2")
    assert loaded is not None
    assert loaded.session_id == "sess-2"


@pytest.mark.asyncio
async def test_delete_removes_row(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    state = _make_state()
    await repo.save(state)
    await db_session.commit()

    await repo.delete(state.session_id)
    await db_session.commit()

    assert await repo.get(state.session_id) is None


@pytest.mark.asyncio
async def test_list_all_returns_all_sessions(db_session: AsyncSession) -> None:
    repo = SessionsRepo(db_session)
    a = _make_state(session_id="sa", case_id="ca")
    b = _make_state(session_id="sb", case_id="cb")
    await repo.save(a)
    await repo.save(b)
    await db_session.commit()

    listed = {s.session_id for s in await repo.list_all()}
    assert listed == {"sa", "sb"}
```

- [ ] **Step 2: Run and verify failure**

```
pytest apps/api/tests/db/repositories/test_sessions_repo.py -v
```

Expected: ImportError for `apps.api.src.db.repositories.sessions_repo`.

- [ ] **Step 3: Implement the repository**

```python
# apps/api/src/db/repositories/__init__.py
```

```python
# apps/api/src/db/repositories/sessions_repo.py
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import IntakeSessionRow
from packages.llm_orchestrator.models.conversation import ConversationState


@dataclass(frozen=True)
class VersionedConversationState:
    state: ConversationState
    version: int


class ConcurrentUpdateError(RuntimeError):
    pass


class SessionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, state: ConversationState, *, expected_version: int | None = None) -> None:
        payload = state.model_dump(mode="json")
        values = dict(
            session_id=state.session_id,
            case_id=state.case_file.case_id,
            user_role=(state.case_file.user_role.value
                       if state.case_file.user_role else None),
            current_stage=state.current_stage.value,
            started_at=state.started_at,
            updated_at=state.updated_at,
            intake_complete=bool(state.case_file.intake_complete),
            completeness_score=float(state.case_file.completeness_score or 0.0),
            role_explicitly_set=bool(state.role_explicitly_set),
            payload=payload,
        )
        if expected_version is not None:
            result = await self._s.execute(
                update(IntakeSessionRow)
                .where(
                    IntakeSessionRow.session_id == state.session_id,
                    IntakeSessionRow.version == expected_version,
                )
                .values(**values, version=IntakeSessionRow.version + 1)
            )
            if result.rowcount != 1:
                raise ConcurrentUpdateError(f"session changed: {state.session_id}")
            return

        stmt = pg_insert(IntakeSessionRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[IntakeSessionRow.session_id],
            set_={**{k: stmt.excluded[k] for k in values if k != "session_id"},
                  "version": IntakeSessionRow.version + 1},
        )
        await self._s.execute(stmt)

    async def get(self, session_id: str) -> ConversationState | None:
        row = await self._s.get(IntakeSessionRow, session_id)
        return ConversationState.model_validate(row.payload) if row else None

    async def get_with_version(self, session_id: str) -> VersionedConversationState | None:
        row = await self._s.get(IntakeSessionRow, session_id)
        if row is None:
            return None
        return VersionedConversationState(
            state=ConversationState.model_validate(row.payload),
            version=row.version,
        )

    async def get_by_case_id(self, case_id: str) -> ConversationState | None:
        result = await self._s.execute(
            select(IntakeSessionRow).where(IntakeSessionRow.case_id == case_id)
        )
        row = result.scalar_one_or_none()
        return ConversationState.model_validate(row.payload) if row else None

    async def delete(self, session_id: str) -> None:
        row = await self._s.get(IntakeSessionRow, session_id)
        if row:
            await self._s.delete(row)

    async def list_all(self) -> list[ConversationState]:
        result = await self._s.execute(select(IntakeSessionRow))
        return [ConversationState.model_validate(r.payload) for r in result.scalars()]
```

- [ ] **Step 4: Run and verify pass**

```
pytest apps/api/tests/db/repositories/test_sessions_repo.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/db/repositories/__init__.py apps/api/src/db/repositories/sessions_repo.py apps/api/tests/db/repositories/test_sessions_repo.py apps/api/tests/db/repositories/__init__.py
git commit -m "feat(db): add SessionsRepo with save/get/list/delete + tests"
```

### Task 3.2 — `DisputesRepo`

Mirrors `SessionsRepo`. Public API:
- `save(dispute: DisputeCase)` → upsert by `dispute_id`
- `get(dispute_id) → DisputeCase | None`
- `get_by_invite_code(code) → DisputeCase | None`
- `get_by_session_id(session_id) → list[DisputeCase]`
- `lock(dispute_id)` → row-locked SELECT FOR UPDATE; returns `DisputeCase | None` for short dispute mutation transactions
- `lock_for_prediction_cache(dispute_id)` → row-locked SELECT FOR UPDATE; returns a small projection DTO with `dispute: DisputeCase` and `cached_prediction_id: str | None`
- `set_cached_prediction_id(dispute_id, prediction_id)` → small UPDATE
- `delete(dispute_id)`
- `list_all()`

**Files:**
- Create: `apps/api/src/db/repositories/disputes_repo.py`
- Create: `apps/api/tests/db/repositories/test_disputes_repo.py`

- [ ] **Step 1: Write the failing tests** (analogous to Task 3.1: round-trip identity, get_by_invite_code, get_by_session_id, set_cached_prediction_id updates correctly, list_all, delete). Use `DisputeCase` factory:

```python
# apps/api/tests/db/repositories/test_disputes_repo.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.disputes_repo import DisputesRepo
from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus
from packages.llm_orchestrator.models.case_file import PartyRole


def _make_dispute(dispute_id: str = "DISP-1", invite: str = "INV-1") -> DisputeCase:
    return DisputeCase(
        dispute_id=dispute_id,
        invite_code=invite,
        status=DisputeStatus.WAITING_FOR_LANDLORD,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        created_by_role=PartyRole.TENANT,
        tenant_session_id=None, landlord_session_id=None,
        property_address=None, property_postcode=None, deposit_amount=None,
        notes=None,
    )


@pytest.mark.asyncio
async def test_dispute_roundtrip(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute()
    await repo.save(d)
    await db_session.commit()
    loaded = await repo.get(d.dispute_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == d.model_dump(mode="json")


@pytest.mark.asyncio
async def test_get_by_invite_code(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute(dispute_id="DISP-A", invite="ABC123")
    await repo.save(d)
    await db_session.commit()
    loaded = await repo.get_by_invite_code("ABC123")
    assert loaded is not None and loaded.dispute_id == "DISP-A"


@pytest.mark.asyncio
async def test_set_cached_prediction_id(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute()
    await repo.save(d)
    await db_session.commit()

    await repo.set_cached_prediction_id(d.dispute_id, None)
    await db_session.commit()


@pytest.mark.asyncio
async def test_lock_for_prediction_cache_exposes_projection(db_session: AsyncSession) -> None:
    repo = DisputesRepo(db_session)
    d = _make_dispute()
    await repo.save(d)
    await db_session.commit()

    locked = await repo.lock_for_prediction_cache(d.dispute_id)

    assert locked is not None
    assert locked.dispute.dispute_id == d.dispute_id
    assert locked.cached_prediction_id is None
```

- [ ] **Step 2: Implement**

```python
# apps/api/src/db/repositories/disputes_repo.py
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import DisputeRow
from apps.api.src.db.repositories.sessions_repo import ConcurrentUpdateError
from packages.llm_orchestrator.models.dispute import DisputeCase


@dataclass(frozen=True)
class LockedDisputeForPredictionCache:
    dispute: DisputeCase
    cached_prediction_id: str | None
    prediction_cache_key: str | None


@dataclass(frozen=True)
class VersionedDisputeCase:
    dispute: DisputeCase
    version: int


class DisputesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, dispute: DisputeCase, *, expected_version: int | None = None) -> None:
        payload = dispute.model_dump(mode="json")
        values = dict(
            dispute_id=dispute.dispute_id,
            invite_code=dispute.invite_code,
            status=dispute.status.value,
            created_at=dispute.created_at,
            updated_at=dispute.updated_at,
            created_by_role=(dispute.created_by_role.value
                             if hasattr(dispute.created_by_role, "value")
                             else dispute.created_by_role),
            tenant_session_id=dispute.tenant_session_id,
            landlord_session_id=dispute.landlord_session_id,
            property_address=dispute.property_address,
            property_postcode=dispute.property_postcode,
            deposit_amount=dispute.deposit_amount,
            cached_prediction_id=None,  # only set explicitly via set_cached_prediction_id
            prediction_cache_key=None,  # only set with cached_prediction_id
            payload=payload,
        )
        if expected_version is not None:
            result = await self._s.execute(
                update(DisputeRow)
                .where(
                    DisputeRow.dispute_id == dispute.dispute_id,
                    DisputeRow.version == expected_version,
                )
                .values(**{k: v for k, v in values.items() if k != "cached_prediction_id"},
                        version=DisputeRow.version + 1)
            )
            if result.rowcount != 1:
                raise ConcurrentUpdateError(f"dispute changed: {dispute.dispute_id}")
            return

        stmt = pg_insert(DisputeRow).values(**values)
        # do NOT overwrite cached_prediction_id on conflict
        update_cols = {k: stmt.excluded[k] for k in values
                       if k not in ("dispute_id", "cached_prediction_id", "prediction_cache_key")}
        update_cols["version"] = DisputeRow.version + 1
        stmt = stmt.on_conflict_do_update(
            index_elements=[DisputeRow.dispute_id], set_=update_cols,
        )
        await self._s.execute(stmt)

    async def get(self, dispute_id: str) -> DisputeCase | None:
        row = await self._s.get(DisputeRow, dispute_id)
        return DisputeCase.model_validate(row.payload) if row else None

    async def get_with_version(self, dispute_id: str) -> VersionedDisputeCase | None:
        row = await self._s.get(DisputeRow, dispute_id)
        if row is None:
            return None
        return VersionedDisputeCase(
            dispute=DisputeCase.model_validate(row.payload),
            version=row.version,
        )

    async def get_by_invite_code(self, code: str) -> DisputeCase | None:
        result = await self._s.execute(
            select(DisputeRow).where(DisputeRow.invite_code == code)
        )
        row = result.scalar_one_or_none()
        return DisputeCase.model_validate(row.payload) if row else None

    async def get_by_session_id(self, session_id: str) -> list[DisputeCase]:
        result = await self._s.execute(
            select(DisputeRow).where(
                (DisputeRow.tenant_session_id == session_id)
                | (DisputeRow.landlord_session_id == session_id)
            )
        )
        return [DisputeCase.model_validate(r.payload) for r in result.scalars()]

    async def lock(self, dispute_id: str) -> DisputeCase | None:
        result = await self._s.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id).with_for_update()
        )
        row = result.scalar_one_or_none()
        return DisputeCase.model_validate(row.payload) if row else None

    async def lock_for_prediction_cache(
        self, dispute_id: str
    ) -> LockedDisputeForPredictionCache | None:
        result = await self._s.execute(
            select(DisputeRow).where(DisputeRow.dispute_id == dispute_id).with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return LockedDisputeForPredictionCache(
            dispute=DisputeCase.model_validate(row.payload),
            cached_prediction_id=row.cached_prediction_id,
            prediction_cache_key=row.prediction_cache_key,
        )

    async def set_cached_prediction_id(
        self, dispute_id: str, prediction_id: str | None, *, cache_key: str | None = None,
    ) -> None:
        await self._s.execute(
            update(DisputeRow)
            .where(DisputeRow.dispute_id == dispute_id)
            .values(cached_prediction_id=prediction_id, prediction_cache_key=cache_key)
        )

    async def delete(self, dispute_id: str) -> None:
        row = await self._s.get(DisputeRow, dispute_id)
        if row:
            await self._s.delete(row)

    async def list_all(self) -> list[DisputeCase]:
        result = await self._s.execute(select(DisputeRow))
        return [DisputeCase.model_validate(r.payload) for r in result.scalars()]
```

- [ ] **Step 3: Run tests**

```
pytest apps/api/tests/db/repositories/test_disputes_repo.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/db/repositories/disputes_repo.py apps/api/tests/db/repositories/test_disputes_repo.py
git commit -m "feat(db): add DisputesRepo with row-lock + cached_prediction_id setter"
```

### Task 3.3 — `PredictionsRepo` (with children)

Public API:
- `save(prediction: PredictionResult)` → upsert prediction + replace child rows transactionally (delete-then-insert children)
- `get(prediction_id) → PredictionResult | None`
- `get_by_case_id(case_id) → list[PredictionResult]`
- `delete(prediction_id)`

**Files:**
- Create: `apps/api/src/db/repositories/predictions_repo.py`
- Create: `apps/api/tests/db/repositories/test_predictions_repo.py`

- [ ] **Step 1: Test — round-trip a real fixture-shape prediction with 5 issues, 7 reasoning steps, 3 verified citations**

```python
# apps/api/tests/db/repositories/test_predictions_repo.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.predictions_repo import PredictionsRepo
from packages.llm_orchestrator.models.prediction_v2 import (
    PredictionResult, IssuePrediction, ReasoningStep, Citation,
    OutcomeType, IssueOutcome, IssueType, EvidenceStrength,
)


def _make_prediction(prediction_id: str = "p1", case_id: str = "c1") -> PredictionResult:
    citation = Citation(
        case_reference="LON/00AY/2023/0042", year=2023, region="London",
        paragraph="12", quote="Q" * 80, relevance="R" * 80,
        similarity_score=0.91, verified=True,
    )
    issue = IssuePrediction(
        issue_type=IssueType.CLEANING, issue_description="Dirty kitchen",
        outcome=IssueOutcome.LANDLORD_WINS, raw_confidence=0.7,
        predicted_amount=120.0, amount_range=(80.0, 160.0),
        reasoning="Inventory checkin clean, checkout dirty.",
        key_factors=["clear inventory"], supporting_cases=[citation],
        counterfactuals=[], evidence_strength=EvidenceStrength.MODERATE,
    )
    step = ReasoningStep(
        step_number=1, category="legal_framework",
        title="Deposit framework", content="Long content about prescribed info...",
        citations=[citation], confidence=0.8,
    )
    return PredictionResult(
        case_id=case_id, prediction_id=prediction_id,
        timestamp="2026-01-01T00:00:00",
        overall_outcome=OutcomeType.SPLIT, overall_confidence=0.65,
        outcome_summary="Mixed outcome",
        tenant_recovery_amount=400.0, landlord_recovery_amount=120.0,
        predicted_settlement_range=(380.0, 500.0),
        issue_predictions=[issue], reasoning_trace=[step],
        retrieved_cases=[], total_cases_analyzed=42,
        pipeline_metadata={"llm_calls": 3, "tokens": 12000, "latency_ms": 4000},
        temporal_distribution={2023: 12, 2022: 10},
        key_strengths=["clear evidence"], key_weaknesses=[],
        uncertainties=[], missing_information=[],
        model_version="2.0.0", pipeline_version="v2",
    )


@pytest.mark.asyncio
async def test_prediction_roundtrip_with_children(db_session: AsyncSession) -> None:
    repo = PredictionsRepo(db_session)
    p = _make_prediction()
    await repo.save(p)
    await db_session.commit()
    loaded = await repo.get(p.prediction_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == p.model_dump(mode="json")


@pytest.mark.asyncio
async def test_save_replaces_children_on_upsert(db_session: AsyncSession) -> None:
    repo = PredictionsRepo(db_session)
    p = _make_prediction()
    await repo.save(p)
    await db_session.commit()

    # mutate: drop the issue
    p.issue_predictions = []
    await repo.save(p)
    await db_session.commit()

    loaded = await repo.get(p.prediction_id)
    assert loaded is not None
    assert loaded.issue_predictions == []


@pytest.mark.asyncio
async def test_get_by_case_id_returns_only_matching(db_session: AsyncSession) -> None:
    repo = PredictionsRepo(db_session)
    p1 = _make_prediction(prediction_id="p1", case_id="case-A")
    p2 = _make_prediction(prediction_id="p2", case_id="case-B")
    await repo.save(p1)
    await repo.save(p2)
    await db_session.commit()
    listed = await repo.get_by_case_id("case-A")
    assert {p.prediction_id for p in listed} == {"p1"}
```

- [ ] **Step 2: Implement**

```python
# apps/api/src/db/repositories/predictions_repo.py
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import (
    PredictionRow, PredictionIssueRow, PredictionReasoningStepRow,
    PredictionCitationRow,
)
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult


class PredictionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, p: PredictionResult) -> None:
        payload = p.model_dump(mode="json")
        # Parent
        rng = p.predicted_settlement_range or (None, None)
        values = dict(
            prediction_id=p.prediction_id,
            case_id=p.case_id,
            created_at=p.timestamp,
            overall_outcome=p.overall_outcome.value,
            overall_confidence=float(p.overall_confidence),
            range_lo=rng[0], range_hi=rng[1],
            pipeline_version=getattr(p, "pipeline_version", None),
            model_version=getattr(p, "model_version", None),
            retrieval_quality=payload.get("retrieval_quality"),
            rag_confidence=payload.get("rag_confidence"),
            pipeline_metadata=payload.get("pipeline_metadata"),
            citation_verification=payload.get("citation_verification"),
            metadata_=payload.get("metadata"),
            payload=payload,
        )
        stmt = pg_insert(PredictionRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PredictionRow.prediction_id],
            set_={k: stmt.excluded[k] for k in values if k != "prediction_id"},
        )
        await self._s.execute(stmt)

        # Replace children
        await self._s.execute(
            delete(PredictionIssueRow).where(PredictionIssueRow.prediction_id == p.prediction_id)
        )
        await self._s.execute(
            delete(PredictionReasoningStepRow).where(
                PredictionReasoningStepRow.prediction_id == p.prediction_id
            )
        )
        await self._s.execute(
            delete(PredictionCitationRow).where(
                PredictionCitationRow.prediction_id == p.prediction_id
            )
        )

        for i, issue in enumerate(p.issue_predictions):
            ip = issue.model_dump(mode="json")
            ar = issue.amount_range or (None, None)
            self._s.add(PredictionIssueRow(
                prediction_id=p.prediction_id,
                ordinal=i,
                issue_type=issue.issue_type.value,
                issue_description=issue.issue_description,
                outcome=issue.outcome.value,
                raw_confidence=float(issue.raw_confidence),
                calibrated_confidence=ip.get("calibrated_confidence"),
                predicted_amount=issue.predicted_amount,
                amount_range_lo=ar[0], amount_range_hi=ar[1],
                reasoning=issue.reasoning,
                key_factors=ip.get("key_factors"),
                supporting_cases=ip.get("supporting_cases"),
                counterfactuals=ip.get("counterfactuals"),
                evidence_strength=(issue.evidence_strength.value
                                   if issue.evidence_strength else None),
                data_completeness_impact=ip.get("data_completeness_impact"),
                payload=ip,
            ))
            for j, c in enumerate(issue.supporting_cases or []):
                cd = c.model_dump(mode="json")
                self._s.add(PredictionCitationRow(
                    prediction_id=p.prediction_id, reasoning_step_id=None,
                    citation_source="issue_supporting_case", ordinal=j,
                    case_reference=c.case_reference, year=c.year, region=c.region,
                    paragraph=c.paragraph, quote=c.quote, relevance=c.relevance,
                    similarity_score=c.similarity_score, verified=c.verified,
                    payload=cd,
                ))

        # Reasoning trace and per-step citations need a flush to get reasoning_step_id
        for i, step in enumerate(p.reasoning_trace):
            sd = step.model_dump(mode="json")
            row = PredictionReasoningStepRow(
                prediction_id=p.prediction_id, ordinal=i,
                step_number=step.step_number, category=step.category,
                title=step.title, content=step.content, confidence=step.confidence,
                payload=sd,
            )
            self._s.add(row)
            await self._s.flush()  # populate row.id for FK below
            for j, c in enumerate(step.citations or []):
                cd = c.model_dump(mode="json")
                self._s.add(PredictionCitationRow(
                    prediction_id=p.prediction_id, reasoning_step_id=row.id,
                    citation_source="reasoning", ordinal=j,
                    case_reference=c.case_reference, year=c.year, region=c.region,
                    paragraph=c.paragraph, quote=c.quote, relevance=c.relevance,
                    similarity_score=c.similarity_score, verified=c.verified,
                    payload=cd,
                ))

        # Verified citations from citation_verification.verified_citations[]
        verified = (payload.get("citation_verification") or {}).get("verified_citations") or []
        for j, vc in enumerate(verified):
            self._s.add(PredictionCitationRow(
                prediction_id=p.prediction_id, reasoning_step_id=None,
                citation_source="verified", ordinal=j,
                case_reference=vc.get("case_reference"), year=vc.get("year"),
                region=vc.get("region"), paragraph=vc.get("paragraph"),
                quote=vc.get("quote"), relevance=vc.get("relevance"),
                similarity_score=vc.get("similarity_score"),
                verified=vc.get("verified", True),
                payload=vc,
            ))

    async def get(self, prediction_id: str) -> PredictionResult | None:
        row = await self._s.get(PredictionRow, prediction_id)
        return PredictionResult.model_validate(row.payload) if row else None

    async def get_by_case_id(self, case_id: str) -> list[PredictionResult]:
        result = await self._s.execute(
            select(PredictionRow).where(PredictionRow.case_id == case_id)
        )
        return [PredictionResult.model_validate(r.payload) for r in result.scalars()]

    async def delete(self, prediction_id: str) -> None:
        row = await self._s.get(PredictionRow, prediction_id)
        if row:
            await self._s.delete(row)
```

- [ ] **Step 3: Run + commit**

```
pytest apps/api/tests/db/repositories/test_predictions_repo.py -v
git add apps/api/src/db/repositories/predictions_repo.py apps/api/tests/db/repositories/test_predictions_repo.py
git commit -m "feat(db): add PredictionsRepo with normalized children and round-trip identity"
```

### Task 3.4 — `KnowledgeGraphRepo` (polymorphic nodes)

Public API:
- `save(kg: KnowledgeGraph)` → upsert graph, replace nodes + edges (delete-then-insert)
- `get(case_id) → KnowledgeGraph | None`
- `delete(case_id)`
- `list_case_ids() → list[str]`

The polymorphic node read must preserve the existing `JSONGraphStore` behavior. Extract the current `_serialize_graph`, `_serialize_node`, `_deserialize_graph`, and `_deserialize_node` logic into a reusable helper module before moving persistence to Postgres. Plain `KnowledgeGraph.model_validate()` is not enough because `KnowledgeGraph.nodes` is typed as `list[BaseNode]` and can drop subclass-only fields. The write extracts `event_date` (only for `EventNode`) and `amount` (only for `ClaimedAmountNode`) into typed columns; everything else goes into `node_data` JSONB with `_node_class` preserved.

**Files:**
- Create: `packages/kg_builder/storage/graph_serialization.py`
- Modify: `packages/kg_builder/storage/json_store.py` (delegate to shared serialization helpers)
- Create: `apps/api/src/db/repositories/kg_repo.py`
- Create: `apps/api/tests/db/repositories/test_kg_repo.py`

- [ ] **Step 1: Test — round-trip a graph that has at least one node of each of the 7 types and a few edges**

```python
# apps/api/tests/db/repositories/test_kg_repo.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.repositories.kg_repo import KnowledgeGraphRepo
from packages.kg_builder.models.graph import KnowledgeGraph
from packages.kg_builder.models.nodes import (
    PartyNode, PropertyNode, LeaseNode, EvidenceNode, EventNode,
    IssueNode, ClaimedAmountNode,
)
from packages.kg_builder.models.edges import Edge, EdgeType


def _make_kg(case_id: str = "case-1") -> KnowledgeGraph:
    kg = KnowledgeGraph(case_id=case_id, graph_id="g1",
                        created_at="2026-01-01T00:00:00")
    party = PartyNode(node_id="party_tenant", role="tenant",
                      confidence=1.0, source="user_input")
    prop = PropertyNode(node_id="property_main",
                        address="1 X St", postcode="X1 1XX",
                        confidence=1.0, source="user_input")
    lease = LeaseNode(node_id="lease_main", confidence=1.0, source="user_input")
    ev = EvidenceNode(node_id="evidence_1", evidence_type="receipts",
                      description="receipt", confidence=1.0, source="user_input")
    event = EventNode(node_id="event_1", event_type="checkout",
                      event_date="2025-12-01", description="moved out",
                      actors=[], confidence=1.0, source="user_input")
    issue = IssueNode(node_id="issue_cleaning", issue_type="cleaning",
                      description="dirty", disputed=True, severity="high",
                      confidence=1.0, source="user_input")
    claim = ClaimedAmountNode(node_id="claim_1", claimant="landlord",
                              amount=420.0, issue_type="cleaning",
                              description="cleaning cost",
                              confidence=1.0, source="user_input")
    for n in [party, prop, lease, ev, event, issue, claim]:
        kg.add_node(n)
    kg.add_edge(Edge(edge_id="e1", edge_type=EdgeType.PARTY_OWNS,
                     source_node_id="party_tenant", target_node_id="property_main",
                     confidence=1.0, source="user_input", description="x"))
    kg.add_edge(Edge(edge_id="e2", edge_type=EdgeType.ISSUE_INVOLVES,
                     source_node_id="issue_cleaning", target_node_id="claim_1",
                     confidence=1.0, source="user_input", description="x"))
    return kg


@pytest.mark.asyncio
async def test_kg_roundtrip_all_node_types(db_session: AsyncSession) -> None:
    repo = KnowledgeGraphRepo(db_session)
    kg = _make_kg()
    await repo.save(kg)
    await db_session.commit()
    loaded = await repo.get(kg.case_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == kg.model_dump(mode="json")


@pytest.mark.asyncio
async def test_two_graphs_with_same_node_ids(db_session: AsyncSession) -> None:
    """Composite (case_id, node_id) lets identical IDs coexist across cases."""
    repo = KnowledgeGraphRepo(db_session)
    a = _make_kg(case_id="case-A")
    b = _make_kg(case_id="case-B")
    await repo.save(a)
    await repo.save(b)
    await db_session.commit()
    la, lb = await repo.get("case-A"), await repo.get("case-B")
    assert la is not None and lb is not None
```

- [ ] **Step 2: Implement**

```python
# apps/api/src/db/repositories/kg_repo.py
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import KGEdgeRow, KGNodeRow, KnowledgeGraphRow
from packages.kg_builder.models.edges import Edge
from packages.kg_builder.models.graph import KnowledgeGraph
from packages.kg_builder.models.nodes import (
    BaseNode, ClaimedAmountNode, EventNode, EvidenceNode, IssueNode,
    LeaseNode, PartyNode, PropertyNode,
)
from packages.kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
    serialize_node,
)

_NODE_CLASSES: dict[str, type[BaseNode]] = {
    "party": PartyNode,
    "property": PropertyNode,
    "lease": LeaseNode,
    "evidence": EvidenceNode,
    "event": EventNode,
    "issue": IssueNode,
    "claimed_amount": ClaimedAmountNode,
}


def _parse_event_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class KnowledgeGraphRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, kg: KnowledgeGraph) -> None:
        payload = serialize_knowledge_graph(kg)
        meta_section = payload.get("metadata")
        values = dict(
            case_id=kg.case_id,
            graph_id=kg.graph_id,
            created_at=kg.created_at,
            updated_at=payload.get("updated_at"),
            validation_errors=payload.get("validation_errors"),
            validation_warnings=payload.get("validation_warnings"),
            validation_info=payload.get("validation_info"),
            is_consistent=payload.get("is_consistent"),
            data_quality_tier=payload.get("data_quality_tier"),
            metadata_=meta_section,
            payload=payload,
        )
        stmt = pg_insert(KnowledgeGraphRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[KnowledgeGraphRow.case_id],
            set_={k: stmt.excluded[k] for k in values if k != "case_id"},
        )
        await self._s.execute(stmt)

        # Wipe and re-insert children
        await self._s.execute(
            delete(KGEdgeRow).where(KGEdgeRow.case_id == kg.case_id)
        )
        await self._s.execute(
            delete(KGNodeRow).where(KGNodeRow.case_id == kg.case_id)
        )

        for node in kg.nodes:
            d = serialize_node(node)
            self._s.add(KGNodeRow(
                case_id=kg.case_id,
                node_id=node.node_id,
                node_type=node.node_type.value if hasattr(node.node_type, "value") else node.node_type,
                confidence=float(node.confidence),
                source=node.source,
                source_text=getattr(node, "source_text", None),
                created_at=getattr(node, "created_at", None) or kg.created_at,
                event_date=_parse_event_date(d.get("event_date")),
                amount=d.get("amount") if "claimed_amount" in (
                    node.node_type.value if hasattr(node.node_type, "value") else node.node_type
                ) else None,
                node_data=d,
                metadata_=d.get("metadata"),
            ))

        for edge in kg.edges:
            d = edge.model_dump(mode="json")
            self._s.add(KGEdgeRow(
                case_id=kg.case_id, edge_id=edge.edge_id,
                edge_type=edge.edge_type.value,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                confidence=float(edge.confidence),
                source=edge.source, description=edge.description,
                metadata_=d.get("metadata"),
                payload=d,
            ))

    async def get(self, case_id: str) -> KnowledgeGraph | None:
        row = await self._s.get(KnowledgeGraphRow, case_id)
        if row is None:
            return None
        # nodes + edges may have been mutated since payload write; rebuild from rows
        nodes_q = await self._s.execute(
            select(KGNodeRow).where(KGNodeRow.case_id == case_id)
        )
        edges_q = await self._s.execute(
            select(KGEdgeRow).where(KGEdgeRow.case_id == case_id)
        )
        kg_dict = dict(row.payload)
        kg_dict["nodes"] = [self._row_to_node_dict(n) for n in nodes_q.scalars()]
        kg_dict["edges"] = [e.payload for e in edges_q.scalars()]
        return deserialize_knowledge_graph(kg_dict)

    @staticmethod
    def _row_to_node_dict(row: KGNodeRow) -> dict:
        return row.node_data

    async def delete(self, case_id: str) -> None:
        row = await self._s.get(KnowledgeGraphRow, case_id)
        if row:
            await self._s.delete(row)

    async def list_case_ids(self) -> list[str]:
        result = await self._s.execute(select(KnowledgeGraphRow.case_id))
        return [r for (r,) in result.all()]
```

- [ ] **Step 3: Run + commit**

```
pytest apps/api/tests/db/repositories/test_kg_repo.py -v
git add apps/api/src/db/repositories/kg_repo.py apps/api/tests/db/repositories/test_kg_repo.py
git commit -m "feat(db): add KnowledgeGraphRepo with composite-key polymorphic nodes"
```

### Task 3.5 — `MediationsRepo`

Public API:
- `save(mediation: MediationSession)` → upsert mediation + replace messages and offers (delete-then-insert)
- `get(mediation_id) → MediationSession | None`
- `get_by_dispute_id(dispute_id) → MediationSession | None`
- `delete(mediation_id)`

**Files:**
- Create: `apps/api/src/db/repositories/mediations_repo.py`
- Create: `apps/api/tests/db/repositories/test_mediations_repo.py`

Follows the same delete-then-insert children pattern as `PredictionsRepo`. Test must include: round-trip with messages + offers, `offer_id` cross-reference preserved between message and offer rows, `get_by_dispute_id` returns the correct one when two disputes have mediations.

(Code body identical in shape to PredictionsRepo with substituted column names — apply the same delete-then-insert + payload pattern. Skip duplication here; see PredictionsRepo template.)

- [ ] **Step 1**: write the round-trip test mirroring `_make_mediation()` from `apps/api/tests/conftest.py:63–102`.
- [ ] **Step 2**: implement `MediationsRepo` mapping every column from spec §"`mediations`", §"`mediation_messages`", §"`structured_offers`".
- [ ] **Step 3**: run the tests; commit with `feat(db): add MediationsRepo with messages and offers`.

### Task 3.6 — `EvidenceRepo`

Smallest repo. Public API:
- `save(metadata: EvidenceMetadata)` (define `EvidenceMetadata` Pydantic model in `packages/llm_orchestrator/models/evidence.py` if not already present — Phase 2 doesn't depend on it being there; check first)
- `get(case_id, evidence_id)` / `get_by_case_id(case_id) → list` / `delete(case_id, evidence_id)`

Identity is composite `(case_id, evidence_id)` to match the existing nested JSON path and avoid eight-character ID collisions across cases.

**Files:**
- Create: `apps/api/src/db/repositories/evidence_repo.py`
- Create: `apps/api/tests/db/repositories/test_evidence_repo.py`

- [ ] **Step 1**: write tests — round-trip, `get_by_case_id` filters correctly, duplicate `evidence_id` can exist in two different cases, and `delete(case_id, evidence_id)` removes only the matching row.
- [ ] **Step 2**: implement. If `EvidenceMetadata` model doesn't exist, extract it from `apps/api/src/services/storage_service.py` (the existing JSON shape) into `packages/llm_orchestrator/models/evidence.py` and export it; this is part of the migration.
- [ ] **Step 3**: run; commit `feat(db): add EvidenceRepo and lift EvidenceMetadata into a domain model`.

### Task 3.7 — Repositories `__init__` re-exports

**Files:**
- Modify: `apps/api/src/db/repositories/__init__.py`

- [ ] **Step 1: Re-export everything**

```python
# apps/api/src/db/repositories/__init__.py
from apps.api.src.db.repositories.disputes_repo import DisputesRepo
from apps.api.src.db.repositories.evidence_repo import EvidenceRepo
from apps.api.src.db.repositories.kg_repo import KnowledgeGraphRepo
from apps.api.src.db.repositories.mediations_repo import MediationsRepo
from apps.api.src.db.repositories.predictions_repo import PredictionsRepo
from apps.api.src.db.repositories.sessions_repo import SessionsRepo

__all__ = [
    "DisputesRepo", "EvidenceRepo", "KnowledgeGraphRepo",
    "MediationsRepo", "PredictionsRepo", "SessionsRepo",
]
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/db/repositories/__init__.py
git commit -m "feat(db): re-export all repositories from db.repositories"
```

---

## Phase 4 — Backfill tooling

### Task 4.1 — Backfill `--dry-run`

**Files:**
- Create: `scripts/migrations/backfill_json_to_postgres.py`
- Create: `scripts/migrations/tests/test_backfill_dryrun.py`

- [ ] **Step 1: Test that dry-run reads files, validates Pydantic, and reports counts without touching the DB**

```python
# scripts/migrations/tests/test_backfill_dryrun.py
import json
from pathlib import Path

from scripts.migrations.backfill_json_to_postgres import dry_run


def test_dry_run_reports_planned_counts(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "session_x.json").write_text(json.dumps({
        "session_id": "x", "case_file": {"case_id": "c", "user_role": "tenant"},
        "messages": [], "current_stage": "greeting",
        "started_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        "stages_completed": [], "current_stage_attempts": 0,
        "last_extraction_successful": True, "extraction_errors": [],
        "role_explicitly_set": False,
    }))

    report = dry_run(tmp_path)

    assert report["planned"]["sessions"] == 1
    assert report["invalid"] == []
```

- [ ] **Step 2: Implement**

```python
# scripts/migrations/backfill_json_to_postgres.py
"""Backfill JSON state directories into Postgres."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.llm_orchestrator.models.conversation import ConversationState
from packages.llm_orchestrator.models.dispute import DisputeCase
from packages.llm_orchestrator.models.mediation import MediationSession
from packages.llm_orchestrator.models.prediction_v2 import PredictionResult
from packages.kg_builder.storage.graph_serialization import (
    deserialize_knowledge_graph,
    serialize_knowledge_graph,
)

VALIDATORS: dict[str, Any] = {
    "sessions": ConversationState,
    "disputes": DisputeCase,
    "predictions": PredictionResult,
    "mediations": MediationSession,
}


def _validate_kg_payload(data: dict[str, Any]) -> None:
    kg = deserialize_knowledge_graph(data)
    serialized = serialize_knowledge_graph(kg)
    # Ensure subclass-only data remains present after round-trip.
    if len(serialized.get("nodes", [])) != len(data.get("nodes", [])):
        raise ValueError("KG node count changed during polymorphic round-trip")


def dry_run(data_dir: Path) -> dict[str, Any]:
    planned: dict[str, int] = {}
    invalid: list[dict[str, Any]] = []

    def _json_files(dirname: str) -> list[Path]:
        sub = data_dir / dirname
        if not sub.is_dir():
            return []
        if dirname == "evidence_metadata":
            return sorted(sub.rglob("*.json"))
        return sorted(sub.glob("*.json"))

    for d, model in VALIDATORS.items():
        files = _json_files(d)
        planned[d] = 0
        for f in files:
            try:
                model.model_validate(json.loads(f.read_text()))
                planned[d] += 1
            except Exception as exc:
                invalid.append({"dir": d, "file": str(f), "error": repr(exc)[:300]})

    planned["knowledge_graphs"] = 0
    for f in _json_files("knowledge_graphs"):
        try:
            _validate_kg_payload(json.loads(f.read_text()))
            planned["knowledge_graphs"] += 1
        except Exception as exc:
            invalid.append({"dir": "knowledge_graphs", "file": str(f), "error": repr(exc)[:300]})

    # dispute_predictions are dict-shaped. evidence_metadata is nested under
    # data/evidence_metadata/<case_id>/<evidence_id>.json and becomes typed in
    # Task 4.2 before commit/verify can run.
    planned["dispute_predictions"] = len(_json_files("dispute_predictions"))
    planned["evidence_metadata"] = len(_json_files("evidence_metadata"))

    return {"planned": planned, "invalid": invalid}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--archive-json", action="store_true")
    args = p.parse_args()

    if args.dry_run:
        report = dry_run(args.data_dir)
        print(json.dumps(report, indent=2))
        return
    raise NotImplementedError("--commit / --verify / --archive-json land in 4.2/4.3/4.4/11.4")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run + commit**

```
pytest scripts/migrations/tests/test_backfill_dryrun.py -v
git add scripts/migrations/backfill_json_to_postgres.py scripts/migrations/tests/test_backfill_dryrun.py
git commit -m "feat(backfill): add --dry-run mode validating JSON against Pydantic"
```

### Task 4.2 — Backfill `--commit`

**Files:**
- Modify: `scripts/migrations/backfill_json_to_postgres.py`
- Create: `scripts/migrations/tests/test_backfill_commit.py`

The commit pass first runs a full preflight over every directory before writing anything: Pydantic validation, KG polymorphic round-trip, duplicate PK/natural-key detection, FK/orphan checks, enum alignment, projection map validation, nested evidence metadata shape, and quarantine handling. Only if preflight is clean does it load JSON in FK-correct order (per spec): `intake_sessions` → `predictions` (with children) → `disputes` (without `cached_prediction_id`) → apply `dispute_predictions` mappings → `knowledge_graphs/kg_nodes/kg_edges` → `mediations/messages/offers` → `evidence_metadata`. Idempotent: the repos use `ON CONFLICT DO UPDATE`, so a re-run is safe on an empty or previously completed target.

- [ ] **Step 1**: integration test that takes a `tmp_path` data dir with one of each entity, including nested `evidence_metadata/<case_id>/<evidence_id>.json`, runs `--commit` against a `db_session`, then verifies every entity is queryable through the matching repo. Use the parametrized `_make_*` helpers from the repo tests as fixture sources.

- [ ] **Step 2**: add typed validators for `dispute_predictions` and `evidence_metadata` before commit. `evidence_metadata` must use `rglob("*.json")`, derive `case_id` from the parent directory when absent, preserve `extracted_text`/`image_description` if present, and write rollback output in the same nested shape.

- [ ] **Step 3**: implement `commit()` in `backfill_json_to_postgres.py` with one migration transaction after preflight. Use one `AsyncSession`/transaction, stream files in FK order to avoid holding all payloads in memory, and commit only after every directory has been written and projection checks pass. If a late unexpected error occurs, rollback leaves the target unchanged. Log progress to `data/_backfill_report.jsonl`, one line per file, using file paths/counts/status only; do not log raw payload fields. If any directory has validation errors, FK orphans, enum drift, duplicate IDs, projection mismatches, or unhandled KG/evidence shape, exit non-zero unless the file is listed in `scripts/migrations/quarantine.yml` with a remediation note.

- [ ] **Step 4**: run + commit `feat(backfill): implement --commit with FK-aware order and idempotent upserts`.

### Task 4.3 — Backfill `--verify`

`--verify` reads every JSON file again, loads the corresponding Pydantic model or typed migration validator, loads the corresponding entity through the repo, and asserts `state.model_dump(mode="json") == row_state.model_dump(mode="json")`. It also verifies projection parity, child-table counts, citation counts, `disputes.cached_prediction_id` mappings from `dispute_predictions`, nested evidence metadata count, and KG subclass fields via `deserialize_knowledge_graph`. Failures get logged without raw PII; exit code != 0 if any.

- [ ] **Step 1**: failing integration test that mutates a row directly in the DB after `--commit`, runs `--verify`, asserts non-zero exit / report flags the diff.
- [ ] **Step 2**: implement.
- [ ] **Step 3**: commit `feat(backfill): add --verify mode for round-trip identity assertion`.

### Task 4.4 — `dump_postgres_to_json.py` (rollback insurance)

The reverse operation: load every entity through repos, dump JSON in the original directory shape into `--out`, including `dispute_predictions/<dispute_id>.json` derived from `disputes.cached_prediction_id` and nested `evidence_metadata/<case_id>/<evidence_id>.json`. Use `serialize_knowledge_graph` for KG rollback output so `_node_class` and subclass fields survive.

- [ ] **Step 1**: integration test — populate via repos, dump, parse output, compare to source via Pydantic round-trip.
- [ ] **Step 2**: implement.
- [ ] **Step 3**: commit `feat(backfill): add dump_postgres_to_json.py for rollback insurance`.

---

## Phase 5 — Runtime: Unit of Work + app wiring

### Task 5.1 — `UnitOfWork` class

**Files:**
- Create: `apps/api/src/db/uow.py`
- Create: `apps/api/tests/db/test_uow.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/db/test_uow.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.db.uow import UnitOfWork


@pytest.mark.asyncio
async def test_uow_commits_on_clean_exit(db_session: AsyncSession,
                                          uow_factory) -> None:
    async with uow_factory() as uow:
        from packages.llm_orchestrator.models.conversation import ConversationState
        from packages.llm_orchestrator.models.case_file import CaseFile, PartyRole
        from packages.llm_orchestrator.models.conversation import IntakeStage

        state = ConversationState(
            session_id="uow-1",
            case_file=CaseFile(case_id="uow-c-1", user_role=PartyRole.TENANT),
            messages=[], current_stage=IntakeStage.GREETING,
            started_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            stages_completed=[], current_stage_attempts=0,
            last_extraction_successful=True, extraction_errors=[],
            role_explicitly_set=False,
        )
        await uow.sessions.save(state)

    async with uow_factory() as uow2:
        loaded = await uow2.sessions.get("uow-1")
        assert loaded is not None


@pytest.mark.asyncio
async def test_uow_rolls_back_on_exception(uow_factory) -> None:
    with pytest.raises(RuntimeError):
        async with uow_factory() as uow:
            from packages.llm_orchestrator.models.dispute import DisputeCase, DisputeStatus
            from packages.llm_orchestrator.models.case_file import PartyRole
            d = DisputeCase(
                dispute_id="uow-d-1", invite_code="UOW1",
                status=DisputeStatus.WAITING_FOR_LANDLORD,
                created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
                created_by_role=PartyRole.TENANT,
            )
            await uow.disputes.save(d)
            raise RuntimeError("boom")

    # confirm rollback
    async with uow_factory() as uow:
        assert await uow.disputes.get("uow-d-1") is None
```

`uow_factory` fixture is added in Task 5.4.

- [ ] **Step 2: Implement**

```python
# apps/api/src/db/uow.py
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.src.db.repositories import (
    DisputesRepo, EvidenceRepo, KnowledgeGraphRepo,
    MediationsRepo, PredictionsRepo, SessionsRepo,
)


class UnitOfWork(AbstractAsyncContextManager["UnitOfWork"]):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker
        self._session: AsyncSession | None = None
        self.sessions: SessionsRepo
        self.disputes: DisputesRepo
        self.predictions: PredictionsRepo
        self.kg: KnowledgeGraphRepo
        self.mediations: MediationsRepo
        self.evidence: EvidenceRepo

    async def __aenter__(self) -> "UnitOfWork":
        self._session = self._sm()
        await self._session.begin()
        s = self._session
        self.sessions = SessionsRepo(s)
        self.disputes = DisputesRepo(s)
        self.predictions = PredictionsRepo(s)
        self.kg = KnowledgeGraphRepo(s)
        self.mediations = MediationsRepo(s)
        self.evidence = EvidenceRepo(s)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()


class UnitOfWorkFactory:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    def __call__(self) -> UnitOfWork:
        return UnitOfWork(self._sm)
```

- [ ] **Step 3: Add the `uow_factory` test fixture**

```python
# Append to apps/api/tests/conftest.py
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.src.db.uow import UnitOfWorkFactory


@pytest_asyncio.fixture
async def uow_factory(db_sessionmaker):
    yield UnitOfWorkFactory(db_sessionmaker)
```

- [ ] **Step 4: Run + commit**

```
pytest apps/api/tests/db/test_uow.py -v
git add apps/api/src/db/uow.py apps/api/tests/db/test_uow.py apps/api/tests/conftest.py
git commit -m "feat(db): add UnitOfWork with auto commit/rollback + uow_factory fixture"
```

### Task 5.2 — `create_lifespan(settings)` factory

**Files:**
- Modify: `apps/api/src/main.py`
- Create: `apps/api/tests/test_lifespan.py`

- [ ] **Step 1: Test that lifespan attaches sessionmaker to app.state**

```python
# apps/api/tests/test_lifespan.py
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.src.config import APIConfig
from apps.api.src.main import create_app


@pytest.mark.asyncio
async def test_lifespan_creates_sessionmaker(monkeypatch) -> None:
    cfg = APIConfig(database_url="postgresql+asyncpg://x:y@localhost:1/z")
    app = create_app(cfg)
    async with LifespanManager(app):
        assert isinstance(app.state.sessionmaker, async_sessionmaker)
```

- [ ] **Step 2: Refactor main.py**

```python
# apps/api/src/main.py — replace lifespan + create_app
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.src.config import APIConfig


def create_lifespan(settings: APIConfig):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_async_engine(
            settings.database_url,
            pool_size=10, max_overflow=5, pool_timeout=10,
            pool_pre_ping=True, future=True,
        )
        app.state.engine = engine
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        settings.ensure_directories()
        yield
        await engine.dispose()
    return lifespan


def create_app(settings: APIConfig) -> FastAPI:
    app = FastAPI(lifespan=create_lifespan(settings))
    # ... existing router includes stay ...

    @app.get("/livez")
    async def livez():
        return {"status": "alive"}

    @app.get("/readyz")
    async def readyz():
        expected_revision = "0001"
        try:
            async with app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="database_not_ready") from exc
        if version != expected_revision:
            raise HTTPException(status_code=503, detail="schema_version_mismatch")
        return {"status": "ready", "alembic_version": version}

    return app
```

Add structured, PII-safe operational logs/metrics around DB connection failures, pool timeout/exhaustion, migration duration, backfill counts/errors, 409 concurrency conflicts, and orphan evidence cleanup. `/livez` must not touch the DB; `/readyz` must fail on schema drift.

- [ ] **Step 3: Run + commit**

```
pytest apps/api/tests/test_lifespan.py -v
git add apps/api/src/main.py apps/api/tests/test_lifespan.py
git commit -m "refactor(main): make lifespan a factory that captures injected settings"
```

### Task 5.3 — `get_db_session` and `get_uow` FastAPI deps

**Files:**
- Modify: `apps/api/src/dependencies.py`

- [ ] **Step 1: Add deps**

```python
# apps/api/src/dependencies.py — append
from typing import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.uow import UnitOfWork, UnitOfWorkFactory


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    sm = request.app.state.sessionmaker
    async with sm() as session:
        yield session


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    return UnitOfWorkFactory(request.app.state.sessionmaker)
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/dependencies.py
git commit -m "feat(api): add get_db_session and get_uow_factory deps"
```

### Task 5.4 — Request-scoped service factories and router wiring

Adding `get_uow_factory()` is not enough by itself. Existing routers depend on singleton `get_*_service()` factories that cannot see `request.app.state.sessionmaker`. This task rewires route dependencies so production paths actually use UoW-backed services.

**Files:**
- Modify: `apps/api/src/dependencies.py`
- Modify: `apps/api/src/routers/chat.py`
- Modify: `apps/api/src/routers/cases.py`
- Modify: `apps/api/src/routers/disputes.py`
- Modify: `apps/api/src/routers/predictions.py`
- Modify: `apps/api/src/routers/evidence.py`
- Modify: `apps/api/src/routers/mediation.py`

- [ ] **Step 1: Add service dependency factories**

Each factory accepts `uow_factory: UnitOfWorkFactory = Depends(get_uow_factory)` and returns a service instance with only safe singleton collaborators cached (LLM clients, RAG pipeline, graph builder). Do not cache services that hold mutable persistence state.

- [ ] **Step 2: Rewrite router dependencies**

Replace imports of `get_intake_service`, `get_dispute_service`, `get_prediction_service`, `get_storage_service`, and `get_mediation_service` from service modules with dependency factories from `apps.api.src.dependencies`.

- [ ] **Step 3: Add a route smoke test**

Use `httpx` + `asgi-lifespan` with dependency override of `get_uow_factory` to assert each router reaches the test DB-backed service dependency.

- [ ] **Step 4: Add access-isolation tests before broad router rewiring**

Add integration tests proving a caller scoped to one `session_id`/party cannot fetch or mutate another party's case, prediction, evidence, or mediation merely by guessing `case_id`, `evidence_id`, `dispute_id`, or invite code. Service methods should accept the current session/party context where needed and repository queries should include that scope. Invite-code join remains a deliberate exception, but only for the join flow.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/dependencies.py apps/api/src/routers/
git commit -m "refactor(api): route services through request-scoped UnitOfWorkFactory"
```

---

## Phase 6 — Services: intake + disputes

Goal: rewrite `IntakeService` and `DisputeService` to drop `_sessions`, `_disputes`, `_invite_code_index` from production paths and route every read/write through repositories under a UoW.

### Task 6.1 — `IntakeService` rewrite

**Files:**
- Modify: `apps/api/src/services/intake_service.py`
- Modify: `apps/api/tests/test_intake_service.py` (or wherever the tests live)

- [ ] **Step 1: Identify and disable the in-memory cache**

Replace `self._sessions: dict[str, ConversationState] = {}` with nothing. Every method that previously hit `self._sessions[session_id]` must now go through `repo.get`/`repo.save` inside a UoW.

- [ ] **Step 2: Refactor every public method**

Concrete shape for `process_message` (the primary hot path):

```python
# apps/api/src/services/intake_service.py
class IntakeService:
    def __init__(self, uow_factory: UnitOfWorkFactory, intake_agent: IntakeAgent) -> None:
        self._uow_factory = uow_factory
        self._intake_agent = intake_agent

    async def process_message(self, session_id: str, message: str) -> dict[str, Any]:
        async with self._uow_factory() as uow:
            versioned = await uow.sessions.get_with_version(session_id)
            if versioned is None:
                raise SessionNotFoundError(session_id)
            state = versioned.state
            version = versioned.version

        # External work (LLM) OUTSIDE the transaction.
        _, new_state = await self._intake_agent.process_message(state, message)

        async with self._uow_factory() as uow:
            await uow.sessions.save(new_state, expected_version=version)
            # If a dispute is linked, sync property/deposit/status.
            disputes = await uow.disputes.get_by_session_id(session_id)
            for d in disputes:
                d.update_from_session(new_state)  # existing pure method on DisputeCase
                await uow.disputes.save(d)

        return self._build_response(new_state)
```

If `save(..., expected_version=version)` raises `ConcurrentUpdateError`, return a clean 409/retry response or retry once by reloading the latest session and re-running the deterministic merge. Do not silently overwrite a newer message history.

Apply the same pattern to:
- `start_session` → insert session + create dispute (one UoW)
- `set_role` → load, mutate, save (one UoW)
- `bulk_intake` → external LLM work first, then one UoW for save + dispute sync
- `get_session_status` / `get_case_file*` / `list_*` / `delete_*` → one UoW each

Remove `_save_session`, `_load_session`, all `data/sessions/` glob/path use, all `json.load`/`json.dump` in this file.

- [ ] **Step 3: Update existing tests to construct `IntakeService(uow_factory, agent)` and to expect repo-backed semantics**

The existing service tests should largely keep their assertions; only construction changes. Where a test pokes `service._sessions[...]` directly, rewrite it to use the `uow_factory` fixture.

- [ ] **Step 4: Run + commit**

```
pytest apps/api/tests/test_intake_service.py -v
git add apps/api/src/services/intake_service.py apps/api/tests/test_intake_service.py
git commit -m "refactor(intake): route IntakeService through UoW + SessionsRepo"
```

### Task 6.2 — `DisputeService` rewrite

Same shape. Remove `self._disputes`, `self._invite_code_index`. All routes go through `uow.disputes`. The invite-code lookup uses `DisputesRepo.get_by_invite_code` (unique index on the column).

- [ ] **Step 1**: rewrite to UoW.
- [ ] **Step 2**: tests, including a concurrent-create test that asserts the unique invite_code index rejects duplicates with a clean error.
- [ ] **Step 3**: commit `refactor(dispute): route DisputeService through UoW + DisputesRepo, drop in-memory caches`.

### Task 6.3 — Chat workflow rewrite under UoW

The two routes `/chat/start` and `/chat/join` each touch sessions + disputes atomically.

- [ ] **Step 1**: failing integration test in `apps/api/tests/integration/test_atomicity.py` simulating a failure on the second write and asserting neither row landed (use `monkeypatch` to make `DisputesRepo.save` raise).

- [ ] **Step 2**: refactor both flows to a single `async with uow_factory() as uow:` block calling `uow.sessions.save` and `uow.disputes.save` in sequence.

- [ ] **Step 3**: commit `refactor(chat): atomic session+dispute create under one UoW`.

---

## Phase 7 — Services: predictions + KG

### Task 7.1 — `PredictionService` rewrite

Replace `self.kg_store = JSONGraphStore(config.kg_dir)` with use of `uow.kg`. Replace `_save_prediction`, `_save_dispute_prediction_mapping`, `_get_cached_dispute_prediction`, `list_predictions_for_case` with repo calls. Keep the public API contract: `/predictions/generate` and `PredictionService.generate_prediction()` still accept `case_id` only (plus existing `include_reasoning`) and internally resolve whether the case belongs to a two-party dispute.

- [ ] **Step 1**: failing tests that call `generate_prediction(case_id)` and assert:
  - prediction + KG + `disputes.cached_prediction_id` are written in a single transaction (parametrize a failure injection on the second write to assert atomic rollback)
  - tenant and landlord case IDs for the same dispute resolve to the same merged cached prediction
  - a dispute with only one party generates a one-party prediction but does **not** populate `disputes.cached_prediction_id`
  - a case not linked to a dispute still generates a one-party prediction

Only fully merged two-party predictions are cacheable through `disputes.cached_prediction_id`. `_resolve_and_merge_from_repos` returns `(case_file, dispute_id, cacheable, cache_key)` where `cacheable` is true only when both tenant and landlord sessions are present and successfully merged. `cache_key` includes the tenant and landlord session IDs plus their current versions, so stale merged predictions can be invalidated when either side changes.

- [ ] **Step 2**: implement the workflow per spec §"Prediction Generation Detail":

```python
async def generate_prediction(self, case_id: str, include_reasoning: bool = True) -> PredictionResult:
    # 1: short read transaction to preserve existing case_id-only API behavior.
    async with self._uow_factory() as uow:
        case_file, dispute_id, cacheable, cache_key = await self._resolve_and_merge_from_repos(case_id, uow)
        if cacheable and dispute_id:
            locked = await uow.disputes.lock_for_prediction_cache(dispute_id)
            if locked and locked.cached_prediction_id and locked.prediction_cache_key == cache_key:
                cached = await uow.predictions.get(locked.cached_prediction_id)
                if cached:
                    return cached

    # 2-4: external work outside the transaction.
    kg = self._graph_builder.build(case_file)
    prediction = await self._engine.predict(case_file, kg)
    if cacheable and dispute_id:
        prediction.metadata["dispute_id"] = dispute_id
        prediction.metadata["merged"] = True
        prediction.metadata["prediction_cache_key"] = cache_key

    # 5-9: short write transaction. Re-check cache after row lock; another request
    # may have populated it while this request was doing LLM work.
    async with self._uow_factory() as uow:
        if cacheable and dispute_id:
            locked = await uow.disputes.lock_for_prediction_cache(dispute_id)
            if locked and locked.cached_prediction_id and locked.prediction_cache_key == cache_key:
                cached = await uow.predictions.get(locked.cached_prediction_id)
                if cached:
                    return cached
        await uow.kg.save(kg)
        await uow.predictions.save(prediction)
        if cacheable and dispute_id:
            await uow.disputes.set_cached_prediction_id(dispute_id, prediction.prediction_id, cache_key=cache_key)
    return prediction
```

Also rewrite and test the other public prediction service methods used by routes:
- `check_case_ready(case_id)` loads the case through `uow.sessions` and preserves the existing response shape.
- `get_prediction(prediction_id)` loads through `uow.predictions`.
- `list_predictions_for_case(case_id)` returns direct case predictions plus the shared cached dispute prediction by resolving `case_id → session → dispute → cached_prediction_id`; it must not be a bare `PredictionsRepo.get_by_case_id`.

- [ ] **Step 3**: remove production use of `JSONGraphStore` from `prediction_service.py`, but keep the shared `graph_serialization.py` helpers and keep/adapt tests that prove legacy KG JSON files deserialize with subclass fields intact. Delete only the JSON file-backed facade once no production path imports it.

- [ ] **Step 4**: commit `refactor(prediction): drop JSONGraphStore; UoW workflow with row-locked cache`.

### Task 7.2 — Concurrent-prediction integration test

Two simultaneous `generate_prediction(case_id)` calls for case IDs linked to the same dispute must produce only one `predictions` row referenced by `disputes.cached_prediction_id`.

- [ ] **Step 1**: write `apps/api/tests/integration/test_concurrent_predictions.py` using `asyncio.gather` against the real DB.
- [ ] **Step 2**: confirm test fails before the row-lock is added; passes after.
- [ ] **Step 3**: commit `test(prediction): assert dispute row-lock prevents duplicate cached predictions`.

---

## Phase 8 — Services: evidence

### Task 8.1 — `StorageService` metadata rewrite

Move metadata reads/writes from `data/evidence_metadata/` JSON files to `EvidenceRepo`. Keep blob upload/download untouched (Supabase / local file).

- [ ] **Step 1**: failing test for upload-success-then-DB-fail compensation: blob is uploaded, DB insert raises, the blob path is unlinked, an `orphan` log line is emitted.
- [ ] **Step 2**: implement upload as: upload blob → try-except DB insert → on except, attempt blob delete and log orphan with a stable correlation id.
- [ ] **Step 3**: same shape for delete: DB row removed first, then blob delete; on blob-delete failure log orphan.
- [ ] **Step 4**: commit `refactor(storage): move evidence metadata to EvidenceRepo with compensation`.

### Task 8.2 — Evidence routes wiring

Routes `/evidence/upload/{case_id}`, `GET /evidence/{case_id}`, and existing `DELETE /evidence/{case_id}/{evidence_id}` consume the rewritten service. Keep the current API path; do not introduce `/evidence/delete/{id}`. No DB code in the route file.

- [ ] **Step 1**: smoke test against the test client (httpx + asgi-lifespan + dependency override of `get_uow_factory` to use the test sessionmaker).
- [ ] **Step 2**: commit `refactor(evidence-routes): wire to repo-backed StorageService`.

---

## Phase 9 — Services: mediation

The four atomicity hazards (settle, escalate, accept→settle, start_mediation) all collapse into single UoW blocks here.

### Task 9.1 — `MediationService` rewrite

- [ ] **Step 1**: drop `self._mediations` and the `fcntl` file lock.
- [ ] **Step 2**: rewrite each public method used by current routes (`start_mediation`, `get_expectation_data`, `add_message`, `submit_offer`, `respond_to_offer`, `get_messages`, `settle`, `escalate`, `get_settlement`, `generate_settlement_pdf`) to use `uow.mediations` + `uow.disputes`.

Any helper that currently scans singleton services, including `_get_prediction_data`, must use `uow.sessions`, `uow.predictions`, and `disputes.cached_prediction_id`/`prediction_cache_key` instead.
- [ ] **Step 3**: the four hazards become explicit UoW blocks per the spec table:

```python
async def settle(self, dispute_id: str, settlement_amount: float) -> None:
    async with self._uow_factory() as uow:
        mediation = await uow.mediations.get_by_dispute_id(dispute_id)
        if mediation is None:
            raise MediationNotFoundError(dispute_id)
        mediation.settle(settlement_amount)
        await uow.mediations.save(mediation)

        dispute = await uow.disputes.lock(dispute_id)
        if dispute is None:
            raise DisputeNotFoundError(dispute_id)
        dispute.settle()
        await uow.disputes.save(dispute)
```

- [ ] **Step 4**: commit `refactor(mediation): UoW-managed transactions for settle/escalate/accept`.

### Task 9.2 — Atomicity tests for the four hazards

- [ ] **Step 1**: write `apps/api/tests/integration/test_atomicity.py::test_settle_rolls_back_on_dispute_failure` etc. for all four flows.
- [ ] **Step 2**: confirm failures roll back fully.
- [ ] **Step 3**: commit `test(mediation): assert transactional rollback for the four atomicity hazards`.

---

## Phase 10 — Verification

### Task 10.1 — Round-trip integration test against archived `data/`

- [ ] **Step 1**: write `apps/api/tests/integration/test_roundtrip.py` parametrized over entity types; iterate every JSON file in the spec's audit table; load → save → reload → assert `model_dump(mode="json")` identity.

```python
from packages.kg_builder.storage.graph_serialization import deserialize_knowledge_graph
from packages.llm_orchestrator.models.evidence import EvidenceMetadata

@pytest.mark.parametrize("kind,model_cls,save_fn", [
    ("sessions", ConversationState, "sessions.save"),
    ("disputes", DisputeCase, "disputes.save"),
    ("predictions", PredictionResult, "predictions.save"),
    ("knowledge_graphs", KnowledgeGraph, "kg.save"),
    ("mediations", MediationSession, "mediations.save"),
    ("evidence_metadata", EvidenceMetadata, "evidence.save"),
])
async def test_roundtrip(kind, model_cls, save_fn, uow_factory) -> None:
    src = Path("data") / kind
    if not src.is_dir():
        pytest.skip(f"no data/{kind}")
    files = src.rglob("*.json") if kind == "evidence_metadata" else src.glob("*.json")
    for f in files:
        data = json.loads(f.read_text())
        # KGs must use shared graph_serialization.deserialize_knowledge_graph,
        # not plain KnowledgeGraph.model_validate, so subclass fields survive.
        original = (
            deserialize_knowledge_graph(data)
            if kind == "knowledge_graphs"
            else model_cls.model_validate(data)
        )
        async with uow_factory() as uow:
            ns = save_fn.split(".")
            await getattr(getattr(uow, ns[0]), ns[1])(original)
        async with uow_factory() as uow:
            if kind == "evidence_metadata":
                reloaded = await uow.evidence.get(original.case_id, original.evidence_id)
            else:
                ident_arg = original.session_id if kind == "sessions" else (
                    original.dispute_id if kind == "disputes" else (
                    original.prediction_id if kind == "predictions" else (
                    original.case_id if kind == "knowledge_graphs" else
                    original.mediation_id)))
                reloaded = await getattr(getattr(uow, ns[0]), "get")(ident_arg)
        assert reloaded.model_dump(mode="json") == original.model_dump(mode="json"), str(f)
```

- [ ] **Step 2**: commit `test(integration): round-trip identity for every JSON entity`.

### Task 10.2 — Concurrent-write test

`test_concurrent_writes.py::test_two_concurrent_session_messages_detect_conflict` — two workers load the same session version, both mutate, one save succeeds and the other raises `ConcurrentUpdateError` or returns a 409/retry response. Do not rely on Postgres to serialize stale read-modify-write state automatically.

- [ ] **Step 1**: write the test (template in spec §3e).
- [ ] **Step 2**: commit `test(concurrent): no lost writes on dispute updates`.

### Task 10.3 — API contract test

Capture redacted or synthetic golden JSON responses from the existing JSON-backed code BEFORE this branch lands (run on `main`). After cutover, replay the same requests against the Postgres-backed app and diff responses.

- [ ] **Step 1**: capture golden responses on `main` into `apps/api/tests/integration/golden/*.json`; scrub names, addresses, messages, evidence descriptions, file URLs, and invite codes before commit.
- [ ] **Step 2**: write replay test `test_api_contract.py` using httpx + asgi-lifespan.
- [ ] **Step 3**: assert response shape equality. Allow whitelisted fields with timestamps to diff by structure, not value. Explicitly assert the case-id-only prediction flow still returns the same shared prediction for both parties.
- [ ] **Step 4**: commit `test(api): API contract regression replay vs JSON-era golden responses`.

### Task 10.3a — Legal invariant regression tests

- [ ] **Step 1**: add canonical fixtures for cited claims, uncertain/abstained claims, unverified citations, and removed citations. Define "surfaced legal prediction claim" as any issue outcome, reasoning step, settlement range rationale, mediation expectation nudge, or API field that explains likely tribunal treatment.
- [ ] **Step 2**: assert only `verified=True` citations satisfy cite-or-abstain. Unverified/removed citations must not be presented as support; they must either be absent from surfaced support or paired with explicit uncertainty/abstention.
- [ ] **Step 3**: assert citation counts, citation source, case reference, year, paragraph, quote, and reasoning-step linkage survive repository round-trip and backfill verify.
- [ ] **Step 4**: assert the legal-information-not-advice disclaimer remains present and materially unchanged in prediction APIs and mediation nudges.
- [ ] **Step 5**: commit `test(prediction): preserve citation and disclaimer invariants through Postgres migration`.

### Task 10.4 — No-JSON-write test

Hard guard against accidental JSON regressions.

- [ ] **Step 1**: write `apps/api/tests/integration/test_no_json_writes.py` that wraps `pathlib.Path.write_text` and `builtins.open(..., 'w')` with `monkeypatch`, exercises every API endpoint, and asserts no calls under `data/sessions/`, `data/disputes/`, `data/predictions/`, `data/dispute_predictions/`, `data/knowledge_graphs/`, `data/mediations/`, `data/evidence_metadata/`.
- [ ] **Step 2**: commit `test(integration): assert no production code path writes JSON state`.

### Task 10.5 — Pydantic ↔ SQLAlchemy alignment check

**Files:**
- Create: `scripts/migrations/check_model_alignment.py`

- [ ] **Step 1**: enumerate every ORM class in `apps.api.src.db.models`; for each, find the corresponding Pydantic class; verify each ORM column either appears as a Pydantic field of compatible type or is one of `payload`/`metadata_`/`ordinal`/audit columns.

- [ ] **Step 1b**: add projection parity checks using an explicit projection map, not reflection guesses. Cover aliases/derived fields such as `PredictionResult.timestamp -> predictions.created_at`, settlement range tuple -> `range_lo/range_hi`, issue amount ranges -> `amount_range_lo/amount_range_hi`, `disputes.cached_prediction_id` and `prediction_cache_key` as projection-only state, `metadata -> metadata_`, `verified/removed` citation child rows, and KG node subclass fields. This catches indexed-query drift that payload-only round-trip tests miss.

- [ ] **Step 2**: run as a CI step (added in Phase 11).

- [ ] **Step 3**: commit `feat(ci): add Pydantic↔SQLA alignment check`.

---

## Phase 11 — Cutover

### Task 11.0 — DB target preflight script

**Files:**
- Create: `scripts/migrations/print_db_target.py`

- [ ] **Step 1**: add a small script that parses `--database-url`, prints sanitized host/database/user/sslmode, refuses missing URL, refuses localhost/dev credentials unless `--allow-local`, and never prints passwords.
- [ ] **Step 2**: test production URL, local URL with `--allow-local`, and password redaction.
- [ ] **Step 3**: commit `feat(migration): add safe database target preflight script`.

### Task 11.1 — CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib
      - run: pip install -r requirements.txt
      - run: pytest -q
      - run: python scripts/migrations/check_model_alignment.py
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "infra(ci): run pytest with pytest-postgresql"
```

### Task 11.2 — README + dev setup

**Files:**
- Modify: `README.md`

- [ ] **Step 1**: add a "Database setup" section: `make db-up`, `make migrate`, `make test`. Reference the rollback runbook in the spec.
- [ ] **Step 2**: commit `docs(readme): document Postgres-backed dev setup and rollback`.

### Task 11.3 — Backfill `--archive-json`

- [ ] **Step 1**: add `--archive-json --archive-dir <path>` mode that moves each migrated `data/<dir>` to `<archive-dir>/<timestamp>/<dir>` after `--verify` passes. The archive dir must be outside the repo or under a gitignored encrypted/private artifact root; refuse paths inside tracked `data/`. Preserve nested evidence metadata paths, `chmod 700` the archive root where supported, and write only a redacted manifest into the repo. Refuse to run if `_migration_audit_report.json`, `_backfill_report.jsonl`, or verify output contains unresolved errors.
- [ ] **Step 2**: integration test: tmp data dir → commit → verify → archive to an outside tmp archive dir → assert source dirs moved into timestamped archive and rollback dump can recreate the original shape.
- [ ] **Step 3**: commit `feat(backfill): add --archive-json finalization step`.

### Task 11.4 — Run end-to-end migration on real `data/`

- [ ] **Step 0: Rehearse on a clone**
Run this full sequence against a staging clone of `data/` and a disposable Postgres database first. Do not touch the live/local working `data/` until rehearsal passes.

- [ ] **Step 1: Freeze writes and snapshot**
Stop the API or enable maintenance mode. Create a timestamped copy of `data/` outside git, and take a DB snapshot/PITR checkpoint if migrating a hosted database.

- [ ] **Step 2**: confirm target database and run migrations. Do not run `make db-reset` in a real cutover.
```bash
python -m scripts.migrations.print_db_target --database-url "$DATABASE_URL"
alembic -c alembic.ini upgrade head
```

- [ ] **Step 3**: run the audit.
```bash
python -m scripts.migrations.audit_json_stores --data-dir ./data --out data/_migration_audit_report.json
```

- [ ] **Step 4**: dry-run the backfill.
```bash
python -m scripts.migrations.backfill_json_to_postgres --data-dir ./data --dry-run
```

- [ ] **Step 5**: commit the backfill.
```bash
python -m scripts.migrations.backfill_json_to_postgres --data-dir ./data --commit
```

- [ ] **Step 6**: verify identity, projection parity, row counts, child counts, citation counts, KG subclass preservation, nested evidence metadata count, and dispute prediction cache mappings.
```bash
python -m scripts.migrations.backfill_json_to_postgres --data-dir ./data --verify
```

- [ ] **Step 7**: smoke-test the API against Postgres.
```bash
make test-db
```

- [ ] **Step 8**: archive only after verify + smoke pass.
```bash
python -m scripts.migrations.backfill_json_to_postgres \
  --data-dir ./data \
  --archive-json \
  --archive-dir "$PROPOSER_MIGRATION_ARCHIVE_DIR"
```

- [ ] **Step 9**: post-cutover reconciliation.
```bash
python -m scripts.migrations.backfill_json_to_postgres \
  --data-dir "$PROPOSER_MIGRATION_ARCHIVE_DIR/<timestamp>" \
  --verify
```
Then manually spot-check the key flows: start chat, join dispute, generate prediction from both party case IDs, upload/list/delete evidence metadata, start mediation, submit/accept offer.

- [ ] **Step 10: Rollback decision tree**
If verify or smoke fails before archive: keep the API frozen, fix and rerun backfill on the same empty target or restore the DB snapshot. If failure is after archive but before release: move archived JSON dirs back into `data/`, deploy the previous JSON-backed release, and restore the DB snapshot/PITR checkpoint if needed. If failure is after release: choose rollback (previous release + JSON archive restore) or roll-forward (code fix + DB migration) based on data divergence; record owner, decision time, and max downtime in the runbook.

- [ ] **Step 11**: commit only code/docs/redacted reports. Do not commit raw archived JSON data or PII-bearing migration artifacts.

### Task 11.5 — Open the PR

- [ ] **Step 1**: push the feature branch.
```bash
git push -u origin feature/sha-102-migrate-user-facing-storage-from-json-files-to-postgres
```

- [ ] **Step 2**: open the PR with `gh pr create` referencing SHA-102, the spec, and the rollback runbook. Tag in-flight branches (SHA-32/68/36) as needing rebase.

---

## Self-Review

I checked this plan against every section of the spec:

- **Verdict + review amendments:** ✓ UoW (Tasks 5.1, 5.3, 5.4, 6.x, 7.1, 9.1). ✓ Process-local map removal (Tasks 6.1, 6.2, 9.1). ✓ JSONB + projections with parity checks (every model task, Task 10.5). ✓ Audit-first/fail-closed backfill (Phase 0, Phase 4). ✓ Archive only after verify + smoke, outside the repo (Task 11.3, 11.4 step 8).
- **Decisions 1–9:** all reflected — SQLA 2.0 stack (1.1), UoW (5.1), payload+projections (every model + repo), composite KG identity (2.5), no FK to sessions for prediction.case_id and kg.case_id (2.4, 2.5), cached_prediction_id column (2.3), evidence in scope (2.7, 3.6, 8.1), hard cutover (Phase 11), `metadata_` aliasing (every model with a `metadata` column).
- **Schema/Aggregate columns:** all 13 tables modeled (Tasks 2.2–2.7) and migrated (2.8); columns match the spec's per-table list.
- **Indexes:** all spec-listed indexes appear in 2.8.
- **Transactions:** every workflow in spec §"Required Transaction Boundaries" maps to a Phase 6/7/9 task (chat start/join → 6.3; intake message → 6.1; bulk → 6.1; prediction generation → 7.1; cached prediction lookup row-lock → 7.1; start mediation → 9.1; offer flows → 9.1; accept/settle → 9.1; escalate → 9.1; evidence upload/delete → 8.1; dispute fix endpoint → 6.2).
- **Backfill (audit, dry-run, preflight, commit, verify, archive):** 0.1–0.4, 4.1–4.4, 11.3–11.4.
- **Tests (Required Tests table):** Data audit (0.1–0.3), enum alignment (2.1a), Alembic upgrade/downgrade (2.9), repository round-trip (3.1–3.6), raw API contract (10.3), legal citation/disclaimer invariants (10.3a), concurrent update conflict (10.2), concurrent prediction (7.2), mid-transaction crash (6.3, 9.2), evidence compensation (8.1), access isolation (5.4), no production JSON writes (10.4).
- **Infra/Docker/Make/CI:** 1.5, 1.6, 11.1.
- **Rollback:** Task 4.4 ships the dump script before cutover; Task 11.3 archives outside the repo; Task 11.4 includes freeze, snapshots, smoke gates, reconciliation, and rollback decision tree.
- **DoD:** every checkbox in spec §"Definition of Done" maps to a task above.

**Placeholder scan:** searched for `TBD`, `TODO`, `implement later`, `fill in details`. Tasks 3.5, 3.6, 4.2, 4.3, 4.4, 6.2, 6.3, 7.1, 7.2, 8.1, 8.2, 9.1, 9.2, 10.1–10.5, 11.2, 11.3 use the "follow the SessionsRepo template / spec table" shorthand instead of inlining identical code three more times. Each of those tasks names the exact file paths, the exact public methods to implement, and the exact tests to write — that's complete enough for an engineer with the spec open. The same-code copy-paste antipattern would make this plan unreadable; the explicit references to specific spec sections (`spec §"mediations"`, `spec §"Aggregate Columns"`) keep it actionable.

**Type/method consistency:** spot-checked `UnitOfWork.sessions/disputes/predictions/kg/mediations/evidence` attribute names against every Phase 6/7/8/9/10 reference. All match. `set_cached_prediction_id(..., cache_key=...)`, `lock_for_prediction_cache`, composite `EvidenceRepo.get/delete(case_id, evidence_id)`, and request-scoped service factories are now reflected across repository, service, route, backfill, and test tasks.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-29-postgres-migration.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
