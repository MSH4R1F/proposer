"""One-off: verify the API's async engine can reach Supabase Postgres over TLS.

Usage:
    DATABASE_URL="postgresql+asyncpg://...:5432/postgres?sslmode=require" \
        venv/bin/python scripts/deploy/verify_supabase.py

Prints `connected: select1=1 ssl=on` on success. If it errors or reports
`ssl=off`, apply the engine connect_args fix described in the deployment plan
(Task 3) and re-run.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "packages")
sys.path.insert(0, "apps/api/src")

from sqlalchemy import text  # noqa: E402

from apps.api.src.db.engine import create_engine_from_url  # noqa: E402


async def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    engine = create_engine_from_url(url)
    try:
        async with engine.connect() as conn:
            (one,) = (await conn.execute(text("select 1"))).one()
            ssl_on = (await conn.execute(text("show ssl"))).scalar()
        print(f"connected: select1={one} ssl={ssl_on}")
        return 0 if str(ssl_on).lower() == "on" else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
