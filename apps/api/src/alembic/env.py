"""Async Alembic env that imports project models for autogenerate."""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.engine import Connection

# Use the same import roots as scripts/api.py so package imports
# (`llm_orchestrator`, `kg_builder`) resolve to a single module identity.
# Without `packages/` on sys.path the model imports below fail with
# ModuleNotFoundError once repositories import the packages without a
# `packages.` prefix.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
for _p in (_PROJECT_ROOT, _PROJECT_ROOT / "packages"):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

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
