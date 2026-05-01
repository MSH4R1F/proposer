"""Phase 11.0: DB target preflight script."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(*args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "scripts.migrations.print_db_target", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, env=env,
    )


def test_refuses_missing_url():
    import os
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    r = _run(env=env)
    assert r.returncode == 2
    assert "DATABASE_URL is required" in r.stderr


def test_refuses_localhost_without_allow_local():
    r = _run("--database-url", "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer")
    assert r.returncode == 3
    assert "refusing" in r.stderr


def test_allows_localhost_with_allow_local():
    r = _run("--database-url",
             "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
             "--allow-local")
    assert r.returncode == 0
    assert "host:     localhost" in r.stdout


def test_password_never_printed():
    r = _run("--database-url",
             "postgresql+asyncpg://user:supersecret@db.example.com:5432/proposer?sslmode=require")
    assert r.returncode == 0
    assert "supersecret" not in r.stdout
    assert "supersecret" not in r.stderr
    assert "sslmode:  require" in r.stdout


def test_warns_when_sslmode_unset_on_non_local():
    r = _run("--database-url", "postgresql+asyncpg://u:p@db.example.com:5432/proposer")
    assert r.returncode == 0
    assert "sslmode is unset" in r.stderr


def test_refuses_hostless_dsn_without_allow_local():
    """Unix-socket DSNs (no host) must be treated as local and refused without --allow-local."""
    r = _run("--database-url", "postgresql:///proposer")
    assert r.returncode == 3
    assert "refusing" in r.stderr
