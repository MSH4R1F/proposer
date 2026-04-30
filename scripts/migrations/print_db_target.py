"""Safe preflight: print the database target Alembic / backfill will hit.

Use BEFORE any cutover step. Refuses to print or proceed if:
  - DATABASE_URL is missing
  - host is localhost / 127.0.0.1 / dev sentinel without --allow-local
  - sslmode is unset for non-local hosts (warning, not blocker)

NEVER prints the password.
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import parse_qs, urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def sanitize(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    qs = parse_qs(parsed.query)
    sslmode = (qs.get("sslmode") or [""])[0]
    return {
        "scheme": parsed.scheme,
        "host": host,
        "port": str(parsed.port) if parsed.port else "(default)",
        "database": parsed.path.lstrip("/") or "(none)",
        "user": parsed.username or "(none)",
        "sslmode": sslmode or "(unset)",
    }


def is_local(host: str) -> bool:
    return host == "" or host in LOCAL_HOSTS


def is_dev_url(url: str) -> bool:
    return "proposer-dev" in url or "://proposer:proposer-dev@" in url


def main() -> int:
    p = argparse.ArgumentParser(description="Print the database target safely.")
    p.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    p.add_argument("--allow-local", action="store_true",
                   help="Permit localhost/dev credentials for development.")
    args = p.parse_args()

    if not args.database_url:
        print("ERROR: DATABASE_URL is required (--database-url or env var)",
              file=sys.stderr)
        return 2

    info = sanitize(args.database_url)
    is_local_host = is_local(info["host"])
    is_dev = is_dev_url(args.database_url)

    if (is_local_host or is_dev) and not args.allow_local:
        print(
            f"ERROR: refusing to target a local/dev URL without --allow-local "
            f"(host={info['host']}, dev_credentials={is_dev})",
            file=sys.stderr,
        )
        return 3

    if not is_local_host and info["sslmode"] == "(unset)":
        print(
            f"WARN: sslmode is unset for non-local host {info['host']!r}",
            file=sys.stderr,
        )

    print(f"scheme:   {info['scheme']}")
    print(f"host:     {info['host']}")
    print(f"port:     {info['port']}")
    print(f"database: {info['database']}")
    print(f"user:     {info['user']}")
    print(f"sslmode:  {info['sslmode']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
