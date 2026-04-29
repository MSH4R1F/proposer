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
