"""Round-trip tests for the 0002 proposition KG migration.

Mirrors `test_migration_roundtrip.py`: spawns an ephemeral Postgres via
`pytest_postgresql.factories.postgresql_proc`, creates a fresh database, sets
`DATABASE_URL`, shells out to `alembic`, and verifies schema state with psycopg.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from pytest_postgresql import factories

postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")


PROPOSITION_TABLES = (
    "decision_documents",
    "proposition_extraction_runs",
    "propositions",
    "proposition_edges",
)
PROPOSITION_ENUMS = (
    "proposition_type",
    "proposition_edge_type",
    "proposition_run_status",
)


def _admin_url(postgresql_proc) -> str:
    return (
        f"postgresql://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/postgres"
    )


def _db_url(postgresql_proc, db_name: str) -> str:
    return (
        f"postgresql://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/{db_name}"
    )


def _async_url_for_db(postgresql_proc, db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{postgresql_proc.user}:@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/{db_name}"
    )


def _make_db(postgresql_proc) -> tuple[str, str, dict[str, str], Path]:
    db_name = f"proposer_prop_mig_{uuid.uuid4().hex[:12]}"
    admin_url = _admin_url(postgresql_proc)
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {db_name}")
    env = {**os.environ, "DATABASE_URL": _async_url_for_db(postgresql_proc, db_name)}
    cwd = Path(__file__).resolve().parents[4]
    return db_name, admin_url, env, cwd


def _drop_db(admin_url: str, db_name: str) -> None:
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


def _alembic(args: list[str], env: dict[str, str], cwd: Path) -> None:
    subprocess.run(
        ["alembic", "-c", "alembic.ini", *args],
        check=True,
        env=env,
        cwd=cwd,
    )


def test_alembic_upgrade_creates_proposition_tables(postgresql_proc) -> None:
    """upgrade head must create all 4 tables and 3 enums."""
    import psycopg

    db_name, admin_url, env, cwd = _make_db(postgresql_proc)
    try:
        _alembic(["upgrade", "head"], env, cwd)
        with psycopg.connect(_db_url(postgresql_proc, db_name)) as conn:
            for table in PROPOSITION_TABLES:
                row = conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                ).fetchone()
                assert row is not None, f"table {table} missing after upgrade"

            for enum_name in PROPOSITION_ENUMS:
                row = conn.execute(
                    "SELECT 1 FROM pg_type WHERE typname = %s",
                    (enum_name,),
                ).fetchone()
                assert row is not None, f"enum {enum_name} missing after upgrade"

            # Spot-check distinctive constraints to confirm schema fidelity.
            # Note: uq_proposition_runs_document_extractor was dropped in
            # Task 9 — see test_proposition_run_no_pipeline_unique_constraint.
            for cname in (
                "ck_proposition_edges_no_self_loop",
                "uq_proposition_edges_triple",
                "ck_propositions_confidence_range",
            ):
                row = conn.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    (cname,),
                ).fetchone()
                assert row is not None, f"constraint {cname} missing after upgrade"

            # And the dropped one must NOT exist:
            row = conn.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s",
                ("uq_proposition_runs_document_extractor",),
            ).fetchone()
            assert row is None, (
                "uq_proposition_runs_document_extractor should have been "
                "dropped in Task 9 to allow deliberate re-runs"
            )
    finally:
        _drop_db(admin_url, db_name)


def test_alembic_downgrade_to_0001_removes_proposition_tables(postgresql_proc) -> None:
    """downgrade 0001 must drop the 4 tables and 3 enums but leave 0001 intact."""
    import psycopg

    db_name, admin_url, env, cwd = _make_db(postgresql_proc)
    try:
        _alembic(["upgrade", "head"], env, cwd)
        _alembic(["downgrade", "0001"], env, cwd)
        with psycopg.connect(_db_url(postgresql_proc, db_name)) as conn:
            for table in PROPOSITION_TABLES:
                row = conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (table,),
                ).fetchone()
                assert row is None, f"table {table} still present after downgrade"

            for enum_name in PROPOSITION_ENUMS:
                row = conn.execute(
                    "SELECT 1 FROM pg_type WHERE typname = %s",
                    (enum_name,),
                ).fetchone()
                assert row is None, f"enum {enum_name} still present after downgrade"

            # 0001 schema must remain — kg_nodes is a 0001 table.
            row = conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'kg_nodes'"
            ).fetchone()
            assert row is not None, "0001 table kg_nodes was dropped — downgrade went too far"
    finally:
        _drop_db(admin_url, db_name)


def test_alembic_upgrade_downgrade_upgrade_repeatable(postgresql_proc) -> None:
    """upgrade -> downgrade 0001 -> upgrade must succeed without errors.

    Catches enum-recreation bugs (e.g. enum left undropped on downgrade so the
    second upgrade fails with `type "X" already exists`).
    """
    db_name, admin_url, env, cwd = _make_db(postgresql_proc)
    try:
        _alembic(["upgrade", "head"], env, cwd)
        _alembic(["downgrade", "0001"], env, cwd)
        _alembic(["upgrade", "head"], env, cwd)
    finally:
        _drop_db(admin_url, db_name)
