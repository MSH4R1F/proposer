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


def test_production_rejects_debug(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://u:p@db.example.com:5432/proposer?sslmode=require",
    )

    with pytest.raises(ValueError, match="DEBUG"):
        APIConfig.from_env()
